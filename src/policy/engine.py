"""
Policy Engine

Evaluates policy rules and score thresholds to make
fraud decisions. Separated from ML scoring to allow:
- Business-controlled thresholds
- Hot-reload without deployment
- A/B testing of policies
- Full audit trail

Decision flow:
1. Check allowlists (immediate ALLOW)
2. Check blocklists (immediate BLOCK)
3. Evaluate explicit rules (in priority order)
4. Apply score thresholds
5. Return default decision
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("fraud_detection.policy")

from ..schemas import (
    PaymentEvent,
    FeatureSet,
    RiskScores,
    Decision,
    DecisionReason,
    ReasonCodes,
)
from .rules import PolicyRules, RuleAction, DEFAULT_POLICY


class PolicyEngine:
    """
    Policy evaluation engine.

    Loads policy from YAML configuration and evaluates
    transactions against rules and thresholds.
    """

    def __init__(
        self,
        policy: PolicyRules = None,
        policy_path: Optional[Path] = None,
    ):
        """
        Initialize policy engine.

        Args:
            policy: Policy rules (if None, uses default)
            policy_path: Path to YAML policy file (optional)
        """
        self.policy = policy or DEFAULT_POLICY
        self.policy_path = policy_path
        self.policy_hash = self._compute_hash()

        if policy_path and policy_path.exists():
            self.reload_policy()

    def _compute_hash(self) -> str:
        """Compute hash of current policy for audit."""
        policy_json = self.policy.model_dump_json()
        return hashlib.sha256(policy_json.encode()).hexdigest()[:16]

    def reload_policy(self) -> bool:
        """
        Reload policy from YAML file.

        Returns:
            True if reload successful
        """
        if not self.policy_path or not self.policy_path.exists():
            return False

        try:
            with open(self.policy_path) as f:
                config = yaml.safe_load(f)

            self.policy = PolicyRules(**config)
            self.policy_hash = self._compute_hash()
            return True
        except Exception as e:
            # Log error but keep existing policy
            logger.error("Policy reload failed: %s", e)
            return False

    def evaluate(
        self,
        event: PaymentEvent,
        features: FeatureSet,
        scores: RiskScores,
    ) -> tuple[Decision, list[DecisionReason], Optional[str], Optional[str]]:
        """
        Evaluate policy for a transaction.

        Args:
            event: Payment event
            features: Computed features
            scores: Risk scores

        Returns:
            Tuple of (decision, reasons, friction_type, review_priority)
        """
        reasons = []
        friction_type = None
        review_priority = None

        # =======================================================================
        # Step 1: Check allowlists (immediate ALLOW)
        # =======================================================================
        if event.card_token in self.policy.allowlist_cards:
            reasons.append(DecisionReason(
                code=ReasonCodes.ALLOWLIST_CARD,
                description="Card is on allowlist",
                severity="LOW",
            ))
            return Decision.ALLOW, reasons, None, None

        if event.user_id and event.user_id in self.policy.allowlist_users:
            reasons.append(DecisionReason(
                code=ReasonCodes.ALLOWLIST_USER,
                description="User is on allowlist",
                severity="LOW",
            ))
            return Decision.ALLOW, reasons, None, None

        if event.service_id in self.policy.allowlist_services:
            reasons.append(DecisionReason(
                code=ReasonCodes.ALLOWLIST_SERVICE,
                description="Service is on allowlist",
                severity="LOW",
            ))
            return Decision.ALLOW, reasons, None, None

        # =======================================================================
        # Step 2: Check blocklists (immediate BLOCK)
        # =======================================================================
        if event.card_token in self.policy.blocklist_cards:
            reasons.append(DecisionReason(
                code=ReasonCodes.BLOCKLIST_CARD,
                description="Card is on blocklist",
                severity="CRITICAL",
            ))
            return Decision.BLOCK, reasons, None, None

        if event.device_id and event.device_id in self.policy.blocklist_devices:
            reasons.append(DecisionReason(
                code=ReasonCodes.BLOCKLIST_DEVICE,
                description="Device is on blocklist",
                severity="CRITICAL",
            ))
            return Decision.BLOCK, reasons, None, None

        if event.ip_address and event.ip_address in self.policy.blocklist_ips:
            reasons.append(DecisionReason(
                code=ReasonCodes.BLOCKLIST_IP,
                description="IP is on blocklist",
                severity="CRITICAL",
            ))
            return Decision.BLOCK, reasons, None, None

        if event.user_id and event.user_id in self.policy.blocklist_users:
            reasons.append(DecisionReason(
                code=ReasonCodes.BLOCKLIST_USER,
                description="User is on blocklist",
                severity="CRITICAL",
            ))
            return Decision.BLOCK, reasons, None, None

        # =======================================================================
        # Step 3: Evaluate explicit rules
        # =======================================================================
        for rule in self.policy.get_sorted_rules():
            matches, rule_reasons = self._evaluate_rule(rule, event, features, scores)

            if matches:
                reasons.extend(rule_reasons)

                if rule.action == RuleAction.BLOCK:
                    return Decision.BLOCK, reasons, None, None
                elif rule.action == RuleAction.REVIEW:
                    return Decision.REVIEW, reasons, None, rule.review_priority
                elif rule.action == RuleAction.FRICTION:
                    return Decision.FRICTION, reasons, rule.friction_type.value if rule.friction_type else None, None
                elif rule.action == RuleAction.ALLOW:
                    return Decision.ALLOW, reasons, None, None
                # CONTINUE means keep evaluating

        # =======================================================================
        # Step 4: Apply score thresholds
        # =======================================================================
        decision, threshold_reasons, friction_type, review_priority = self._apply_thresholds(scores)
        reasons.extend(threshold_reasons)

        if decision != Decision.ALLOW:
            return decision, reasons, friction_type, review_priority

        # =======================================================================
        # Step 5: Default decision
        # =======================================================================
        return self._convert_action(self.policy.default_action), reasons, None, None

    def _evaluate_rule(
        self,
        rule,
        event: PaymentEvent,
        features: FeatureSet,
        scores: RiskScores,
    ) -> tuple[bool, list[DecisionReason]]:
        """
        Evaluate a single rule against the transaction.

        Returns:
            Tuple of (matches, reasons)
        """
        reasons = []

        for condition_key, expected_value in rule.conditions.items():
            actual_value = self._get_condition_value(condition_key, event, features, scores)

            if not self._check_condition(condition_key, actual_value, expected_value):
                return False, []

        # All conditions matched
        reasons.append(DecisionReason(
            code=f"RULE_{rule.id.upper()}",
            description=rule.description or rule.name,
            severity="HIGH" if rule.action == RuleAction.BLOCK else "MEDIUM",
        ))

        return True, reasons

    def _get_condition_value(
        self,
        key: str,
        event: PaymentEvent,
        features: FeatureSet,
        scores: RiskScores,
    ):
        """Get the value for a condition key."""
        # Score values
        if key == "risk_score":
            return scores.risk_score
        if key == "criminal_score":
            return scores.criminal_score
        if key == "friendly_score":
            return scores.friendly_fraud_score

        # Event values
        if key == "amount_cents":
            return event.amount_cents
        if key.startswith("amount_cents_"):
            return event.amount_cents

        # Feature values
        if key == "device_is_emulator":
            return features.entity.device_is_emulator
        if key == "device_is_rooted":
            return features.entity.device_is_rooted
        if key == "ip_is_tor":
            return features.entity.ip_is_tor
        if key == "ip_is_datacenter":
            return features.entity.ip_is_datacenter
        if key == "ip_is_vpn":
            return features.entity.ip_is_vpn
        if key == "user_is_new":
            return features.entity.user_is_new
        if key == "user_is_guest":
            return features.entity.user_is_guest
        if key == "card_is_new":
            return features.entity.card_is_new

        return None

    def _check_condition(self, key: str, actual, expected) -> bool:
        """Check if a condition is met."""
        if actual is None:
            return False

        # Handle comparison operators in key
        if key.endswith("_gte"):
            return actual >= expected
        if key.endswith("_gt"):
            return actual > expected
        if key.endswith("_lte"):
            return actual <= expected
        if key.endswith("_lt"):
            return actual < expected
        if key.endswith("_ne"):
            return actual != expected

        # Default: equality check
        return actual == expected

    def _apply_thresholds(
        self,
        scores: RiskScores,
    ) -> tuple[Decision, list[DecisionReason], Optional[str], Optional[str]]:
        """
        Apply score thresholds.

        Returns:
            Tuple of (decision, reasons, friction_type, review_priority)
        """
        reasons = []
        highest_decision = Decision.ALLOW
        friction_type = None
        review_priority = None

        # Check each threshold type
        score_values = {
            "risk": scores.risk_score,
            "criminal": scores.criminal_score,
            "friendly": scores.friendly_fraud_score,
        }

        for score_type, threshold in self.policy.thresholds.items():
            score_value = score_values.get(score_type, 0)

            # Check BLOCK threshold
            if score_value >= threshold.block_threshold:
                reasons.append(DecisionReason(
                    code=f"THRESHOLD_{score_type.upper()}_BLOCK",
                    description=f"{score_type.title()} score {score_value:.2f} exceeds block threshold",
                    severity="CRITICAL",
                    value=f"{score_value:.4f}",
                    threshold=f"{threshold.block_threshold:.2f}",
                ))
                return Decision.BLOCK, reasons, None, None

            # Check REVIEW threshold
            if score_value >= threshold.review_threshold:
                if self._decision_priority(Decision.REVIEW) > self._decision_priority(highest_decision):
                    highest_decision = Decision.REVIEW
                    review_priority = "HIGH" if score_value >= 0.8 else "MEDIUM"

                reasons.append(DecisionReason(
                    code=f"THRESHOLD_{score_type.upper()}_REVIEW",
                    description=f"{score_type.title()} score {score_value:.2f} exceeds review threshold",
                    severity="HIGH",
                    value=f"{score_value:.4f}",
                    threshold=f"{threshold.review_threshold:.2f}",
                ))

            # Check FRICTION threshold
            elif score_value >= threshold.friction_threshold:
                if self._decision_priority(Decision.FRICTION) > self._decision_priority(highest_decision):
                    highest_decision = Decision.FRICTION
                    friction_type = "3DS"

                reasons.append(DecisionReason(
                    code=f"THRESHOLD_{score_type.upper()}_FRICTION",
                    description=f"{score_type.title()} score {score_value:.2f} exceeds friction threshold",
                    severity="MEDIUM",
                    value=f"{score_value:.4f}",
                    threshold=f"{threshold.friction_threshold:.2f}",
                ))

        return highest_decision, reasons, friction_type, review_priority

    def _decision_priority(self, decision: Decision) -> int:
        """Get priority of a decision (higher = more severe)."""
        priorities = {
            Decision.ALLOW: 0,
            Decision.FRICTION: 1,
            Decision.REVIEW: 2,
            Decision.BLOCK: 3,
        }
        return priorities.get(decision, 0)

    def _convert_action(self, action: RuleAction) -> Decision:
        """Convert RuleAction to Decision."""
        mapping = {
            RuleAction.ALLOW: Decision.ALLOW,
            RuleAction.FRICTION: Decision.FRICTION,
            RuleAction.REVIEW: Decision.REVIEW,
            RuleAction.BLOCK: Decision.BLOCK,
        }
        return mapping.get(action, Decision.ALLOW)

    @property
    def version(self) -> str:
        """Get current policy version."""
        return self.policy.version

    @property
    def hash(self) -> str:
        """Get current policy hash."""
        return self.policy_hash
