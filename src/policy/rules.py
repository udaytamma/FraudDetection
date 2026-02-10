"""
Policy Rules Configuration

Defines the structure for configurable policy rules.
Rules can be loaded from YAML files and hot-reloaded
without code deployment.

Rule hierarchy (evaluated in order):
1. Blocklists/Allowlists (immediate override)
2. Hard thresholds (immediate block)
3. Score-based rules (configurable thresholds)
4. Default decision
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RuleAction(str, Enum):
    """Actions that can be taken by a rule."""
    ALLOW = "ALLOW"
    FRICTION = "FRICTION"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"
    CONTINUE = "CONTINUE"  # Continue to next rule


class FrictionType(str, Enum):
    """Types of friction that can be applied."""
    THREE_DS = "3DS"
    OTP = "OTP"
    STEP_UP = "STEP_UP"
    CAPTCHA = "CAPTCHA"


class PolicyRule(BaseModel):
    """
    Single policy rule definition.

    Rules are evaluated in priority order. First matching rule wins.
    """
    id: str = Field(
        ...,
        description="Unique rule identifier",
    )
    name: str = Field(
        ...,
        description="Human-readable rule name",
    )
    description: Optional[str] = Field(
        default=None,
        description="Rule description",
    )
    enabled: bool = Field(
        default=True,
        description="Whether rule is active",
    )
    priority: int = Field(
        default=100,
        description="Rule priority (lower = higher priority)",
    )

    # Conditions (all must match for rule to trigger)
    conditions: dict = Field(
        default_factory=dict,
        description="Conditions that must all be true",
    )

    # Action to take when rule matches
    action: RuleAction = Field(
        ...,
        description="Action to take",
    )

    # Friction configuration (if action is FRICTION)
    friction_type: Optional[FrictionType] = Field(
        default=None,
        description="Type of friction to apply",
    )

    # Review configuration (if action is REVIEW)
    review_priority: Optional[str] = Field(
        default=None,
        description="Review priority: LOW, MEDIUM, HIGH, URGENT",
    )


class ScoreThreshold(BaseModel):
    """
    Score-based threshold configuration.

    Allows business users to tune thresholds without code changes.
    """
    score_type: str = Field(
        ...,
        description="Which score to check: risk, criminal, friendly",
    )
    block_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Score above this = BLOCK",
    )
    review_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Score above this = REVIEW",
    )
    friction_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Score above this = FRICTION",
    )


class PolicyRules(BaseModel):
    """
    Complete policy configuration.

    Loaded from YAML file and can be hot-reloaded.
    """
    version: str = Field(
        default="1.0.0",
        description="Policy version for audit trail",
    )
    description: Optional[str] = Field(
        default=None,
        description="Policy description",
    )

    # Default decision when no rules match
    default_action: RuleAction = Field(
        default=RuleAction.ALLOW,
        description="Default action when no rules trigger",
    )

    # Score thresholds (primary decision mechanism)
    thresholds: dict[str, ScoreThreshold] = Field(
        default_factory=dict,
        description="Score thresholds by score type",
    )

    # Explicit rules (evaluated before thresholds)
    rules: list[PolicyRule] = Field(
        default_factory=list,
        description="Explicit policy rules",
    )

    # Blocklists
    blocklist_cards: set[str] = Field(
        default_factory=set,
        description="Blocked card tokens",
    )
    blocklist_devices: set[str] = Field(
        default_factory=set,
        description="Blocked device IDs",
    )
    blocklist_ips: set[str] = Field(
        default_factory=set,
        description="Blocked IP addresses",
    )
    blocklist_users: set[str] = Field(
        default_factory=set,
        description="Blocked user IDs",
    )

    # Allowlists (skip fraud checks)
    allowlist_cards: set[str] = Field(
        default_factory=set,
        description="Allowed card tokens (skip checks)",
    )
    allowlist_users: set[str] = Field(
        default_factory=set,
        description="Allowed user IDs (skip checks)",
    )
    allowlist_services: set[str] = Field(
        default_factory=set,
        description="Allowed service IDs (skip checks)",
    )

    def get_sorted_rules(self) -> list[PolicyRule]:
        """Get rules sorted by priority (ascending)."""
        return sorted(
            [r for r in self.rules if r.enabled],
            key=lambda r: r.priority,
        )


# Default policy configuration (fallback)
# ========================================
# This DEFAULT_POLICY serves as the fallback when config/policy.yaml is missing
# or fails to load. It provides minimal, conservative defaults to keep the system
# operational during degraded configuration state.
#
# The deployed policy is in config/policy.yaml, which has additional rules
# (e.g., tor_block, datacenter_review, rooted_high_value) and tuned thresholds.
# The YAML policy is loaded at startup and can be hot-reloaded via POST /policy/reload.
#
# DEFAULT_POLICY thresholds are intentionally more conservative (higher block
# thresholds, fewer rules) to minimize false positives when running without
# the full production policy configuration.
DEFAULT_POLICY = PolicyRules(
    version="1.0.0",
    description="Default fraud detection policy",
    default_action=RuleAction.ALLOW,
    thresholds={
        "risk": ScoreThreshold(
            score_type="risk",
            block_threshold=0.9,
            review_threshold=0.7,
            friction_threshold=0.5,
        ),
        "criminal": ScoreThreshold(
            score_type="criminal",
            block_threshold=0.85,
            review_threshold=0.65,
            friction_threshold=0.45,
        ),
        "friendly": ScoreThreshold(
            score_type="friendly",
            block_threshold=0.95,  # Higher threshold - don't block good customers
            review_threshold=0.6,
            friction_threshold=0.4,
        ),
    },
    rules=[
        # High-value + new account = friction
        PolicyRule(
            id="high_value_new_account",
            name="High Value New Account",
            description="Require friction for high-value transactions from new accounts",
            priority=50,
            conditions={
                "amount_cents_gte": 100000,  # $1000
                "user_is_new": True,
            },
            action=RuleAction.FRICTION,
            friction_type=FrictionType.THREE_DS,
        ),
        # Emulator = block
        PolicyRule(
            id="emulator_block",
            name="Emulator Block",
            description="Block transactions from emulated devices",
            priority=10,
            conditions={
                "device_is_emulator": True,
            },
            action=RuleAction.BLOCK,
        ),
        # Tor = review
        PolicyRule(
            id="tor_review",
            name="Tor Review",
            description="Review transactions from Tor exit nodes",
            priority=20,
            conditions={
                "ip_is_tor": True,
            },
            action=RuleAction.REVIEW,
            review_priority="HIGH",
        ),
    ],
)
