"""Observable record and result validation for generated charging sessions."""
import math
from collections import Counter, defaultdict
from datetime import datetime


FIELDS = [
    "session_id", "station_id", "plug_id", "day_type", "day_of_week", "calendar_basis",
    "arrival_time", "plug_in_time", "start_time", "end_time", "plug_out_time", "exit_time",
    "duration_minutes", "connected_minutes", "queue_wait_minutes", "kwh_consumed",
    "vehicle_type", "charger_type", "charger_power_kw", "average_power_kw",
    "battery_capacity_kwh", "soc_in", "soc_out", "charging_efficiency", "source",
]

CHARGER_POWER_BY_LABEL = {"AC 7 kW": 7.0, "AC 22 kW": 22.0, "DC 60 kW": 60.0}


def validate_rows(rows):
    errors = Counter()
    ids = set()
    intervals = defaultdict(list)
    invalid_ids = set()
    for index, row in enumerate(rows):
        issues = []
        if any(row.get(key) is None or row.get(key) == "" for key in FIELDS):
            issues.append("missing_fields")
        if row.get("session_id") in ids:
            issues.append("duplicate_ids")
        ids.add(row.get("session_id"))
        try:
            times = [
                datetime.fromisoformat(row[key])
                for key in ("arrival_time", "plug_in_time", "start_time", "end_time", "plug_out_time", "exit_time")
            ]
            if any(value.tzinfo is None or value.utcoffset() is None for value in times) or times != sorted(times):
                issues.append("timestamp_order")
            if times[1] != times[2]:
                issues.append("charging_start")
            seconds = (times[3] - times[2]).total_seconds()
            if seconds <= 0 or abs(row["duration_minutes"] - seconds / 60) > 0.011:
                issues.append("active_duration")
            if abs(row["queue_wait_minutes"] - (times[1] - times[0]).total_seconds() / 60) > 0.011:
                issues.append("queue_duration")
            if abs(row["connected_minutes"] - (times[4] - times[1]).total_seconds() / 60) > 0.011:
                issues.append("connected_duration")

            numeric = (
                "kwh_consumed", "soc_in", "soc_out", "average_power_kw", "charger_power_kw",
                "battery_capacity_kwh", "charging_efficiency", "queue_wait_minutes",
                "duration_minutes", "connected_minutes",
            )
            if not all(math.isfinite(row[key]) for key in numeric):
                issues.append("non_finite")
            if not 0 <= row["soc_in"] < row["soc_out"] <= 100:
                issues.append("soc_range")
            if not 0 < row["charging_efficiency"] <= 1:
                issues.append("efficiency")

            energy = row["kwh_consumed"]
            capacity = row["battery_capacity_kwh"]
            expected = capacity * (row["soc_out"] - row["soc_in"]) / 100 / row["charging_efficiency"]
            if energy <= 0 or abs(energy - expected) > 0.0011:
                issues.append("battery_energy")
            if energy > row["charger_power_kw"] * seconds / 3600 + 0.001:
                issues.append("power_limit")
            if seconds > 0 and abs(row["average_power_kw"] - energy * 3600 / seconds) > 0.00011:
                issues.append("average_power")
            if CHARGER_POWER_BY_LABEL.get(row["charger_type"]) != float(row["charger_power_kw"]):
                issues.append("charger_rating")
            if not str(row["plug_id"]).startswith(f"{row['station_id']}-P"):
                issues.append("plug_station")
            intervals[row["plug_id"]].append((times[1], times[4], index))
        except (KeyError, ValueError, TypeError, ZeroDivisionError, OverflowError):
            issues.append("malformed_record")
        if issues:
            invalid_ids.add(index)
            errors.update(set(issues))

    for intervals_for_plug in intervals.values():
        previous_end = None
        for start, end, index in sorted(intervals_for_plug):
            if previous_end is not None and start < previous_end:
                invalid_ids.add(index)
                errors["port_overlap"] += 1
            previous_end = max(previous_end, end) if previous_end else end
    return {
        "checked_rows": len(rows),
        "valid_rows": len(rows) - len(invalid_ids),
        "invalid_rows": len(invalid_ids),
        "errors": dict(errors),
    }


def validate_summary(rows, summary, capacities):
    """Cross-check displayed totals against their source records."""
    errors = []
    station_counts = dict(Counter(row["station_id"] for row in rows))
    hourly_counts = [0] * 24
    for row in rows:
        hourly_counts[datetime.fromisoformat(row["arrival_time"]).hour] += 1
    if summary.get("sessions") != len(rows):
        errors.append("session_total")
    if summary.get("station_counts") != station_counts:
        errors.append("station_totals")
    if summary.get("arrivals_by_hour") != hourly_counts:
        errors.append("hourly_totals")
    if summary.get("total_plugs") != sum(capacities.values()):
        errors.append("plug_total")
    if abs(summary.get("total_energy_kwh", 0) - round(sum(row["kwh_consumed"] for row in rows), 2)) > 0.001:
        errors.append("energy_total")
    if summary.get("waiting_sessions") != sum(row["queue_wait_minutes"] > 0 for row in rows):
        errors.append("waiting_total")
    return {"valid": not errors, "errors": errors}
