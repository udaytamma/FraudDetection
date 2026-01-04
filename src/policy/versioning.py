"""
Policy Versioning Service

Manages policy versions with semantic versioning:
- Every change creates a new immutable version
- Rollback creates new version from old content
- Full audit trail linked to transaction evidence

Version format: MAJOR.MINOR.PATCH
- MAJOR: Breaking policy changes
- MINOR: New rules or significant threshold changes
- PATCH: Small adjustments, list updates
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

import yaml
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from .rules import PolicyRules, ScoreThreshold, PolicyRule, RuleAction, FrictionType


class PolicyValidationError(Exception):
    """Raised when policy validation fails."""
    pass


class PolicyVersion(BaseModel):
    """Represents a policy version record."""
    id: int
    version: str
    policy_content: dict
    policy_hash: str
    change_type: str
    change_summary: str
    changed_by: str
    created_at: datetime
    is_active: bool
    previous_version: Optional[str] = None


class ThresholdUpdate(BaseModel):
    """Request to update score thresholds."""
    score_type: str = Field(..., description="risk, criminal, or friendly")
    block_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    review_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    friction_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)

    @field_validator('score_type')
    @classmethod
    def validate_score_type(cls, v):
        if v not in ('risk', 'criminal', 'friendly'):
            raise ValueError('score_type must be risk, criminal, or friendly')
        return v


class RuleUpdate(BaseModel):
    """Request to add or update a rule."""
    id: str
    name: str
    description: Optional[str] = None
    enabled: bool = True
    priority: int = 100
    conditions: dict = Field(default_factory=dict)
    action: str  # ALLOW, FRICTION, REVIEW, BLOCK
    friction_type: Optional[str] = None  # 3DS, OTP, STEP_UP, CAPTCHA
    review_priority: Optional[str] = None  # LOW, MEDIUM, HIGH, URGENT


class ListUpdate(BaseModel):
    """Request to add or remove from a list."""
    list_type: str  # blocklist_cards, blocklist_devices, etc.
    value: str
    action: str = "add"  # add or remove

    @field_validator('list_type')
    @classmethod
    def validate_list_type(cls, v):
        valid_types = [
            'blocklist_cards', 'blocklist_devices', 'blocklist_ips', 'blocklist_users',
            'allowlist_cards', 'allowlist_users', 'allowlist_merchants'
        ]
        if v not in valid_types:
            raise ValueError(f'list_type must be one of: {valid_types}')
        return v


class PolicyVersioningService:
    """
    Service for managing policy versions.

    Implements:
    - Semantic versioning (MAJOR.MINOR.PATCH)
    - Immutable version history
    - Threshold validation
    - YAML file synchronization
    """

    def __init__(self, database_url: str, policy_path: Optional[Path] = None):
        """
        Initialize versioning service.

        Args:
            database_url: PostgreSQL connection URL
            policy_path: Path to policy.yaml file
        """
        self.database_url = database_url
        self.policy_path = policy_path
        self.engine = None
        self.session_factory = None
        self._current_version_id: Optional[int] = None

    async def initialize(self) -> None:
        """Initialize database connection and load/create initial version."""
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        # Check if we have any versions, if not create initial from YAML
        active = await self.get_active_version()
        if not active:
            await self._create_initial_version()

    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()

    async def _create_initial_version(self) -> PolicyVersion:
        """Create initial version from YAML file or defaults."""
        if self.policy_path and self.policy_path.exists():
            with open(self.policy_path) as f:
                config = yaml.safe_load(f)
            policy = PolicyRules(**config)
        else:
            from .rules import DEFAULT_POLICY
            policy = DEFAULT_POLICY

        return await self._save_version(
            policy=policy,
            change_type="initial",
            change_summary="Initial policy version",
            changed_by="system",
            version="1.0.0",
        )

    def _compute_hash(self, policy: PolicyRules) -> str:
        """Compute SHA256 hash of policy content."""
        policy_json = policy.model_dump_json(exclude_none=True)
        return hashlib.sha256(policy_json.encode()).hexdigest()

    def _increment_version(self, current: str, change_type: str) -> str:
        """
        Increment semantic version based on change type.

        - threshold changes: PATCH
        - rule add/update/delete: MINOR
        - rollback: MINOR
        - list changes: PATCH
        """
        match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', current)
        if not match:
            return "1.0.1"

        major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))

        if change_type in ('rule_add', 'rule_update', 'rule_delete', 'rollback'):
            return f"{major}.{minor + 1}.0"
        else:  # threshold, list_add, list_remove
            return f"{major}.{minor}.{patch + 1}"

    def validate_thresholds(self, thresholds: dict[str, ScoreThreshold]) -> None:
        """
        Validate threshold configuration.

        Ensures:
        - friction < review < block
        - All values in valid range
        """
        for score_type, threshold in thresholds.items():
            # Validate ordering: friction < review < block
            if threshold.friction_threshold >= threshold.review_threshold:
                raise PolicyValidationError(
                    f"{score_type}: friction_threshold ({threshold.friction_threshold}) "
                    f"must be less than review_threshold ({threshold.review_threshold})"
                )
            if threshold.review_threshold >= threshold.block_threshold:
                raise PolicyValidationError(
                    f"{score_type}: review_threshold ({threshold.review_threshold}) "
                    f"must be less than block_threshold ({threshold.block_threshold})"
                )

    async def _save_version(
        self,
        policy: PolicyRules,
        change_type: str,
        change_summary: str,
        changed_by: str,
        version: Optional[str] = None,
    ) -> PolicyVersion:
        """Save a new policy version to database and sync to YAML."""
        # Validate thresholds
        self.validate_thresholds(policy.thresholds)

        # Get current active version for previous_version reference
        current = await self.get_active_version()
        previous_version = current.version if current else None

        # Compute new version if not provided
        if not version:
            version = self._increment_version(
                previous_version or "1.0.0",
                change_type
            )

        # Update policy version string
        policy.version = version

        # Compute hash
        policy_hash = self._compute_hash(policy)

        # Convert policy to JSON-serializable dict
        policy_dict = json.loads(policy.model_dump_json())

        async with self.session_factory() as session:
            # Deactivate current active version
            await session.execute(
                text("UPDATE policy_versions SET is_active = FALSE WHERE is_active = TRUE")
            )

            # Insert new version
            result = await session.execute(
                text("""
                    INSERT INTO policy_versions (
                        version, policy_content, policy_hash, change_type,
                        change_summary, changed_by, is_active, previous_version
                    ) VALUES (
                        :version, :policy_content, :policy_hash, :change_type,
                        :change_summary, :changed_by, TRUE, :previous_version
                    )
                    RETURNING id, created_at
                """),
                {
                    "version": version,
                    "policy_content": json.dumps(policy_dict),
                    "policy_hash": policy_hash,
                    "change_type": change_type,
                    "change_summary": change_summary,
                    "changed_by": changed_by,
                    "previous_version": previous_version,
                },
            )
            row = result.fetchone()
            await session.commit()

            # Cache current version ID
            self._current_version_id = row[0]

        # Sync to YAML file
        await self._sync_to_yaml(policy)

        return PolicyVersion(
            id=row[0],
            version=version,
            policy_content=policy_dict,
            policy_hash=policy_hash,
            change_type=change_type,
            change_summary=change_summary,
            changed_by=changed_by,
            created_at=row[1],
            is_active=True,
            previous_version=previous_version,
        )

    async def _sync_to_yaml(self, policy: PolicyRules) -> None:
        """Sync policy to YAML file."""
        if not self.policy_path:
            return

        # Convert to YAML-friendly format
        policy_dict = json.loads(policy.model_dump_json())

        # Convert sets to lists for YAML
        for key in ['blocklist_cards', 'blocklist_devices', 'blocklist_ips',
                    'blocklist_users', 'allowlist_cards', 'allowlist_users',
                    'allowlist_merchants']:
            if key in policy_dict and isinstance(policy_dict[key], list):
                policy_dict[key] = list(policy_dict[key])

        with open(self.policy_path, 'w') as f:
            yaml.dump(policy_dict, f, default_flow_style=False, sort_keys=False)

    async def get_active_version(self) -> Optional[PolicyVersion]:
        """Get the currently active policy version."""
        if not self.session_factory:
            return None

        async with self.session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT id, version, policy_content, policy_hash, change_type,
                           change_summary, changed_by, created_at, is_active, previous_version
                    FROM policy_versions
                    WHERE is_active = TRUE
                    LIMIT 1
                """)
            )
            row = result.fetchone()
            if not row:
                return None

            self._current_version_id = row[0]

            return PolicyVersion(
                id=row[0],
                version=row[1],
                policy_content=row[2] if isinstance(row[2], dict) else json.loads(row[2]),
                policy_hash=row[3],
                change_type=row[4],
                change_summary=row[5],
                changed_by=row[6],
                created_at=row[7],
                is_active=row[8],
                previous_version=row[9],
            )

    async def get_version(self, version: str) -> Optional[PolicyVersion]:
        """Get a specific policy version by version string."""
        async with self.session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT id, version, policy_content, policy_hash, change_type,
                           change_summary, changed_by, created_at, is_active, previous_version
                    FROM policy_versions
                    WHERE version = :version
                """),
                {"version": version},
            )
            row = result.fetchone()
            if not row:
                return None

            return PolicyVersion(
                id=row[0],
                version=row[1],
                policy_content=row[2] if isinstance(row[2], dict) else json.loads(row[2]),
                policy_hash=row[3],
                change_type=row[4],
                change_summary=row[5],
                changed_by=row[6],
                created_at=row[7],
                is_active=row[8],
                previous_version=row[9],
            )

    async def get_version_by_id(self, version_id: int) -> Optional[PolicyVersion]:
        """Get a specific policy version by ID."""
        async with self.session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT id, version, policy_content, policy_hash, change_type,
                           change_summary, changed_by, created_at, is_active, previous_version
                    FROM policy_versions
                    WHERE id = :id
                """),
                {"id": version_id},
            )
            row = result.fetchone()
            if not row:
                return None

            return PolicyVersion(
                id=row[0],
                version=row[1],
                policy_content=row[2] if isinstance(row[2], dict) else json.loads(row[2]),
                policy_hash=row[3],
                change_type=row[4],
                change_summary=row[5],
                changed_by=row[6],
                created_at=row[7],
                is_active=row[8],
                previous_version=row[9],
            )

    async def list_versions(self, limit: int = 50) -> List[PolicyVersion]:
        """List policy versions, most recent first."""
        async with self.session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT id, version, policy_content, policy_hash, change_type,
                           change_summary, changed_by, created_at, is_active, previous_version
                    FROM policy_versions
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            )
            rows = result.fetchall()

            return [
                PolicyVersion(
                    id=row[0],
                    version=row[1],
                    policy_content=row[2] if isinstance(row[2], dict) else json.loads(row[2]),
                    policy_hash=row[3],
                    change_type=row[4],
                    change_summary=row[5],
                    changed_by=row[6],
                    created_at=row[7],
                    is_active=row[8],
                    previous_version=row[9],
                )
                for row in rows
            ]

    @property
    def current_version_id(self) -> Optional[int]:
        """Get the current active version ID for evidence linking."""
        return self._current_version_id

    async def update_thresholds(
        self,
        updates: List[ThresholdUpdate],
        changed_by: str = "system",
    ) -> PolicyVersion:
        """
        Update score thresholds.

        Args:
            updates: List of threshold updates
            changed_by: User making the change

        Returns:
            New policy version
        """
        # Get current policy
        current = await self.get_active_version()
        if not current:
            raise PolicyValidationError("No active policy found")

        policy = PolicyRules(**current.policy_content)

        # Apply updates
        changes = []
        for update in updates:
            if update.score_type not in policy.thresholds:
                policy.thresholds[update.score_type] = ScoreThreshold(
                    score_type=update.score_type
                )

            threshold = policy.thresholds[update.score_type]
            old_values = {}

            if update.block_threshold is not None:
                old_values['block'] = threshold.block_threshold
                threshold.block_threshold = update.block_threshold
            if update.review_threshold is not None:
                old_values['review'] = threshold.review_threshold
                threshold.review_threshold = update.review_threshold
            if update.friction_threshold is not None:
                old_values['friction'] = threshold.friction_threshold
                threshold.friction_threshold = update.friction_threshold

            changes.append(f"{update.score_type}: {old_values}")

        change_summary = f"Updated thresholds: {'; '.join(changes)}"

        return await self._save_version(
            policy=policy,
            change_type="threshold",
            change_summary=change_summary,
            changed_by=changed_by,
        )

    async def add_rule(
        self,
        rule: RuleUpdate,
        changed_by: str = "system",
    ) -> PolicyVersion:
        """Add a new rule to the policy."""
        current = await self.get_active_version()
        if not current:
            raise PolicyValidationError("No active policy found")

        policy = PolicyRules(**current.policy_content)

        # Check if rule ID already exists
        for existing in policy.rules:
            if existing.id == rule.id:
                raise PolicyValidationError(f"Rule with id '{rule.id}' already exists")

        # Create new rule
        new_rule = PolicyRule(
            id=rule.id,
            name=rule.name,
            description=rule.description,
            enabled=rule.enabled,
            priority=rule.priority,
            conditions=rule.conditions,
            action=RuleAction(rule.action),
            friction_type=FrictionType(rule.friction_type) if rule.friction_type else None,
            review_priority=rule.review_priority,
        )

        policy.rules.append(new_rule)

        return await self._save_version(
            policy=policy,
            change_type="rule_add",
            change_summary=f"Added rule: {rule.name} ({rule.id})",
            changed_by=changed_by,
        )

    async def update_rule(
        self,
        rule: RuleUpdate,
        changed_by: str = "system",
    ) -> PolicyVersion:
        """Update an existing rule."""
        current = await self.get_active_version()
        if not current:
            raise PolicyValidationError("No active policy found")

        policy = PolicyRules(**current.policy_content)

        # Find and update rule
        found = False
        for i, existing in enumerate(policy.rules):
            if existing.id == rule.id:
                policy.rules[i] = PolicyRule(
                    id=rule.id,
                    name=rule.name,
                    description=rule.description,
                    enabled=rule.enabled,
                    priority=rule.priority,
                    conditions=rule.conditions,
                    action=RuleAction(rule.action),
                    friction_type=FrictionType(rule.friction_type) if rule.friction_type else None,
                    review_priority=rule.review_priority,
                )
                found = True
                break

        if not found:
            raise PolicyValidationError(f"Rule with id '{rule.id}' not found")

        return await self._save_version(
            policy=policy,
            change_type="rule_update",
            change_summary=f"Updated rule: {rule.name} ({rule.id})",
            changed_by=changed_by,
        )

    async def delete_rule(
        self,
        rule_id: str,
        changed_by: str = "system",
    ) -> PolicyVersion:
        """Delete a rule from the policy."""
        current = await self.get_active_version()
        if not current:
            raise PolicyValidationError("No active policy found")

        policy = PolicyRules(**current.policy_content)

        # Find and remove rule
        original_count = len(policy.rules)
        policy.rules = [r for r in policy.rules if r.id != rule_id]

        if len(policy.rules) == original_count:
            raise PolicyValidationError(f"Rule with id '{rule_id}' not found")

        return await self._save_version(
            policy=policy,
            change_type="rule_delete",
            change_summary=f"Deleted rule: {rule_id}",
            changed_by=changed_by,
        )

    async def update_list(
        self,
        update: ListUpdate,
        changed_by: str = "system",
    ) -> PolicyVersion:
        """Add or remove from a blocklist/allowlist."""
        current = await self.get_active_version()
        if not current:
            raise PolicyValidationError("No active policy found")

        policy = PolicyRules(**current.policy_content)

        # Get the appropriate list
        list_attr = getattr(policy, update.list_type)

        if update.action == "add":
            if update.value in list_attr:
                raise PolicyValidationError(f"'{update.value}' already in {update.list_type}")
            list_attr.add(update.value)
            change_type = "list_add"
            change_summary = f"Added '{update.value}' to {update.list_type}"
        else:  # remove
            if update.value not in list_attr:
                raise PolicyValidationError(f"'{update.value}' not in {update.list_type}")
            list_attr.remove(update.value)
            change_type = "list_remove"
            change_summary = f"Removed '{update.value}' from {update.list_type}"

        return await self._save_version(
            policy=policy,
            change_type=change_type,
            change_summary=change_summary,
            changed_by=changed_by,
        )

    async def rollback(
        self,
        target_version: str,
        changed_by: str = "system",
    ) -> PolicyVersion:
        """
        Rollback to a previous version.

        Creates a new version with the content from the target version.
        Does not delete any history.
        """
        target = await self.get_version(target_version)
        if not target:
            raise PolicyValidationError(f"Version '{target_version}' not found")

        policy = PolicyRules(**target.policy_content)

        return await self._save_version(
            policy=policy,
            change_type="rollback",
            change_summary=f"Rolled back to version {target_version}",
            changed_by=changed_by,
        )

    async def get_policy_for_evidence(self, version_id: int) -> Optional[dict]:
        """Get policy content for a specific version ID (for evidence queries)."""
        version = await self.get_version_by_id(version_id)
        return version.policy_content if version else None
