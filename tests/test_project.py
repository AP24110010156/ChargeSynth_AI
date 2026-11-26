"""Observable behavior checks for ChargeSynth AI's professional release."""

import csv
import io
import json
import math
import re
from collections import Counter
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
import sys

import numpy as np
import pytest
import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import create_app
from backend.generator import (
    CHARGER_INFO,
    MIXED_CHARGER_PROBABILITIES,
    SCENARIOS,
    SessionGenerator,
    Settings,
)
from backend.planning import PlanningSettings, assess
from backend.scheduler import schedule
from backend.validation import FIELDS, validate_rows, validate_summary
from backend import assistant
from model.vae import ConditionalVAE, conditions


DAY_TYPES = {"weekday", "weekend", "holiday", "festival"}
CHARGER_LABELS = {"AC 7 kW", "AC 22 kW", "DC 60 kW"}
CHARGER_POWER = {label: power for label, power in CHARGER_INFO.values()}
REQUIRED_FIELDS = [
    "session_id", "station_id", "plug_id", "day_type", "day_of_week", "calendar_basis",
    "arrival_time", "plug_in_time", "start_time", "end_time", "plug_out_time", "exit_time",
    "duration_minutes", "connected_minutes", "queue_wait_minutes", "kwh_consumed",
    "vehicle_type", "charger_type", "charger_power_kw", "average_power_kw",
    "battery_capacity_kwh", "soc_in", "soc_out", "charging_efficiency", "source",
]


@pytest.fixture(scope="module")
def generator():
    return SessionGenerator()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    return create_app({"TESTING": True}).test_client()


def _waits(rows):
    return {row["session_id"]: row["queue_wait_minutes"] for row in rows}


def _peak_period(hour):
    if hour < 5 or hour >= 22:
        return "overnight"
    if hour <= 10:
        return "morning"
    if hour <= 16:
        return "afternoon"
    return "evening"


def _select_values(markup, select_id):
    match = re.search(
        rf'<select\s+id="{re.escape(select_id)}"[^>]*>(.*?)</select>', markup, re.S
    )
    assert match, f"Missing select #{select_id}"
    return re.findall(r'<option\s+value="([^"]+)"', match.group(1))


def _frontend_text(relative):
    return (ROOT / "frontend" / relative).read_text(encoding="utf-8")


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("charger", ["mixed", "ac7", "ac22", "dc60"])
def test_all_day_and_charger_modes_produce_complete_valid_rows(generator, scenario, charger):
    settings = Settings(
        row_count=80,
        days=7,
        start_date="2026-11-16",
        scenario=scenario,
        charger_type=charger,
    )
    result = generator.generate(settings)
    rows = result["rows"]
    assert len(rows) == 80
    assert result["validation"]["invalid_rows"] == 0
    assert result["validation"]["summary_errors"] == []
    assert all(set(row) == set(FIELDS) for row in rows)
    assert all(all(row[field] != "" and row[field] is not None for field in FIELDS) for row in rows)

    for row in rows:
        arrival = datetime.fromisoformat(row["arrival_time"])
        assert arrival.tzinfo is not None and arrival.utcoffset() is not None
        assert row["day_type"] in DAY_TYPES
        assert row["charger_type"] in CHARGER_LABELS
        assert row["charger_power_kw"] == CHARGER_POWER[row["charger_type"]]
        if scenario == "calendar":
            expected = "weekend" if arrival.weekday() >= 5 else "weekday"
            assert row["day_type"] == expected
        elif scenario == "weekday":
            assert row["day_type"] == "weekday" and arrival.weekday() < 5
        elif scenario == "weekend":
            assert row["day_type"] == "weekend" and arrival.weekday() >= 5
        elif scenario in {"holiday", "festival"}:
            assert row["day_type"] == scenario

    if scenario == "mixed":
        assert {row["day_type"] for row in rows} == DAY_TYPES
    if charger == "mixed":
        assert {row["charger_type"] for row in rows} == CHARGER_LABELS
    else:
        assert {row["charger_type"] for row in rows} == {CHARGER_INFO[charger][0]}


def test_calendar_days_and_mixed_scenario_are_distinct_and_honest(generator):
    base = Settings(row_count=400, days=14, start_date="2026-11-16", charger_type="dc60")
    calendar = generator.generate(replace(base, scenario="calendar"))
    mixed = generator.generate(replace(base, scenario="mixed"))

    assert set(calendar["summary"]["day_type_counts"]) == {"weekday", "weekend"}
    assert set(mixed["summary"]["day_type_counts"]) == DAY_TYPES
    assert "not a verified calendar" in mixed["calendar_note"].lower()
    for row in calendar["rows"]:
        arrival = datetime.fromisoformat(row["arrival_time"])
        assert row["day_type"] == ("weekend" if arrival.weekday() >= 5 else "weekday")
    assert all(
        row["calendar_basis"].startswith("hypothetical")
        for row in mixed["rows"]
        if row["day_type"] in {"holiday", "festival"}
    )


def test_mixed_charger_probabilities_and_session_power(generator):
    assert set(MIXED_CHARGER_PROBABILITIES) == {"ac7", "ac22", "dc60"}
    assert math.isclose(sum(MIXED_CHARGER_PROBABILITIES.values()), 1.0, abs_tol=1e-12)
    assert MIXED_CHARGER_PROBABILITIES == {"ac7": 0.40, "ac22": 0.30, "dc60": 0.30}

    result = generator.generate(Settings(row_count=900, charger_type="mixed", seed=31415))
    rows = result["rows"]
    assert {row["charger_type"] for row in rows} == CHARGER_LABELS
    assert all(row["charger_power_kw"] == CHARGER_POWER[row["charger_type"]] for row in rows)
    assumptions = result["simulation_assumptions"]["mixed_charger_probabilities_percent"]
    assert sum(assumptions.values()) == 100
    assert assumptions == {"AC 7 kW": 40, "AC 22 kW": 30, "DC 60 kW": 30}
    assert "not universal" in result["simulation_assumptions"]["mixed_charger_note"].lower()


def test_every_arrival_hour_is_possible_across_seeded_samples(generator):
    observed = set()
    for seed in range(20):
        demand, _metadata = generator.demand(
            Settings(row_count=240, scenario="mixed", charger_type="mixed", seed=seed)
        )
        observed.update(datetime.fromisoformat(row["arrival_time"]).hour for row in demand)
    assert observed == set(range(24))


def test_rush_peak_is_not_permanently_fixed(generator):
    peak_hours = set()
    peak_periods = set()
    reported_components = set()
    for seed in range(48):
        demand, metadata = generator.demand(
            Settings(
                row_count=280,
                scenario="mixed",
                charger_type="dc60",
                demand_level="busy",
                seed=seed,
            )
        )
        hourly = Counter(datetime.fromisoformat(row["arrival_time"]).hour for row in demand)
        peak = max(range(24), key=lambda hour: hourly[hour])
        peak_hours.add(peak)
        peak_periods.add(_peak_period(peak))
        reported_components.add(metadata["arrival_profile"]["rush_component"])

    assert len(peak_hours) >= 8
    assert peak_periods == {"morning", "afternoon", "evening", "overnight"}
    assert reported_components == {"morning", "afternoon", "evening", "overnight"}


def test_seed_repeats_and_new_seed_changes_the_sample(generator):
    settings = Settings(row_count=160, scenario="mixed", charger_type="mixed", seed=77)
    first = generator.generate(settings)
    repeated = generator.generate(settings)
    changed = generator.generate(replace(settings, seed=78))
    assert first == repeated
    assert first["rows"] != changed["rows"]
    assert first["simulation_assumptions"] != changed["simulation_assumptions"]


def test_queue_uses_unplug_time_and_fcfs_without_a_wait_multiplier(generator):
    demand, _metadata = generator.demand(
        Settings(row_count=3, station_count=1, charger_type="dc60", seed=5)
    )
    arrival = demand[0]["arrival_time"]
    controlled = [
        {
            **demand[0],
            "session_id": f"QUEUE-{index}",
            "station_id": "ST-01",
            "arrival_time": arrival,
            "_seconds": 600,
            "_idle": 300,
            "_exit": 120,
        }
        for index in range(3)
    ]
    rows = schedule(controlled, {"ST-01": 1})
    assert [row["queue_wait_minutes"] for row in rows] == [0, 15, 30]
    assert rows[0]["plug_out_time"] == rows[1]["plug_in_time"]
    assert rows[1]["plug_out_time"] == rows[2]["plug_in_time"]
    assert datetime.fromisoformat(rows[1]["plug_in_time"]) < datetime.fromisoformat(rows[0]["exit_time"])


def test_more_capacity_never_increases_individual_wait_for_fixed_assignment(generator):
    demand, _metadata = generator.demand(
        Settings(
            row_count=220,
            station_count=1,
            scenario="mixed",
            charger_type="mixed",
            demand_level="busy",
            seed=101,
        )
    )
    scheduled = {}
    for plugs in (1, 4, 12, 30):
        rows = schedule(demand, {"ST-01": plugs})
        scheduled[plugs] = _waits(rows)
        assert validate_rows(rows)["invalid_rows"] == 0
        assert len({row["plug_id"] for row in rows}) <= plugs
    for lower, higher in zip((1, 4, 12), (4, 12, 30)):
        assert all(scheduled[higher][session] <= wait for session, wait in scheduled[lower].items())

    # Adding an unused station cannot perturb visits whose station assignment is held fixed.
    original = schedule(demand, {"ST-01": 4})
    extra_station = schedule(demand, {"ST-01": 4, "ST-02": 4})
    assert _waits(extra_station) == _waits(original)


def test_busy_overload_has_significant_physical_wait_but_no_forced_minimum(generator):
    settings = Settings(
        row_count=200,
        station_count=1,
        plugs_per_station=6,
        days=1,
        scenario="mixed",
        charger_type="dc60",
        demand_level="busy",
        seed=42,
    )
    overloaded = generator.generate(settings)
    higher_capacity = generator.generate(replace(settings, plugs_per_station=24))
    summary = overloaded["summary"]
    waits = [row["queue_wait_minutes"] for row in overloaded["rows"]]

    assert summary["average_wait_minutes"] >= 20
    assert summary["max_wait_minutes"] >= 60
    assert 0 < summary["waiting_percent"] <= 100
    assert 0 in waits
    assert len({wait for wait in waits if wait > 0}) > 5
    assert higher_capacity["summary"]["average_wait_minutes"] < summary["average_wait_minutes"]
    assert overloaded["summary"]["total_energy_kwh"] == higher_capacity["summary"]["total_energy_kwh"]
    assert overloaded["summary"]["average_duration_minutes"] == higher_capacity["summary"]["average_duration_minutes"]
    low = _waits(overloaded["rows"])
    high = _waits(higher_capacity["rows"])
    assert all(high[session] <= wait for session, wait in low.items())


def test_sparse_demand_can_legitimately_have_zero_wait(generator):
    result = generator.generate(
        Settings(row_count=1, station_count=12, plugs_per_station=20, seed=9)
    )
    assert result["summary"]["average_wait_minutes"] == 0
    assert result["summary"]["max_wait_minutes"] == 0
    assert result["summary"]["waiting_percent"] == 0
    assert result["rows"][0]["queue_wait_minutes"] == 0


def test_station_shares_and_per_station_metrics_match_rows(generator):
    result = generator.generate(
        Settings(row_count=800, station_count=5, plugs_per_station=7, scenario="mixed", seed=2026)
    )
    summary = result["summary"]
    shares = summary["station_demand_shares"]
    expected_ids = {f"ST-{index:02d}" for index in range(1, 6)}

    assert set(shares) == expected_ids
    assert math.isclose(sum(shares.values()), 100.0, abs_tol=1e-9)
    assert len(set(shares.values())) > 1
    assert result["simulation_assumptions"]["station_demand_shares_percent"] == shares
    assert set(summary["station_counts"]) == expected_ids

    for station in summary["stations"]:
        subset = [row for row in result["rows"] if row["station_id"] == station["station_id"]]
        waited = sum(row["queue_wait_minutes"] > 0 for row in subset)
        assert station["station_id"] in expected_ids
        assert station["plugs"] == 7
        assert station["sessions"] == len(subset) == summary["station_counts"][station["station_id"]]
        assert station["demand_share_percent"] == shares[station["station_id"]]
        assert station["average_wait_minutes"] == round(
            sum(row["queue_wait_minutes"] for row in subset) / len(subset), 1
        )
        assert station["max_wait_minutes"] == round(
            max(row["queue_wait_minutes"] for row in subset), 1
        )
        assert station["waiting_sessions"] == waited
        assert station["waiting_percent"] == round(100 * waited / len(subset), 1)
        assert 0 <= station["occupied_percent"] <= 100


def test_summary_totals_match_dataset_rows(generator):
    settings = Settings(
        row_count=350,
        station_count=3,
        plugs_per_station=2,
        scenario="mixed",
        charger_type="mixed",
        demand_level="busy",
        seed=12,
    )
    result = generator.generate(settings)
    rows, summary = result["rows"], result["summary"]
    capacities = {f"ST-{index:02d}": 2 for index in range(1, 4)}

    assert FIELDS == REQUIRED_FIELDS
    assert summary["sessions"] == len(rows) == 350
    assert sum(summary["arrivals_by_hour"]) == 350
    assert len(summary["arrivals_by_hour"]) == 24
    assert len(summary["energy_by_arrival_hour"]) == 24
    assert len(summary["wait_by_arrival_hour"]) == 24
    assert sum(summary["station_counts"].values()) == 350
    assert abs(sum(summary["energy_by_arrival_hour"]) - summary["total_energy_kwh"]) <= 0.13
    assert summary["waiting_sessions"] == sum(row["queue_wait_minutes"] > 0 for row in rows)
    assert summary["max_wait_minutes"] == round(max(row["queue_wait_minutes"] for row in rows), 1)
    assert summary["total_plugs"] == 6
    assert 0 <= summary["occupied_percent"] <= 100
    assert validate_summary(rows, summary, capacities) == {"valid": True, "errors": []}


def test_validator_detects_overlapping_plug_use(generator):
    rows = generator.generate(
        Settings(row_count=2, station_count=1, plugs_per_station=2, seed=6)
    )["rows"]
    rows[1] = {**rows[0], "session_id": "ANOTHER-SESSION"}
    validation = validate_rows(rows)
    assert validation["invalid_rows"] > 0
    assert "port_overlap" in validation["errors"]


@pytest.mark.parametrize(
    "value",
    [
        {"row_count": 0}, {"row_count": 5001}, {"station_count": 0},
        {"plugs_per_station": 0}, {"plugs_per_station": 41}, {"days": 1.2},
        {"seed": True}, {"seed": float("nan")}, {"scenario": []},
        {"scenario": "ordinary"}, {"charger_type": "ultra"},
        {"start_date": "yesterday"}, {"unknown": 3},
    ],
)
def test_invalid_generation_settings_are_rejected(value):
    with pytest.raises(ValueError):
        Settings.parse(value)


def test_no_weekend_in_selected_range_is_rejected():
    with pytest.raises(ValueError):
        Settings(start_date="2026-11-16", scenario="weekend", days=1).dates()


def test_every_generated_station_can_be_the_planning_reference(generator):
    result = generator.generate(
        Settings(row_count=300, station_count=4, plugs_per_station=8, seed=44)
    )
    station_ids = [station["station_id"] for station in result["summary"]["stations"]]
    assert station_ids == ["ST-01", "ST-02", "ST-03", "ST-04"]

    for station_id in station_ids:
        plan = PlanningSettings(
            reference_station=station_id,
            growth_percent=30,
            diversion_percent=40,
        )
        assessment = assess(generator, result, plan)
        source_visits = result["summary"]["station_counts"][station_id]
        expected_future = math.ceil(source_visits * 1.30)
        assert assessment["reference_station"] == station_id
        assert assessment["assumptions"]["reference_station"] == station_id
        assert assessment["baseline_source_sessions"] == source_visits
        assert assessment["future_sessions"] == expected_future
        assert assessment["baseline"]["sessions"] == expected_future
        assert station_id in assessment["explanation"]
        assert any(station_id in note for note in assessment["notes"])


def test_unknown_reference_station_is_rejected(generator):
    result = generator.generate(Settings(row_count=80, station_count=2, seed=17))
    with pytest.raises(ValueError, match="ST-99"):
        assess(generator, result, PlanningSettings(reference_station="ST-99"))


def test_planner_reuses_one_future_cohort_for_every_option(generator):
    result = generator.generate(
        Settings(row_count=260, station_count=3, plugs_per_station=7, seed=64)
    )
    assessment = assess(
        generator,
        result,
        PlanningSettings(
            reference_station="ST-02",
            growth_percent=35,
            diversion_percent=40,
            candidate_plugs=6,
            additional_plugs=4,
        ),
    )
    baseline, expanded, new_site = (
        assessment["baseline"], assessment["expanded"], assessment["new_site"]
    )
    assert baseline["sessions"] == expanded["sessions"] == new_site["sessions"] == assessment["future_sessions"]
    assert baseline["total_energy_kwh"] == expanded["total_energy_kwh"] == new_site["total_energy_kwh"]
    assert baseline["average_duration_minutes"] == expanded["average_duration_minutes"] == new_site["average_duration_minutes"]
    assert baseline["arrivals_by_hour"] == expanded["arrivals_by_hour"] == new_site["arrivals_by_hour"]
    assert expanded["average_wait_minutes"] <= baseline["average_wait_minutes"]
    assert new_site["station_counts"]["NEW-01"] == assessment["candidate_sessions"]
    assert assessment["candidate"]["station_id"] == "NEW-01"
    for field in ("average_wait_minutes", "max_wait_minutes", "waiting_percent", "occupied_percent"):
        assert field in assessment["candidate"]


def test_distance_alone_does_not_create_or_remove_demand(generator):
    result = generator.generate(Settings(row_count=180, station_count=3, seed=88))
    common = dict(reference_station="ST-03", growth_percent=25, diversion_percent=37)
    near = assess(generator, result, PlanningSettings(distance_km=1, **common))
    far = assess(generator, result, PlanningSettings(distance_km=200, **common))

    assert near["assumptions"]["distance_km"] == 1
    assert far["assumptions"]["distance_km"] == 200
    for key in ("baseline_source_sessions", "future_sessions", "candidate_sessions"):
        assert near[key] == far[key]
    for key in ("baseline", "expanded", "new_site", "candidate"):
        assert near[key] == far[key]


def test_another_operator_disables_reference_station_expansion(generator):
    result = generator.generate(Settings(row_count=150, station_count=3, seed=91))
    assessment = assess(
        generator,
        result,
        PlanningSettings(reference_station="ST-02", existing_owner="another_operator"),
    )
    assert assessment["reference_station"] == "ST-02"
    assert assessment["expanded"] is None
    assert assessment["new_site"] is not None
    assert "another operator" in (assessment["explanation"] + " " + " ".join(assessment["notes"])).lower()


def test_home_generation_and_200_row_csv_export(client):
    home = client.get("/")
    assert home.status_code == 200
    response = client.post("/api/generate", json={"row_count": 200})
    assert response.status_code == 200
    result = response.get_json()
    assert len(result["rows"]) == 200
    assert result["validation"]["invalid_rows"] == 0

    download = client.get(result["download_url"])
    assert download.status_code == 200
    rows = list(csv.DictReader(io.StringIO(download.data.decode("utf-8-sig"))))
    assert len(rows) == 200
    assert list(rows[0]) == FIELDS == REQUIRED_FIELDS
    assert all(value != "" for row in rows for value in row.values())
    assert "attachment" in download.headers["Content-Disposition"]
    assert download.headers["Content-Type"].startswith("text/csv")


def test_5000_row_generation_and_export(client):
    response = client.post(
        "/api/generate",
        json={
            "row_count": 5000,
            "days": 30,
            "station_count": 12,
            "scenario": "mixed",
            "charger_type": "mixed",
        },
    )
    assert response.status_code == 200
    result = response.get_json()
    assert len(result["rows"]) == 5000
    assert result["validation"]["invalid_rows"] == 0
    assert result["validation"]["summary_errors"] == []
    download = client.get(result["download_url"])
    assert download.status_code == 200
    assert len(list(csv.DictReader(io.StringIO(download.data.decode("utf-8-sig"))))) == 5000


def test_assess_api_uses_selected_reference_station(client):
    generated = client.post(
        "/api/generate", json={"row_count": 240, "station_count": 4, "seed": 33}
    ).get_json()
    response = client.post(
        "/api/assess",
        json={
            "run_id": generated["run_id"],
            "planning": {"reference_station": "ST-03", "growth_percent": 20},
        },
    )
    assert response.status_code == 200
    assessment = response.get_json()
    assert assessment["reference_station"] == "ST-03"
    assert assessment["baseline_source_sessions"] == generated["summary"]["station_counts"]["ST-03"]


def test_json_origin_input_bounds_and_removed_private_routes(client):
    assert client.post("/api/generate", data="x").status_code == 415
    assert client.post(
        "/api/generate", json={}, headers={"Origin": "https://elsewhere.example"}
    ).status_code == 403
    assert client.post("/api/generate", json={"row_count": 5001}).status_code == 400
    assert client.get("/api/model").status_code == 404
    assert client.post("/api/groq/check", json={}).status_code == 404


def test_private_configuration_and_provider_details_are_not_in_browser_responses(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "a-private-sentinel")
    home = client.get("/").get_data(as_text=True)
    status = client.get("/api/status")
    content = (home + status.get_data(as_text=True)).lower()
    forbidden = (
        "a-private-sentinel", "groq", "openai", "api key", "vae", "model quality",
        "trained model", "local workspace", "local model ready", "pause motion",
        "resume motion", "about this project",
    )
    assert all(term not in content for term in forbidden)
    assert status.status_code == 200
    assert set(status.get_json()) == {"default_settings", "default_planning"}
    assert status.get_json()["default_settings"]["scenario"] == "calendar"
    assert status.get_json()["default_settings"]["charger_type"] == "mixed"
    assert status.get_json()["default_planning"]["reference_station"] == "ST-01"


def test_frontend_exposes_requested_controls_and_reference_metrics(client):
    markup = client.get("/").get_data(as_text=True)
    assert _select_values(markup, "scenario") == [
        "calendar", "mixed", "weekday", "weekend", "holiday", "festival"
    ]
    assert _select_values(markup, "chargerType") == ["mixed", "ac7", "ac22", "dc60"]
    assert _select_values(markup, "existingOwner") == ["our_network", "another_operator"]
    assert 'id="referenceStation"' in markup
    assert 'id="distanceKm" type="number" min="1" max="200"' in markup
    for element_id in (
        "referenceVisits", "referencePlugs", "referenceAverageWait", "referenceMaximumWait",
        "referenceWaitingPercent", "referenceOccupancy", "searchRows", "prevPage", "nextPage",
        "sessionRows", "rowDialog", "recordDetails", "downloadButton",
    ):
        assert f'id="{element_id}"' in markup
    assert "00:00–23:59" in markup
    assert "VEHICLE ARRIVALS (COUNT)" in markup
    assert "ENERGY" in markup and "kWh" in markup


def test_frontend_wires_navigation_reference_search_pagination_details_and_download(client):
    markup = client.get("/").get_data(as_text=True)
    app_js = client.get("/static/js/app.js").get_data(as_text=True)
    assert client.get("/static/js/app.js").status_code == 200
    for section in ("workspace", "planning", "dataset"):
        assert f'data-section="{section}"' in markup
        assert f'href="#{section}"' in markup
    assert "function updateReferenceStations" in app_js
    assert "(run.summary.stations||[]).map" in app_js
    assert "select.replaceChildren" in app_js
    assert "ids.includes(preferred)?preferred:ids[0]" in app_js
    assert "referenceStation').addEventListener('change'" in app_js
    assert "additionalPlugs').disabled=competitor" in app_js
    assert "searchRows').addEventListener('input'" in app_js
    assert "prevPage').addEventListener('click'" in app_js
    assert "nextPage').addEventListener('click'" in app_js
    assert "open.addEventListener('click',()=>showRow(row))" in app_js
    assert "rowDialog').showModal()" in app_js
    assert "window.location.assign(run.download_url)" in app_js
    assert all(key in app_js for key in ("ArrowLeft", "ArrowRight", "Home", "End"))


def test_reference_dropdown_is_populated_from_every_generated_station_contract(client):
    generated = client.post(
        "/api/generate", json={"row_count": 180, "station_count": 6, "seed": 71}
    ).get_json()
    station_ids = [station["station_id"] for station in generated["summary"]["stations"]]
    assert station_ids == [f"ST-{index:02d}" for index in range(1, 7)]
    app_js = _frontend_text("static/js/app.js")
    assert "const ids=(run.summary.stations||[]).map(item=>item.station_id)" in app_js
    assert "ids.includes(preferred)?preferred:ids[0]" in app_js
    assert "Reference changed to ${selected}" in app_js


def test_hero_scene_is_theme_matched_3d_local_and_honors_motion_preferences(client):
    markup = client.get("/").get_data(as_text=True).lower()
    scene = client.get("/static/js/scene.js").get_data(as_text=True)
    asset = client.get("/static/assets/hero-ev-charger.png")
    lower_scene = scene.lower()
    assert client.get("/static/js/scene.js").status_code == 200
    assert "theme-matched three-dimensional electric car" in markup
    assert asset.status_code == 200 and asset.data.startswith(b"\x89PNG\r\n\x1a\n")
    assert "hero-ev-charger.png" in scene
    assert "new Image" in scene and "drawImage" in scene and "drawEnergyLines" in scene
    assert "prefers-reduced-motion: reduce" in scene
    assert "IntersectionObserver" in scene and "isIntersecting" in scene
    assert "requestAnimationFrame" in scene and "cancelAnimationFrame" in scene
    assert "http://" not in lower_scene and "https://" not in lower_scene
    assert "drawcar" not in lower_scene and "drawstation" not in lower_scene
    assert "ctx.arc" not in scene and "particle" not in lower_scene
    assert "orbit" not in lower_scene and "electron" not in lower_scene


def test_responsive_styles_and_reduced_motion_rules_are_preserved(client):
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    css = re.sub(r"\s+", "", response.get_data(as_text=True))
    markup = client.get("/").get_data(as_text=True)
    assert 'name="viewport"' in markup
    assert "@media(max-width:1250px)" in css
    assert "@media(max-width:820px)" in css
    assert "@media(max-width:700px)" in css
    assert "@media(max-width:440px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert ".table-scroll{overflow:auto" in css


def test_guided_scenario_and_calculated_explanation_use_selected_station(client):
    status = client.get("/api/status").get_json()
    planning = status["default_planning"]
    planning["reference_station"] = "ST-02"
    plan = client.post(
        "/api/plan",
        json={
            "prompt": "A competitor station: plan a new station 30 km away with 6 plugs and 30% diversion.",
            "settings": {},
            "planning": planning,
        },
    )
    assert plan.status_code == 200
    proposal = plan.get_json()
    assert proposal["response_kind"] == "guided_template"
    assert proposal["planning"]["reference_station"] == "ST-02"
    assert proposal["planning"]["distance_km"] == 30
    assert proposal["planning"]["existing_owner"] == "another_operator"
    assert proposal["planning"]["diversion_percent"] == 30

    generated = client.post(
        "/api/generate", json={"row_count": 80, "station_count": 3, "seed": 54}
    ).get_json()
    explain = client.post(
        "/api/explain",
        json={"run_id": generated["run_id"], "planning": proposal["planning"]},
    )
    assert explain.status_code == 200
    result = explain.get_json()
    assert result["response_kind"] == "calculated_assessment"
    assert "30 km" in result["explanation"]
    assert "ST-02" in result["explanation"]
    assert result["assessment"]["reference_station"] == "ST-02"
    assert result["assessment"]["expanded"] is None


def test_external_assistant_plan_is_strictly_validated(monkeypatch):
    response = {
        "settings": asdict(Settings(row_count=321)),
        "planning": asdict(PlanningSettings(reference_station="ST-03", distance_km=28)),
        "explanation": "Compare ST-03 with a candidate 28 km farther along the road.",
    }
    monkeypatch.setattr(assistant, "complete", lambda *args, **kwargs: json.dumps(response))
    result = assistant.plan_scenario(
        "A new station", asdict(Settings()), asdict(PlanningSettings())
    )
    assert result["response_kind"] == "assistant"
    assert result["settings"]["row_count"] == 321
    assert result["planning"]["reference_station"] == "ST-03"
    response["settings"]["row_count"] = 999999
    result = assistant.plan_scenario(
        "A new station", asdict(Settings()), asdict(PlanningSettings())
    )
    assert result["response_kind"] == "guided_template"
    assert result["settings"]["row_count"] == 200


@pytest.mark.parametrize("failure", ["timeout", "http", "bad_json", "incomplete"])
def test_provider_failures_use_non_secret_fallback(monkeypatch, failure):
    monkeypatch.setenv("GROQ_API_KEY", "a-private-sentinel")

    class FakeResponse:
        def raise_for_status(self):
            if failure == "http":
                raise requests.HTTPError("sensitive diagnostics")

        def json(self):
            if failure == "bad_json":
                raise ValueError("sensitive diagnostics")
            return {
                "choices": [
                    {"finish_reason": "length", "message": {"content": "a-private-sentinel"}}
                ]
            }

    def post(*args, **kwargs):
        if failure == "timeout":
            raise requests.Timeout("sensitive diagnostics")
        assert kwargs["headers"]["Authorization"] == "Bearer a-private-sentinel"
        return FakeResponse()

    monkeypatch.setattr(requests, "post", post)
    result = assistant.plan_scenario(
        "New station 25 km away", asdict(Settings()), asdict(PlanningSettings())
    )
    assert result["response_kind"] == "guided_template"
    assert "sentinel" not in json.dumps(result)
    assert "diagnostics" not in json.dumps(result)


def test_assistant_payload_and_response(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "a-private-sentinel")
    payloads = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "ChargeSynth AI: compare the two sites."},
                    }
                ]
            }

    def post(url, **kwargs):
        payloads.append((url, kwargs))
        return Response()

    monkeypatch.setattr(requests, "post", post)
    assert assistant.complete("system", {"request": "scenario"}) == (
        "ChargeSynth AI: compare the two sites."
    )
    assert payloads[0][0].endswith("/chat/completions")
    assert payloads[0][1]["json"]["model"]
    assert "sentinel" not in json.dumps(payloads[0][1]["json"])


def test_vae_backprop_matches_finite_difference():
    model = ConditionalVAE(seed=7, hidden=6, latent=2)
    rng = np.random.default_rng(2)
    x = rng.normal(size=(3, 7))
    condition_matrix = conditions(
        ["weekday", "weekend", "festival"], ["ac7", "ac22", "dc60"]
    )
    epsilon = rng.normal(size=(3, 2))
    gradients = model.loss_and_grads(x, condition_matrix, epsilon)[3]
    for name in model.p:
        index = tuple(0 for _ in model.p[name].shape)
        value = model.p[name][index]
        delta = 1e-5
        model.p[name][index] = value + delta
        plus = model.loss_and_grads(x, condition_matrix, epsilon)[0]
        model.p[name][index] = value - delta
        minus = model.loss_and_grads(x, condition_matrix, epsilon)[0]
        model.p[name][index] = value
        assert np.isclose(
            (plus - minus) / (2 * delta),
            gradients[name][index],
            rtol=1e-4,
            atol=1e-5,
        ), name


def test_reorganized_production_paths_are_single_source():
    required = (
        "backend/app.py", "backend/generator.py", "backend/scheduler.py",
        "backend/planning.py", "backend/assistant.py", "backend/validation.py",
        "model/vae.py", "model/chargesynth_cvae.npz",
        "frontend/templates/index.html", "frontend/static/css/style.css",
        "frontend/static/js/app.js", "frontend/static/js/scene.js",
        "frontend/static/assets/favicon.svg", "frontend/static/assets/hero-ev-charger.png",
    )
    assert all((ROOT / relative).is_file() for relative in required)
    obsolete = ("app.py", "chargesynth", "models", "templates", "static")
    assert all(not (ROOT / relative).exists() for relative in obsolete)
    launcher = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "from backend.app import app" in launcher
    assert "from app import app" not in launcher


