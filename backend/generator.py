"""Generate synthetic EV visits, then schedule them on physical charging plugs."""
import csv
import io
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import numpy as np

from model.vae import CHARGERS, ConditionalVAE, conditions
from .scheduler import schedule
from .validation import FIELDS, validate_rows, validate_summary


ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))

CHARGER_INFO = {
    "ac7": ("AC 7 kW", 7.0),
    "ac22": ("AC 22 kW", 22.0),
    "dc60": ("DC 60 kW", 60.0),
}
MIXED_CHARGER_PROBABILITIES = {"ac7": 0.40, "ac22": 0.30, "dc60": 0.30}
MIXED_DAY_PROBABILITIES = {"weekday": 0.55, "weekend": 0.25, "holiday": 0.10, "festival": 0.10}
SCENARIOS = ("calendar", "mixed", "weekday", "weekend", "holiday", "festival")
CHARGER_MODES = ("mixed", *CHARGERS)

ARRIVAL_COMPONENT_RANGES = {
    "morning": (5.5, 10.0),
    "afternoon": (11.5, 16.0),
    "evening": (16.5, 21.5),
    "overnight": (22.0, 27.0),
}
DAY_ARRIVAL_MODIFIERS = {
    "weekday": np.array([1.30, 0.80, 1.15, 0.65]),
    "weekend": np.array([0.70, 1.20, 1.25, 1.10]),
    "holiday": np.array([0.65, 1.15, 1.30, 1.20]),
    "festival": np.array([0.65, 1.00, 1.45, 1.35]),
}

if not math.isclose(sum(MIXED_CHARGER_PROBABILITIES.values()), 1.0, abs_tol=1e-12):
    raise RuntimeError("Mixed charger probabilities must total 100%.")
if not math.isclose(sum(MIXED_DAY_PROBABILITIES.values()), 1.0, abs_tol=1e-12):
    raise RuntimeError("Mixed day probabilities must total 100%.")


def bounded_integer(value, name, low, high):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or int(value) != value
    ):
        raise ValueError(f"{name} must be a whole number.")
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return int(value)


@dataclass(frozen=True)
class Settings:
    row_count: int = 200
    scenario: str = "calendar"
    charger_type: str = "mixed"
    station_count: int = 3
    plugs_per_station: int = 8
    days: int = 1
    start_date: str = "2026-11-16"
    seed: int = 6
    demand_level: str = "normal"

    @classmethod
    def parse(cls, obj):
        if not isinstance(obj, dict):
            raise ValueError("Send an object with generation settings.")
        defaults = asdict(cls(start_date=datetime.now(IST).date().isoformat()))
        if set(obj) - set(defaults):
            raise ValueError("Unknown generation setting.")
        values = {**defaults, **obj}
        for name, low, high in (
            ("row_count", 1, 5000),
            ("station_count", 1, 20),
            ("plugs_per_station", 1, 40),
            ("days", 1, 90),
            ("seed", 0, 2147483647),
        ):
            values[name] = bounded_integer(values[name], name.replace("_", " "), low, high)
        for name, options in (
            ("scenario", SCENARIOS),
            ("charger_type", CHARGER_MODES),
            ("demand_level", ("quiet", "normal", "busy")),
        ):
            if not isinstance(values[name], str) or values[name] not in options:
                raise ValueError(f"Choose a supported {name.replace('_', ' ')}.")
        try:
            first = date.fromisoformat(values["start_date"])
            if not 2000 <= first.year <= 2100:
                raise ValueError()
            first + timedelta(days=values["days"] - 1)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Use a start date between 2000 and 2100 in YYYY-MM-DD format.") from None
        return cls(**values)

    def dates(self):
        first = date.fromisoformat(self.start_date)
        dates = [first + timedelta(days=index) for index in range(self.days)]
        if self.scenario == "weekday":
            dates = [value for value in dates if value.weekday() < 5]
        elif self.scenario == "weekend":
            dates = [value for value in dates if value.weekday() >= 5]
        if not dates:
            raise ValueError(
                f"The selected range has no {self.scenario} dates. Choose a matching start date or more days."
            )
        return dates


def _seeded_categories(rng, probabilities, count, ensure_all=False):
    labels = list(probabilities)
    values = rng.choice(labels, size=count, p=list(probabilities.values()))
    if ensure_all and count >= len(labels):
        values[: len(labels)] = labels
        rng.shuffle(values)
    return [str(value) for value in values]


def _day_types_and_dates(settings, date_rng, day_rng):
    available = settings.dates()
    if settings.scenario == "mixed":
        day_types = _seeded_categories(day_rng, MIXED_DAY_PROBABILITIES, settings.row_count, ensure_all=True)
        chosen = []
        for day_type in day_types:
            if day_type == "weekday":
                matching = [value for value in available if value.weekday() < 5]
            elif day_type == "weekend":
                matching = [value for value in available if value.weekday() >= 5]
            else:
                matching = available
            pool = matching or available
            chosen.append(pool[int(date_rng.integers(0, len(pool)))])
        return day_types, chosen

    chosen = [available[index] for index in date_rng.integers(0, len(available), settings.row_count)]
    if settings.scenario == "calendar":
        day_types = ["weekend" if value.weekday() >= 5 else "weekday" for value in chosen]
    else:
        day_types = [settings.scenario] * settings.row_count
    return day_types, chosen


def _charger_categories(settings, rng):
    if settings.charger_type == "mixed":
        return _seeded_categories(rng, MIXED_CHARGER_PROBABILITIES, settings.row_count, ensure_all=True)
    return [settings.charger_type] * settings.row_count


def _rounded_percentages(labels, weights):
    """Return one-decimal percentages whose integer tenths total exactly 1000."""
    scaled = np.asarray(weights, dtype=float) / np.sum(weights) * 1000
    tenths = np.floor(scaled).astype(int)
    missing = 1000 - int(tenths.sum())
    order = np.argsort(-(scaled - tenths))
    for index in order[:missing]:
        tenths[index] += 1
    return {label: float(value) / 10 for label, value in zip(labels, tenths)}


def _station_assignments(settings, rng):
    station_ids = [f"ST-{index + 1:02d}" for index in range(settings.station_count)]
    raw_weights = rng.uniform(0.65, 1.35, settings.station_count)
    weights = raw_weights / raw_weights.sum()
    if settings.row_count >= settings.station_count:
        assignments = list(range(settings.station_count))
        assignments.extend(
            rng.choice(settings.station_count, size=settings.row_count - settings.station_count, p=weights).tolist()
        )
        rng.shuffle(assignments)
    else:
        assignments = rng.choice(
            settings.station_count, size=settings.row_count, replace=False, p=weights
        ).tolist()
    return [station_ids[index] for index in assignments], _rounded_percentages(station_ids, weights)


def _arrival_hours(rng, day_types, demand_level):
    component_names = list(ARRIVAL_COMPONENT_RANGES)
    centres = np.array(
        [rng.uniform(*ARRIVAL_COMPONENT_RANGES[name]) for name in component_names], dtype=float
    )
    sigmas = rng.uniform(1.15, 2.35, len(component_names))
    base = rng.uniform(0.75, 1.25, len(component_names))
    background_weight = float(rng.uniform(0.10, 0.18))
    rush_component = None
    hours = []

    for day_type in day_types:
        modifier = DAY_ARRIVAL_MODIFIERS[day_type]
        day_weights = base * modifier
        day_weights /= day_weights.sum()
        draw = rng.random()
        if demand_level == "quiet":
            if draw < 0.82:
                hour = rng.uniform(0, 24)
            else:
                component = int(rng.choice(len(component_names), p=day_weights))
                hour = rng.normal(centres[component], 3.2)
        elif demand_level == "normal":
            if draw < background_weight:
                hour = rng.uniform(0, 24)
            else:
                component = int(rng.choice(len(component_names), p=day_weights))
                hour = rng.normal(centres[component], sigmas[component])
        else:
            if rush_component is None:
                rush_component = int(rng.integers(0, len(component_names)))
            if draw < 0.70:
                hour = rng.normal(centres[rush_component], rng.uniform(0.65, 1.15))
            elif draw < 0.90:
                component = int(rng.choice(len(component_names), p=day_weights))
                hour = rng.normal(centres[component], sigmas[component])
            else:
                hour = rng.uniform(0, 24)
        hours.append(float(hour % 24))

    profile = {
        "mode": {"quiet": "spread_out", "normal": "typical", "busy": "rush_hour"}[demand_level],
        "component_centres_ist": {
            name: round(float(centre % 24), 2) for name, centre in zip(component_names, centres)
        },
        "all_day_background": True,
    }
    if rush_component is not None:
        profile["rush_component"] = component_names[rush_component]
    return hours, profile


class SessionGenerator:
    def __init__(self, model_path=None):
        self.model = ConditionalVAE.load(model_path or ROOT / "model/chargesynth_cvae.npz")

    def demand(self, settings):
        """Create capacity-independent visits using isolated seeded random streams."""
        streams = [np.random.default_rng(seed) for seed in np.random.SeedSequence(settings.seed).spawn(7)]
        date_rng, model_rng, vehicle_rng, arrival_rng, station_rng, charger_rng, day_rng = streams
        day_types, chosen_dates = _day_types_and_dates(settings, date_rng, day_rng)
        charger_categories = _charger_categories(settings, charger_rng)
        learned, adjusted = self.model.sample(conditions(day_types, charger_categories), model_rng)
        vehicles = vehicle_rng.choice(
            ["Compact EV", "Sedan EV", "SUV EV"], size=settings.row_count, p=[0.35, 0.40, 0.25]
        )
        arrival_hours, arrival_profile = _arrival_hours(arrival_rng, day_types, settings.demand_level)
        station_ids, station_shares = _station_assignments(settings, station_rng)
        requests = []

        for index, (day_type, features, visit_date, vehicle, charger_key, station_id, hour) in enumerate(
            zip(day_types, learned, chosen_dates, vehicles, charger_categories, station_ids, arrival_hours)
        ):
            _legacy_hour, _legacy_queue, soc, gain, power_fraction, idle, exit_delay = features
            capacity = {"Compact EV": 40.0, "Sedan EV": 60.0, "SUV EV": 75.0}[vehicle]
            charger_name, charger_power = CHARGER_INFO[charger_key]
            soc_in = round(float(soc), 2)
            soc_out = round(min(100.0, soc_in + float(gain) * (100 - soc_in)), 2)
            energy = round(capacity * (soc_out - soc_in) / 100 / 0.90, 3)
            seconds = math.ceil(3600 * energy / (charger_power * float(power_fraction)))
            seconds_after_midnight = min(86399, round(hour * 3600))
            arrival = datetime.combine(visit_date, time(), tzinfo=IST) + timedelta(
                seconds=seconds_after_midnight
            )
            calendar_basis = (
                "hypothetical_special_day"
                if day_type in ("holiday", "festival")
                else "date_derived_weekday_weekend"
            )
            if settings.scenario == "mixed" and (
                (day_type == "weekday" and visit_date.weekday() >= 5)
                or (day_type == "weekend" and visit_date.weekday() < 5)
            ):
                calendar_basis = "hypothetical_mixed_day"
            requests.append(
                {
                    "session_id": f"EV-{settings.seed:04d}-{index + 1:05d}",
                    "station_id": station_id,
                    "day_type": day_type,
                    "day_of_week": visit_date.strftime("%A"),
                    "calendar_basis": calendar_basis,
                    "arrival_time": arrival.isoformat(),
                    "vehicle_type": str(vehicle),
                    "charger_type": charger_name,
                    "charger_power_kw": charger_power,
                    "average_power_kw": round(energy * 3600 / seconds, 4),
                    "battery_capacity_kwh": capacity,
                    "soc_in": soc_in,
                    "soc_out": soc_out,
                    "charging_efficiency": 0.90,
                    "kwh_consumed": energy,
                    "_seconds": seconds,
                    "_idle": round(float(idle) * 60),
                    "_exit": round(float(exit_delay) * 60),
                    "source": "synthetic_learned_demand_capacity_queue",
                }
            )
        metadata = {
            "station_demand_shares": station_shares,
            "arrival_profile": arrival_profile,
            "model_adjusted_rows": int(adjusted),
        }
        return requests, metadata

    def generate(self, settings):
        demand, metadata = self.demand(settings)
        capacities = {
            f"ST-{index + 1:02d}": settings.plugs_per_station for index in range(settings.station_count)
        }
        rows = schedule(demand, capacities)
        validation = validate_rows(rows)
        if validation["invalid_rows"]:
            raise RuntimeError("Generated records failed validation. Export was stopped.")
        summary = summarize(rows, settings, capacities, metadata["station_demand_shares"])
        summary_validation = validate_summary(rows, summary, capacities)
        validation["summary_errors"] = summary_validation["errors"]
        if not summary_validation["valid"]:
            raise RuntimeError("Generated summary did not match its session rows. Export was stopped.")
        charger_mix = {
            CHARGER_INFO[key][0]: int(probability * 100)
            for key, probability in MIXED_CHARGER_PROBABILITIES.items()
        }
        return {
            "rows": rows,
            "summary": summary,
            "validation": validation,
            "settings": asdict(settings),
            "simulation_assumptions": {
                "mixed_charger_probabilities_percent": charger_mix,
                "mixed_charger_note": "Configurable simulation assumptions; not universal real-world usage.",
                "station_demand_shares_percent": metadata["station_demand_shares"],
                "arrival_profile": metadata["arrival_profile"],
            },
            "provenance": "Synthetic demand with a physical charging-plug queue simulation. Not observed traffic.",
            "calendar_note": "Holiday and festival labels describe hypothetical scenarios, not a verified calendar.",
        }


def summarize(rows, settings, capacities, demand_shares=None):
    hourly = [0] * 24
    hourly_energy = [0.0] * 24
    hourly_wait = [0.0] * 24
    energy_by_charger = {name: 0.0 for name, _power in CHARGER_INFO.values()}
    period_start = datetime.combine(date.fromisoformat(settings.start_date), time(), tzinfo=IST)
    period_end = period_start + timedelta(days=settings.days)
    occupied = Counter()
    station_rows = defaultdict(list)
    for row in rows:
        hour = datetime.fromisoformat(row["arrival_time"]).hour
        hourly[hour] += 1
        hourly_energy[hour] += row["kwh_consumed"]
        hourly_wait[hour] += row["queue_wait_minutes"]
        energy_by_charger[row["charger_type"]] += row["kwh_consumed"]
        station_rows[row["station_id"]].append(row)
        plug_in = datetime.fromisoformat(row["plug_in_time"])
        plug_out = datetime.fromisoformat(row["plug_out_time"])
        occupied[row["station_id"]] += max(
            0, (min(plug_out, period_end) - max(plug_in, period_start)).total_seconds()
        )

    total_rows = len(rows)
    total_plugs = sum(capacities.values())
    span_seconds = settings.days * 86400
    if demand_shares is None:
        counts = [len(station_rows[station]) for station in capacities]
        weights = counts if sum(counts) else [1] * len(counts)
        demand_shares = _rounded_percentages(list(capacities), weights)
    stations = []
    for station, plugs in capacities.items():
        subset = station_rows[station]
        waited = sum(row["queue_wait_minutes"] > 0 for row in subset)
        stations.append(
            {
                "station_id": station,
                "plugs": plugs,
                "sessions": len(subset),
                "demand_share_percent": demand_shares.get(station, 0.0),
                "average_wait_minutes": round(
                    sum(row["queue_wait_minutes"] for row in subset) / max(1, len(subset)), 1
                ),
                "max_wait_minutes": round(
                    max((row["queue_wait_minutes"] for row in subset), default=0), 1
                ),
                "waiting_sessions": waited,
                "waiting_percent": round(100 * waited / max(1, len(subset)), 1),
                "occupied_percent": round(
                    100 * occupied[station] / (plugs * span_seconds), 1
                ),
            }
        )

    energy = sum(row["kwh_consumed"] for row in rows)
    waiting = sum(row["queue_wait_minutes"] > 0 for row in rows)
    return {
        "sessions": total_rows,
        "total_energy_kwh": round(energy, 2),
        "average_energy_kwh": round(energy / max(total_rows, 1), 2),
        "average_duration_minutes": round(
            sum(row["duration_minutes"] for row in rows) / max(total_rows, 1), 1
        ),
        "average_wait_minutes": round(
            sum(row["queue_wait_minutes"] for row in rows) / max(total_rows, 1), 1
        ),
        "max_wait_minutes": round(max((row["queue_wait_minutes"] for row in rows), default=0), 1),
        "waiting_sessions": waiting,
        "waiting_percent": round(100 * waiting / max(total_rows, 1), 1),
        "total_plugs": total_plugs,
        "occupied_percent": round(
            100 * sum(occupied.values()) / (max(1, total_plugs) * span_seconds), 1
        ),
        "sessions_finishing_after_window": sum(
            datetime.fromisoformat(row["plug_out_time"]) > period_end for row in rows
        ),
        "peak_arrival_hour": max(range(24), key=lambda hour: hourly[hour]),
        "arrivals_by_hour": hourly,
        "energy_by_arrival_hour": [round(value, 2) for value in hourly_energy],
        "wait_by_arrival_hour": [
            round(hourly_wait[hour] / max(hourly[hour], 1), 1) for hour in range(24)
        ],
        "energy_by_charger": {key: round(value, 2) for key, value in energy_by_charger.items()},
        "day_type_counts": dict(Counter(row["day_type"] for row in rows)),
        "station_counts": dict(Counter(row["station_id"] for row in rows)),
        "station_demand_shares": dict(demand_shares),
        "stations": stations,
        "eligible_days": len(settings.dates()),
        "calendar_days": settings.days,
    }


def to_csv(rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()
