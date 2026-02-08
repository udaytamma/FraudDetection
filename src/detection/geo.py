"""
Geographic Anomaly Detection

Detects geographic anomalies that indicate fraud:
1. Impossible travel (card used in two distant locations too quickly)
2. Country mismatch (IP country != card country)
3. High-risk countries
4. Geo-inconsistent device behavior

Key signals:
- Transaction location vs previous transaction location
- Card issuing country vs transaction country
- Known high-risk regions
"""

from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
from typing import Optional

from ..schemas import PaymentEvent, FeatureSet, ReasonCodes
from .detector import BaseDetector, DetectionResult


# High-risk countries for fraud (example list - adjust based on data)
HIGH_RISK_COUNTRIES = {
    "NG",  # Nigeria
    "GH",  # Ghana
    "ID",  # Indonesia
    "VN",  # Vietnam
    "PH",  # Philippines
    "UA",  # Ukraine (certain regions)
    "RU",  # Russia
}

# Maximum reasonable travel speed (km/h)
MAX_TRAVEL_SPEED_KMH = 1000  # Allows for air travel


class GeoAnomalyDetector(BaseDetector):
    """
    Detects geographic anomalies in transactions.

    Checks for:
    - Impossible travel between transactions
    - Country mismatches between card and IP
    - Transactions from high-risk countries
    """

    def __init__(
        self,
        max_travel_speed_kmh: float = MAX_TRAVEL_SPEED_KMH,
        high_risk_countries: set[str] = None,
    ):
        """
        Initialize detector.

        Args:
            max_travel_speed_kmh: Max reasonable travel speed
            high_risk_countries: Set of high-risk country codes
        """
        self.max_speed = max_travel_speed_kmh
        self.high_risk_countries = high_risk_countries or HIGH_RISK_COUNTRIES

    async def detect(
        self,
        event: PaymentEvent,
        features: FeatureSet,
    ) -> DetectionResult:
        """
        Run geographic anomaly detection.

        Checks:
        1. Country mismatch (IP vs card)
        2. High-risk country
        3. VPN/Proxy/Datacenter IP
        4. Impossible travel (requires last transaction location)
        """
        result = DetectionResult()
        signals = []

        # =======================================================================
        # Check 1: Country mismatch (IP country != card country)
        # =======================================================================
        if not features.entity.ip_country_card_country_match:
            ip_country = features.entity.ip_country_code
            card_country = event.card_country

            # Weight based on how different the countries are
            if ip_country and card_country:
                signals.append(0.6)
                result.add_reason(
                    code=ReasonCodes.GEO_COUNTRY_MISMATCH,
                    description=f"IP country ({ip_country}) differs from card country ({card_country})",
                    severity="MEDIUM",
                    value=f"IP:{ip_country}, Card:{card_country}",
                )

        # =======================================================================
        # Check 2: High-risk country
        # =======================================================================
        ip_country = features.entity.ip_country_code

        if ip_country and ip_country.upper() in self.high_risk_countries:
            signals.append(0.5)
            result.add_reason(
                code=ReasonCodes.GEO_HIGH_RISK_COUNTRY,
                description=f"Transaction from high-risk country: {ip_country}",
                severity="MEDIUM",
                value=ip_country,
            )

        # =======================================================================
        # Check 3: VPN/Proxy/Datacenter IP (already captured in features)
        # =======================================================================
        if features.entity.ip_is_tor:
            signals.append(0.8)
            result.add_reason(
                code=ReasonCodes.BOT_TOR_EXIT,
                description="Transaction from Tor exit node",
                severity="HIGH",
            )

        if features.entity.ip_is_vpn or features.entity.ip_is_proxy:
            # VPN/proxy is suspicious but not as severe as Tor
            signals.append(0.4)
            result.add_reason(
                code=ReasonCodes.BOT_VPN_PROXY,
                description="Transaction from VPN or proxy",
                severity="LOW",
            )

        if features.entity.ip_is_datacenter:
            # Datacenter IPs are very suspicious for consumer transactions
            signals.append(0.7)
            result.add_reason(
                code=ReasonCodes.BOT_DATACENTER_IP,
                description="Transaction from datacenter IP (non-residential)",
                severity="HIGH",
            )

        # =======================================================================
        # Check 4: Impossible travel (card-level last geo observation)
        # =======================================================================
        if (
            event.geo
            and event.geo.latitude is not None
            and event.geo.longitude is not None
            and features.entity.last_geo_lat is not None
            and features.entity.last_geo_lon is not None
            and features.entity.last_geo_seen is not None
        ):
            is_impossible, speed = self.check_impossible_travel(
                current_lat=event.geo.latitude,
                current_lon=event.geo.longitude,
                current_time=event.timestamp,
                previous_lat=features.entity.last_geo_lat,
                previous_lon=features.entity.last_geo_lon,
                previous_time=features.entity.last_geo_seen,
            )
            if is_impossible:
                signals.append(0.8)
                result.add_reason(
                    code=ReasonCodes.GEO_IMPOSSIBLE_TRAVEL,
                    description="Transaction location implies impossible travel speed",
                    severity="HIGH",
                    value=f"{speed:.0f} km/h" if speed else None,
                )

        # =======================================================================
        # Compute final score
        # =======================================================================
        if signals:
            result.score = min(1.0, max(signals) + 0.05 * (len(signals) - 1))
            result.triggered = result.score >= 0.4

        return result

    @staticmethod
    def calculate_distance_km(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """
        Calculate distance between two points using Haversine formula.

        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates

        Returns:
            Distance in kilometers
        """
        R = 6371  # Earth's radius in km

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c

    def check_impossible_travel(
        self,
        current_lat: float,
        current_lon: float,
        current_time: datetime,
        previous_lat: float,
        previous_lon: float,
        previous_time: datetime,
    ) -> tuple[bool, Optional[float]]:
        """
        Check if travel between two points is physically impossible.

        Args:
            current_lat, current_lon: Current location
            current_time: Current transaction time
            previous_lat, previous_lon: Previous location
            previous_time: Previous transaction time

        Returns:
            Tuple of (is_impossible, calculated_speed_kmh)
        """
        distance_km = self.calculate_distance_km(
            current_lat, current_lon, previous_lat, previous_lon
        )

        time_delta = current_time - previous_time
        hours = time_delta.total_seconds() / 3600

        if hours <= 0:
            # Same time or out of order - can't determine
            return False, None

        speed_kmh = distance_km / hours

        return speed_kmh > self.max_speed, speed_kmh
