# Verification — professional station-planning release

This document defines the release checks for ChargeSynth AI. The final Windows verification on 24 November 2026 completed **74 automated checks** covering generation, queue behavior, planning, privacy, exports, responsive wiring and reduced-motion support.

## Automated test command

From the extracted `ChargeSynth_AI` folder:

```powershell
py -3 -m pip install pytest
py -3 -m pytest -q
```

The project-root launcher must also work with the bundled environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe run.py
```

## Generation and validation checks

The automated suite exercises observable output and invariants, including:

- Calendar Days, Weekday, Weekend, Holiday, Festival and Mixed scenario behavior.
- A sufficiently large Mixed scenario contains multiple supported day types and labels every row explicitly.
- Holiday and festival provenance remains hypothetical rather than claiming a verified public calendar.
- Mixed chargers produces AC 7 kW, AC 22 kW and DC 60 kW sessions in a sufficiently large sample.
- The configurable mixed-charger probabilities equal 100% and default to 40% / 30% / 30%.
- Per-session charger power changes duration correctly and summaries aggregate mixed hardware.
- All 24 arrival hours are reachable across multiple seeded samples.
- Peak hours vary across morning, afternoon, evening and late-night/overnight possibilities rather than remaining fixed.
- Spread out, Typical and Rush hour retain their intended differences while permitting full-day arrivals.
- The same settings and seed reproduce identical rows; a changed seed changes the sample.
- Seeded station demand shares total 100% and reproduce consistently.
- Every generated station has a clear ID and each row has both `station_id` and `plug_id`.
- Every required CSV field is complete for 200-row and 5,000-row generation.
- Timestamps are timezone-aware and ordered correctly.
- Queue, active and connected durations match their timestamps.
- SOC, efficiency, battery energy and charging power remain internally consistent.
- Summary totals equal their source rows.

## Queue and capacity checks

Waiting must come only from physical capacity:

`charging start = max(arrival, earliest available plug time)`

Tests verify that:

- a plug remains unavailable until `plug_out_time`;
- no two vehicles overlap on the same plug;
- increasing plugs cannot increase any individual vehicle's wait when demand and assignment are held fixed;
- increasing station capacity cannot increase individual waits under the same fixed assignment;
- busy/overloaded examples produce meaningful capacity-based waiting without a hard-coded minimum or post-schedule multiplier;
- sparse demand with ample capacity may correctly produce zero waiting;
- legitimate severe overload is not capped and may finish outside the selected period; and
- overall and per-station average wait, maximum wait, waiting percentage, plug count, occupancy and spillover agree with the rows.

Do not use one exact average-wait number as proof of realism. A result depends on the selected visit count, dates, seeded peak, station shares, charger mix, plugs and connected time. The invariant is that changing capacity changes the physical schedule, while the vehicle cohort remains fixed for a fair comparison.

## Planning checks

The suite verifies that:

- the Reference station dropdown contains every station from the current generated sample;
- selecting a station other than `ST-01` changes source measures and all planning calculations to that station;
- regeneration preserves the selection when it still exists and selects the first valid station otherwise;
- an Our Network reference offers current capacity, add-plugs and candidate-site options;
- an Another operator reference is used only as a demand reference and does not offer expansion of that company's station;
- distance accepts values from 1 through 200 km;
- changing distance alone changes no source, future or candidate vehicle counts;
- every option reuses the exact same future vehicles and arrival times;
- candidate visits follow the explicit diversion assumption rather than distance;
- current, expansion and candidate output includes average/max wait, waiting percentage and occupancy;
- the candidate-site queue is separately visible; and
- the explanation names the selected reference and states the assumptions and real-world evidence still required.

## HTTP, CSV and privacy checks

Automated checks cover:

- default generation and CSV download;
- valid JSON and same-origin request handling;
- bounded input validation and safe errors;
- short-lived in-memory run-cache behavior;
- complete CSV headers and values;
- safe assistant response validation and calculated fallback behavior;
- no private credential, provider name, secret-entry control or private configuration in HTML or status responses; and
- no customer-facing model-quality/configuration screen, trained-model badge, Local Workspace, Local Model Ready, Pause Motion, Resume Motion or About This Project control.

The private `.env` file is never part of the final ZIP. Tests may use temporary values or mocks; they must not copy a real credential into fixtures, logs, screenshots or browser responses.

## Browser and interaction checklist

Run the app and check the following with a real browser:

- The initial page generates the default dataset without a console error.
- Sidebar navigation and breadcrumb state reach Session studio, Station planning and Session data.
- Existing dark charcoal colors, restrained green accents, typography, cards, table, profile icon and spacing remain unchanged.
- The local theme-matched 3D EV/charger asset fits the original hero area and contains no atomic/orbital object, bright neon glow or cartoon treatment.
- The animation becomes static under `prefers-reduced-motion`, stops outside the viewport and resumes safely when visible.
- Day Scenario exposes Calendar Days, Weekday, Weekend, Holiday, Festival and Mixed scenario.
- Charger Type exposes Mixed chargers, AC 7 kW, AC 22 kW and DC 60 kW.
- New Sample can produce morning, afternoon, evening and night peak examples.
- The arrival chart spans IST `00:00–23:59`; Arrivals and Energy axes state their units.
- Hover, click/tap and keyboard selection show the exact hour, visit count, energy and average wait.
- Overall and station-level queue/capacity values update after generation.
- Every generated station appears in the Reference station selector.
- Multiple reference stations update the route, cards, assumptions and explanation.
- Our Network and Another operator cases show only valid actions.
- Changing distance alone preserves future and candidate cohorts.
- Record details show all 25 fields and the correct station, plug and charger.
- Search, pagination and CSV download still work.
- No private configuration or provider information appears anywhere in the product interface.

## Responsive inspection

Inspect at representative desktop, tablet and phone widths. Confirm:

- no horizontal page overflow beyond the intentional table scroller;
- sidebar/mobile navigation remains usable;
- hero copy and the realistic EV/charger visual keep their established layout proportions;
- form controls and planning cards remain readable;
- chart bars remain selectable by touch and keyboard; and
- the record dialog, table toolbar and pagination remain accessible.

Reduced-motion mode must be checked separately from viewport size.

## Launcher and packaging checks

Before delivery:

1. Start with `start_windows.bat` from the project root.
2. Start manually with `python run.py`.
3. Confirm Flask finds `frontend/templates/` and `frontend/static/`.
4. Confirm training and tests load files from `model/` and `backend/`.
5. Confirm the updater recognizes the reorganized release and preserves `.env`, `.venv`, CSV exports and unrelated user files.
6. Confirm obsolete production paths such as root `app.py`, `templates/`, `static/`, `chargesynth/` and `models/` are not duplicated beside the new production folders.
7. Exclude `.env`, `.venv`, `__pycache__`, `.pytest_cache`, logs and temporary files from the package.
8. Inspect the ZIP file list for credentials and accidental duplicate production files.
9. Name the final archive `ChargeSynth_AI_Professional_Updated.zip`.
10. Extract that archive into a clean temporary folder and repeat the launcher, default-generation and CSV checks.

## Five-minute release smoke test

1. Generate the default dataset and inspect one session.
2. Generate Mixed scenario with Mixed chargers and confirm variety and complete fields.
3. use several New Sample runs to observe different possible peak periods, including overnight.
4. Compare a sparse case and a busy low-capacity case; confirm waits are schedule-derived.
5. Select at least two different reference stations and compare both ownership modes.
6. Change only candidate distance and confirm demand is unchanged.
7. Inspect chart values, search, pagination, details and the downloaded CSV.
8. Inspect desktop, tablet and phone layouts directly in the running application.

## Limits of verification

Passing software tests proves reproducibility, internal consistency, capacity behavior, interface wiring and privacy boundaries. It does not prove real traffic demand, forecasting accuracy, an optimal distance, commercial viability, electrical feasibility or regulatory approval.

Before a real deployment, obtain actual road traffic, travel direction, nearby-station usage, grid capacity, land, road access, costs and permissions. No synthetic result replaces that evidence.
