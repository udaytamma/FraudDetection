"""
Bot and Automation Detection

Detects automated fraud attacks using:
1. Device fingerprint signals (emulators, rooted devices)
2. Network signals (datacenter IPs, Tor, VPNs)
3. Behavioral signals (timing patterns, interaction patterns)

Key signals:
- Emulated devices
- Rooted/jailbroken devices
- Datacenter/cloud IPs
- Tor exit nodes
- Suspicious browser/device combinations
"""

from ..schemas import PaymentEvent, FeatureSet, ReasonCodes
from .detector import BaseDetector, DetectionResult


class BotDetector(BaseDetector):
    """
    Detects bot and automation signals.

    Automated fraud is characterized by:
    - Non-consumer devices (emulators, VMs)
    - Non-residential networks (datacenters, cloud)
    - Anonymization (Tor, VPNs)
    - Inconsistent device fingerprints
    """

    async def detect(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> DetectionResult:
        """
        Run bot/automation detection.

        Checks:
        1. Emulator detection
        2. Rooted/jailbroken device
        3. Datacenter IP
        4. Tor exit node
        5. VPN/Proxy
        6. Device fingerprint consistency
        """
        result = DetectionResult()
        signals = []

        # =======================================================================
        # Check 1: Emulator detection
        # =======================================================================
        if features.entity.device_is_emulator:
            signals.append(0.9)
            result.add_reason(
                code=ReasonCodes.BOT_EMULATOR,
                description="Device appears to be an emulator",
                severity="CRITICAL",
            )

        # Also check event-level device info
        if event.device and event.device.is_emulator:
            if not features.entity.device_is_emulator:  # Not already counted
                signals.append(0.9)
                result.add_reason(
                    code=ReasonCodes.BOT_EMULATOR,
                    description="Device fingerprint indicates emulator",
                    severity="CRITICAL",
                )

        # =======================================================================
        # Check 2: Rooted/jailbroken device
        # =======================================================================
        if features.entity.device_is_rooted:
            signals.append(0.6)
            result.add_reason(
                code=ReasonCodes.BOT_ROOTED_DEVICE,
                description="Device appears to be rooted/jailbroken",
                severity="MEDIUM",
            )

        if event.device and event.device.is_rooted:
            if not features.entity.device_is_rooted:
                signals.append(0.6)
                result.add_reason(
                    code=ReasonCodes.BOT_ROOTED_DEVICE,
                    description="Device fingerprint indicates rooted device",
                    severity="MEDIUM",
                )

        # =======================================================================
        # Check 3: Datacenter IP
        # =======================================================================
        if features.entity.ip_is_datacenter:
            signals.append(0.8)
            result.add_reason(
                code=ReasonCodes.BOT_DATACENTER_IP,
                description="Transaction from datacenter IP (non-residential)",
                severity="HIGH",
            )

        if event.geo and event.geo.is_datacenter:
            if not features.entity.ip_is_datacenter:
                signals.append(0.8)
                result.add_reason(
                    code=ReasonCodes.BOT_DATACENTER_IP,
                    description="IP classified as datacenter",
                    severity="HIGH",
                )

        # =======================================================================
        # Check 4: Tor exit node
        # =======================================================================
        if features.entity.ip_is_tor:
            signals.append(0.85)
            result.add_reason(
                code=ReasonCodes.BOT_TOR_EXIT,
                description="Transaction from Tor exit node",
                severity="HIGH",
            )

        if event.geo and event.geo.is_tor:
            if not features.entity.ip_is_tor:
                signals.append(0.85)
                result.add_reason(
                    code=ReasonCodes.BOT_TOR_EXIT,
                    description="IP identified as Tor exit node",
                    severity="HIGH",
                )

        # =======================================================================
        # Check 5: VPN/Proxy
        # =======================================================================
        is_vpn = features.entity.ip_is_vpn or (event.geo and event.geo.is_vpn)
        is_proxy = features.entity.ip_is_proxy or (event.geo and event.geo.is_proxy)

        if is_vpn or is_proxy:
            # VPN alone is common for privacy-conscious users
            # Only flag if combined with other signals
            signals.append(0.3)
            result.add_reason(
                code=ReasonCodes.BOT_VPN_PROXY,
                description="Transaction from VPN or proxy",
                severity="LOW",
            )

        # =======================================================================
        # Check 6: Device fingerprint anomalies
        # =======================================================================
        if event.device:
            device = event.device

            # Suspicious browser/OS combinations
            if self._is_suspicious_user_agent(device):
                signals.append(0.5)
                result.add_reason(
                    code="BOT_SUSPICIOUS_UA",
                    description="Suspicious browser/device combination",
                    severity="MEDIUM",
                )

            # Missing common fingerprint elements
            if self._is_incomplete_fingerprint(device):
                signals.append(0.4)
                result.add_reason(
                    code="BOT_INCOMPLETE_FINGERPRINT",
                    description="Incomplete or suspicious device fingerprint",
                    severity="MEDIUM",
                )

        # =======================================================================
        # Compute final score
        # =======================================================================
        if signals:
            # Bot signals are highly indicative - use max with strong boost
            result.score = min(1.0, max(signals) + 0.08 * (len(signals) - 1))
            result.triggered = result.score >= 0.5

        return result

    def _is_suspicious_user_agent(self, device) -> bool:
        """
        Check for suspicious browser/device combinations.

        Examples:
        - Linux + Safari (Safari doesn't run on Linux)
        - Windows + Chrome on mobile
        - Very old browser versions
        """
        if not device.browser or not device.os:
            return False

        browser = device.browser.lower()
        os = device.os.lower()

        # Safari only runs on Apple devices
        if "safari" in browser and "linux" in os:
            return True

        # iOS apps masquerading as desktop browsers
        if "windows" in os and device.device_type == "mobile":
            return True

        return False

    def _is_incomplete_fingerprint(self, device) -> bool:
        """
        Check for incomplete device fingerprints.

        Missing common elements may indicate fingerprint spoofing.
        """
        # Must have basic elements
        if not device.device_id:
            return True

        # Check for suspicious patterns
        missing_count = 0

        if not device.os:
            missing_count += 1
        if not device.browser:
            missing_count += 1
        if not device.screen_resolution:
            missing_count += 1
        if not device.timezone:
            missing_count += 1
        if not device.language:
            missing_count += 1

        # More than half missing is suspicious
        return missing_count >= 3
