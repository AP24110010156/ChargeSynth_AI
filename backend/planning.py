"""Compare station-capacity options using one common future demand cohort."""
import math
import re
from dataclasses import asdict, dataclass, replace

import numpy as np

from .generator import Settings, bounded_integer, schedule, summarize


@dataclass(frozen=True)
class PlanningSettings:
    reference_station: str = "ST-01"
    road_name: str = "My highway corridor"
    existing_owner: str = "our_network"
    distance_km: int = 25
    additional_plugs: int = 4
    candidate_plugs: int = 6
    growth_percent: int = 30
    diversion_percent: int = 40

    @classmethod
    def parse(cls, obj):
        if not isinstance(obj, dict):
            raise ValueError("Send planning assumptions as an object.")
        defaults = asdict(cls())
        if set(obj) - set(defaults):
            raise ValueError("Unknown planning assumption.")
        values = {**defaults, **obj}
        if not isinstance(values["reference_station"], str) or not re.fullmatch(
            r"ST-\d{2}", values["reference_station"]
        ):
            raise ValueError("Choose a reference station from the generated station locations.")
        if not isinstance(values["road_name"], str) or not 1 <= len(values["road_name"].strip()) <= 100:
            raise ValueError("Use a road name of 1 to 100 characters.")
        values["road_name"] = values["road_name"].strip()
        if values["existing_owner"] not in ("our_network", "another_operator"):
            raise ValueError("Choose who operates the reference station.")
        for name, low, high in (
            ("distance_km", 1, 200),
            ("additional_plugs", 1, 40),
            ("candidate_plugs", 1, 40),
            ("growth_percent", 0, 200),
            ("diversion_percent", 1, 99),
        ):
            values[name] = bounded_integer(values[name], name.replace("_", " "), low, high)
        return cls(**values)


def _find_reference(result, station_id):
    for station in result["summary"]["stations"]:
        if station["station_id"] == station_id:
            return station
    raise ValueError(
        f"{station_id} is not in this generated sample. Choose one of the displayed station locations."
    )


def assess(generator, result, plan):
    settings = Settings.parse(result["settings"])
    reference_station = plan.reference_station
    reference = _find_reference(result, reference_station)
    baseline_count = reference["sessions"]
    if not baseline_count:
        raise ValueError(
            f"{reference_station} has no visits in this sample. Generate more sessions before comparing this site."
        )

    future_count = math.ceil(baseline_count * (1 + plan.growth_percent / 100))
    future_settings = replace(
        settings,
        row_count=future_count,
        station_count=1,
        seed=(settings.seed + 7919) % 2147483647,
    )
    future_demand, _metadata = generator.demand(future_settings)
    future_demand = [{**row, "station_id": reference_station} for row in future_demand]
    reference_plugs = reference["plugs"]

    current_capacity = {reference_station: reference_plugs}
    baseline = summarize(
        schedule(future_demand, current_capacity),
        future_settings,
        current_capacity,
        {reference_station: 100.0},
    )

    own_station = plan.existing_owner == "our_network"
    expanded = None
    if own_station:
        expanded_capacity = {reference_station: reference_plugs + plan.additional_plugs}
        expanded = summarize(
            schedule(future_demand, expanded_capacity),
            future_settings,
            expanded_capacity,
            {reference_station: 100.0},
        )

    # The user-supplied distance is a label only. Route choice is the explicit
    # diversion assumption and does not add or remove a vehicle.
    rng = np.random.default_rng(settings.seed + 12345)
    count_diverted = math.floor(future_count * plan.diversion_percent / 100 + 0.5)
    selected = set(rng.permutation(future_count)[:count_diverted].tolist())
    routed = [
        {**row, "station_id": "NEW-01" if index in selected else reference_station}
        for index, row in enumerate(future_demand)
    ]
    new_capacity = {reference_station: reference_plugs, "NEW-01": plan.candidate_plugs}
    candidate_share = round(100 * count_diverted / future_count, 1)
    route_shares = {reference_station: round(100 - candidate_share, 1), "NEW-01": candidate_share}
    new_site = summarize(
        schedule(routed, new_capacity), future_settings, new_capacity, route_shares
    )
    candidate = next(
        station for station in new_site["stations"] if station["station_id"] == "NEW-01"
    )
    routed_reference = next(
        station for station in new_site["stations"] if station["station_id"] == reference_station
    )

    baseline_wait = baseline["average_wait_minutes"]
    expanded_wait = expanded["average_wait_minutes"] if expanded else math.inf
    candidate_scenario_wait = new_site["average_wait_minutes"]
    if baseline_wait <= 5:
        headline = "Capacity is comfortable in this scenario."
        decision = (
            "The simulated queue alone does not justify extra capacity. A new site would need evidence "
            "of a coverage gap or additional road traffic."
        )
    elif own_station and expanded_wait <= candidate_scenario_wait:
        headline = f"Test expansion at {reference_station} first."
        decision = (
            f"Adding {plan.additional_plugs} plugs at {reference_station} gives an average wait of "
            f"{expanded_wait:.1f} minutes, compared with {candidate_scenario_wait:.1f} minutes across "
            "both sites in the candidate scenario. This compares queues, not costs or profitability."
        )
    else:
        headline = "Investigate a second station along the corridor."
        decision = (
            f"A candidate {plan.distance_km} km from {reference_station} gives an average wait of "
            f"{candidate_scenario_wait:.1f} minutes across both sites under the assumed "
            f"{plan.diversion_percent}% shift in visits. "
            + (
                "Another operator's station is a demand reference only and is not an expansion option."
                if not own_station
                else "Compare this with the cost and accessibility of adding plugs at the reference station."
            )
        )
    if candidate_scenario_wait >= baseline_wait and baseline_wait > 5:
        decision += (
            " The candidate does not improve the overall queue in this sample; test another capacity "
            "or explicitly assumed demand split."
        )

    eligible_days = len(settings.dates())
    notes = [
        f"The selected reference is {reference_station}: {baseline_count} visits, {reference_plugs} plugs, "
        f"{reference['average_wait_minutes']:.1f} minutes average wait and "
        f"{reference['max_wait_minutes']:.1f} minutes maximum wait in the source sample.",
        f"Assumed growth of {plan.growth_percent}% produces {future_count} visits over "
        f"{eligible_days} eligible day(s). Every option reuses those exact vehicles and arrival times.",
        f"{count_diverted} visits move to NEW-01 ({plan.diversion_percent}% assumption, rounded). "
        "No additional road traffic is invented.",
        f"{plan.distance_km} km is a user-provided planning assumption. Distance does not create demand, "
        "prove suitability or establish an optimal location.",
        "A real deployment still requires actual road traffic, travel direction, nearby stations, grid "
        "capacity, land, road access, costs and permissions.",
    ]
    return {
        "assumptions": asdict(plan),
        "reference_station": reference_station,
        "reference": reference,
        "baseline_source_sessions": baseline_count,
        "future_sessions": future_count,
        "candidate_sessions": count_diverted,
        "candidate_sessions_per_day": round(count_diverted / eligible_days, 1),
        "reference_sessions_per_day": round(baseline_count / eligible_days, 1),
        "eligible_days": eligible_days,
        "baseline": baseline,
        "expanded": expanded,
        "new_site": new_site,
        "candidate": candidate,
        "candidate_site_queue": {
            "average_wait_minutes": candidate["average_wait_minutes"],
            "max_wait_minutes": candidate["max_wait_minutes"],
            "waiting_percent": candidate["waiting_percent"],
            "occupied_percent": candidate["occupied_percent"],
        },
        "routed_reference": routed_reference,
        "headline": headline,
        "explanation": decision,
        "notes": notes,
    }


def written_assessment(result, assessment):
    summary = result["summary"]
    plan = assessment["assumptions"]
    station_id = assessment["reference_station"]
    ownership = (
        "your selected station" if plan["existing_owner"] == "our_network" else "another operator's station"
    )
    return (
        f"ChargeSynth AI generated {summary['sessions']} visits across "
        f"{result['settings']['station_count']} location(s). For {plan['road_name']}, {station_id} is "
        f"{ownership} and contributes {assessment['baseline_source_sessions']} reference visits. "
        f"With {plan['growth_percent']}% assumed growth, the common future cohort contains "
        f"{assessment['future_sessions']} visits and its current-capacity average wait is "
        f"{assessment['baseline']['average_wait_minutes']:.1f} minutes. A candidate "
        f"{plan['distance_km']} km away receives {assessment['candidate_sessions']} of those same visits "
        f"under the {plan['diversion_percent']}% assumption; its own average wait is "
        f"{assessment['candidate']['average_wait_minutes']:.1f} minutes and maximum wait is "
        f"{assessment['candidate']['max_wait_minutes']:.1f} minutes. {assessment['explanation']} "
        "These are synthetic planning assumptions, not measured demand or a recommended real-world site."
    )
