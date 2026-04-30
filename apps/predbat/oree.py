"""OREE (Ukrainian Day-Ahead Market) electricity price integration.

Reads 24 hourly price sensors (UAH/MWh) published by the OREE HA REST sensor
and converts them into the per-minute rate dictionary used by predbat.
"""

from utils import dp4


class Oree:
    """OREE Day-Ahead Market integration for Ukrainian electricity rates.

    Reads 24 individual HA sensors (one per hour) populated by the OREE REST
    sensor and converts the UAH/MWh values into a per-minute rate dictionary
    spanning the full forecast horizon.

    Configuration (apps.yaml):
        metric_oree_import: sensor.oree_dam_hour   # sensor prefix for import
        metric_oree_export: sensor.oree_dam_hour   # sensor prefix for export (optional)
        oree_import_scale: 0.1                     # UAH/MWh → kopecks/kWh
        oree_export_scale: 0.1
    """

    def fetch_oree_rates(self, sensor_prefix, scale=0.1):
        """Fetch OREE DAM prices from 24 HA sensors and return a per-minute rate dict.

        Reads sensors named {sensor_prefix}_1 through {sensor_prefix}_24.
        Prices in UAH/MWh are multiplied by *scale* (default 0.1) to convert
        to kopecks/kWh — the pence-equivalent internal unit used by predbat
        (1 UAH/MWh × 100 kopecks/UAH ÷ 1000 kWh/MWh = 0.1 kopecks/kWh).

        Today's 24-hour pattern is replicated across the full forecast horizon
        so that the optimiser always has rates for every future minute.

        Returns an empty dict if any sensor is missing or contains an invalid value.
        """
        prices = []
        for hour in range(1, 25):
            entity_id = f"{sensor_prefix}_{hour}"
            state = self.get_state_wrapper(entity_id=entity_id, default=None)
            if state is None:
                self.log(f"Warn: OREE sensor {entity_id} not found or unavailable")
                return {}
            try:
                prices.append(float(state) * scale)
            except (ValueError, TypeError):
                self.log(f"Warn: OREE sensor {entity_id} has invalid value: {state!r}")
                return {}

        if self.debug_enable:
            self.log(f"OREE: read {len(prices)} hourly prices from {sensor_prefix}_1..24, min={min(prices):.4f} max={max(prices):.4f}")

        return self._oree_expand_to_minutes(prices)

    def _oree_expand_to_minutes(self, prices):
        """Expand a 24-element hourly price list into a per-minute rate dict.

        Keys are minute offsets from midnight_utc covering the full forecast
        window (forecast_days + 1 days).  Today's pattern repeats for every
        subsequent day so that the optimiser is never rate-starved.
        """
        rate_data = {}
        total_minutes = (self.forecast_days + 1) * 24 * 60
        for minute in range(total_minutes):
            hour_index = (minute % (24 * 60)) // 60  # 0-23
            rate_data[minute] = dp4(prices[hour_index])
        return rate_data
