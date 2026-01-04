"""
Policy Engine Tests

Tests for policy evaluation logic.
"""

import pytest

from src.schemas import (
    PaymentEvent,
    FeatureSet,
    VelocityFeatures,
    EntityFeatures,
    RiskScores,
    Decision,
)
from src.policy import PolicyEngine
from src.policy.rules import PolicyRules, PolicyRule, RuleAction, ScoreThreshold


class TestPolicyEngine:
    """Tests for policy engine."""

    @pytest.fixture
    def policy(self):
        """Create test policy."""
        return PolicyRules(
            version="1.0.0-test",
            default_action=RuleAction.ALLOW,
            thresholds={
                "risk": ScoreThreshold(
                    score_type="risk",
                    block_threshold=0.9,
                    review_threshold=0.7,
                    friction_threshold=0.5,
                ),
            },
            rules=[
                PolicyRule(
                    id="test_emulator",
                    name="Test Emulator Block",
                    priority=10,
                    conditions={"device_is_emulator": True},
                    action=RuleAction.BLOCK,
                ),
            ],
            blocklist_cards={"blocked_card_token"},
            allowlist_users={"vip_user"},
        )

    @pytest.fixture
    def engine(self, policy):
        return PolicyEngine(policy=policy)

    def test_allowlist_immediate_allow(self, engine, sample_event):
        """Test that allowlisted users get immediate ALLOW."""
        sample_event.user_id = "vip_user"
        features = FeatureSet()
        scores = RiskScores(risk_score=0.95)  # Would normally block

        decision, reasons, _, _ = engine.evaluate(sample_event, features, scores)

        assert decision == Decision.ALLOW
        assert any("ALLOWLIST" in r.code for r in reasons)

    def test_blocklist_immediate_block(self, engine, sample_event):
        """Test that blocklisted cards get immediate BLOCK."""
        sample_event.card_token = "blocked_card_token"
        features = FeatureSet()
        scores = RiskScores(risk_score=0.1)  # Would normally allow

        decision, reasons, _, _ = engine.evaluate(sample_event, features, scores)

        assert decision == Decision.BLOCK
        assert any("BLOCKLIST" in r.code for r in reasons)

    def test_rule_triggers(self, engine, sample_event):
        """Test that rules trigger correctly."""
        features = FeatureSet(
            entity=EntityFeatures(device_is_emulator=True),
        )
        scores = RiskScores(risk_score=0.1)

        decision, reasons, _, _ = engine.evaluate(sample_event, features, scores)

        assert decision == Decision.BLOCK
        assert any("EMULATOR" in r.code for r in reasons)

    def test_threshold_block(self, engine, sample_event):
        """Test score threshold triggers BLOCK."""
        features = FeatureSet()
        scores = RiskScores(risk_score=0.95)

        decision, reasons, _, _ = engine.evaluate(sample_event, features, scores)

        assert decision == Decision.BLOCK
        assert any("THRESHOLD" in r.code and "BLOCK" in r.code for r in reasons)

    def test_threshold_review(self, engine, sample_event):
        """Test score threshold triggers REVIEW."""
        features = FeatureSet()
        scores = RiskScores(risk_score=0.75)

        decision, reasons, _, _ = engine.evaluate(sample_event, features, scores)

        assert decision == Decision.REVIEW
        assert any("THRESHOLD" in r.code and "REVIEW" in r.code for r in reasons)

    def test_threshold_friction(self, engine, sample_event):
        """Test score threshold triggers FRICTION."""
        features = FeatureSet()
        scores = RiskScores(risk_score=0.55)

        decision, reasons, friction_type, _ = engine.evaluate(sample_event, features, scores)

        assert decision == Decision.FRICTION
        assert friction_type is not None

    def test_default_allow(self, engine, sample_event):
        """Test default ALLOW when no rules trigger."""
        features = FeatureSet()
        scores = RiskScores(risk_score=0.1)

        decision, reasons, _, _ = engine.evaluate(sample_event, features, scores)

        assert decision == Decision.ALLOW

    def test_policy_version(self, engine):
        """Test policy version tracking."""
        assert engine.version == "1.0.0-test"
        assert engine.hash is not None


class TestPolicyRules:
    """Tests for policy rules configuration."""

    def test_sorted_rules(self):
        """Test that rules are sorted by priority."""
        policy = PolicyRules(
            rules=[
                PolicyRule(id="low", name="Low", priority=100, action=RuleAction.BLOCK, conditions={}),
                PolicyRule(id="high", name="High", priority=10, action=RuleAction.BLOCK, conditions={}),
                PolicyRule(id="mid", name="Mid", priority=50, action=RuleAction.BLOCK, conditions={}),
            ],
        )

        sorted_rules = policy.get_sorted_rules()

        assert sorted_rules[0].id == "high"
        assert sorted_rules[1].id == "mid"
        assert sorted_rules[2].id == "low"

    def test_disabled_rules_excluded(self):
        """Test that disabled rules are excluded."""
        policy = PolicyRules(
            rules=[
                PolicyRule(id="enabled", name="Enabled", enabled=True, action=RuleAction.BLOCK, conditions={}),
                PolicyRule(id="disabled", name="Disabled", enabled=False, action=RuleAction.BLOCK, conditions={}),
            ],
        )

        sorted_rules = policy.get_sorted_rules()

        assert len(sorted_rules) == 1
        assert sorted_rules[0].id == "enabled"
