# ChargeSynth AI — beginner project guide

## What is this project?

ChargeSynth AI generates hypothetical EV charging visits so a student or planning team can explore demand patterns, physical queues and capacity options before using real operational data. Its full project name is **ChargeSynth AI — Synthetic EV Charging Session Generator and Station Planning Studio**.

Synthetic-data generation is the core project. Station planning adds two transparent what-if questions: “What if we add plugs at a selected station?” and “What if some future visits use a proposed station along the same corridor?” The application is an educational screening tool. It does not claim that a real station should be built at a particular location.

No dataset has to be typed before use. The application creates sessions, and the release includes example CSV files and trained model weights.

## What is learned and what is calculated?

A conditional variational autoencoder (CVAE), implemented in NumPy, supplies synthetic vehicle and session characteristics from simulated reference features. The bundled weights make retraining optional. Reference data is synthetic, so model fit is not proof of real-world forecasting accuracy.

Arrival timing is calibrated by a seeded 24-hour mixture layer. It can combine morning, afternoon, evening, late-night/overnight and background components. Component weights and peak centres vary within bounded ranges using the sample seed. This keeps results reproducible without fixing every dataset to the same daytime peak.

Queue waiting is **not** predicted by the model and is never added as cosmetic noise. The physical scheduler calculates it from arrivals, station assignment, plug capacity, charging duration and post-charge parking. Any legacy learned queue feature in old model artifacts is ignored.

ChargeSynth AI can also interpret a written scenario and explain the calculated comparison. This explanation does not perform the queue calculation, discover demand or optimize a road location. Private implementation and configuration details remain outside the customer interface.

## Day scenarios

The Day Scenario control separates ordinary calendar behavior from a deliberately mixed simulation:

- **Calendar Days:** uses the selected calendar dates and labels each visit as a weekday or weekend.
- **Weekday:** uses weekday dates only.
- **Weekend:** uses weekend dates only.
- **Holiday:** assigns a hypothetical-holiday scenario.
- **Festival:** assigns a hypothetical-festival scenario.
- **Mixed scenario:** creates a controlled, seeded combination of weekdays, weekends, hypothetical holidays and hypothetical festivals.

Every row contains its assigned `day_type`. Holiday and festival labels are simulation assumptions; they are not claims about verified national, state or local public holidays.

## Charger choices

Single-charger modes use AC 7 kW, AC 22 kW or DC 60 kW for all generated sessions. **Mixed chargers** chooses a port type independently for each session from one clearly named backend configuration object. The default assumptions are:

| Session charger | Default share |
|---|---:|
| AC 7 kW | 40% |
| AC 22 kW | 30% |
| DC 60 kW | 30% |
| **Total** | **100%** |

The distribution is editable and validated to total 100%. It is a configurable simulation assumption, not a universal measure of charging behavior. An EV session uses an AC or DC port; the project does not invent separate “AC cars” and “DC cars.” Charger rating affects the maximum and average power, active duration, connected time and therefore plug availability.

## How generation works, step by step

1. The user chooses visit count, station locations, plugs per location, dates, day scenario, charger mode and arrival pattern.
2. Independent random streams are derived from one hidden seed. This makes rows reproducible while keeping arrival, vehicle, charger and station choices logically separate.
3. Day types and per-session chargers are assigned from the selected scenario and validated assumptions.
4. The model and numerical rules create internally consistent battery, energy, charging-power, parking and exit features.
5. A configurable 24-hour mixture creates arrival times. **Spread out** uses broad components and background demand. **Typical** combines several possible peaks with background demand. **Rush hour** concentrates demand around a seeded morning, afternoon, evening or late-night centre.
6. Each station receives a seeded demand share. Shares are not assumed equal unless that mode is deliberately configured, and they always total 100%. The same seed reproduces both shares and assignments.
7. Arrivals are processed in chronological order at their assigned station. The scheduler assigns the earliest available plug.
8. Each plug remains occupied through charging and post-charge parking, until `plug_out_time`. Later exit delay does not occupy the plug.
9. Validation checks required fields, unique IDs, timezone-aware timestamp order, durations, energy and SOC relationships, charging power and non-overlapping plug use.
10. Summaries, charts, station measures, details and CSV export are derived from the validated rows.

## Station location, plug and session

A **station location** is one physical site. A **plug** is one independently usable charging port serving one vehicle at a time. A **session** is one EV visit.

One location with ten independently usable plugs is one station with ten plugs, not ten stations. Ten such plugs permit up to ten simultaneous connected vehicles. Real hardware may provide multiple cables that share one power port; those cables should not be counted as independent capacity in this simplified model.

The CSV identifies both `station_id` and `plug_id`. IDs remain explicit, such as `ST-03` and `ST-03-P05`. Validation rejects overlapping connected intervals on the same plug.

## Physical queue and capacity measures

For each arrival:

`charging start = max(vehicle arrival, earliest available plug time)`

The scheduler then holds the selected plug until `plug_out_time`. It does not replace a small wait with a random 20- or 30-minute value, multiply waits after scheduling, impose a minimum or cap a legitimate long queue.

Queue behavior depends on visit density, arrival concentration, station demand share, plugs, per-session charger duration and post-charge parking:

- Quiet demand or high capacity may correctly produce zero or very little waiting.
- A moderately loaded typical case often produces noticeable waiting.
- A busy or overloaded case can produce averages around 20–30 minutes and individual waits near or above an hour.
- Severe overload can produce multi-hour waits and sessions that finish outside the selected arrival period because the model assumes vehicles wait until served.

The interface reports average wait, longest wait, percentage that waited, total plugs, occupancy/utilization and sessions finishing outside the selected period. Each station shows visits, average wait, longest wait, waiting percentage and occupancy. Low waiting across many dates or many locations is explained as a valid consequence of lower density, not altered for appearance.

## Why the random seed matters

A seed is a repeatable starting point for generation. It is not a station count, model-quality score or accuracy measure.

The same settings and seed reproduce the same day types, vehicles, chargers, station shares, arrivals and rows. **Generate sessions** can therefore keep a cohort stable while capacity changes are tested. **New sample** changes the hidden seed, allowing a different arrival peak and station mix.

Fair comparisons require the same cohort. If vehicles changed at the same time as plug count, a queue reduction might come from a quieter sample instead of added capacity.

## How reference-station planning works

The **Reference station** dropdown is populated from every station in the current dataset. If the sample contains `ST-01` through `ST-06`, all six are selectable. Changing the selection updates that station's source visits, plug count, average wait, longest wait, waiting percentage and occupancy, along with every planning comparison and explanation.

After regeneration, the selected station is preserved if it still exists. If not, the first available station is selected and the displayed reference is updated rather than silently presenting stale values.

Planner inputs are:

- reference station;
- road or corridor name;
- operator of the reference station;
- candidate distance from 1 to 200 km;
- plugs at the candidate;
- plugs to add at the selected reference;
- assumed demand growth; and
- percentage of future visits choosing the candidate.

Suppose selected `ST-03` has 100 source visits. With 30% assumed growth, its future cohort has 130 visits. With 40% candidate diversion, 52 of those same visits use `NEW-01` and 78 remain at `ST-03`. All options reuse the exact same future vehicles and arrival times:

- **Current capacity:** all 130 visits use the selected reference with its current plugs.
- **Add plugs:** the same 130 visits use the selected reference with the entered extra capacity.
- **Open candidate:** 52 of the same visits use `NEW-01`; the other 78 use the selected reference.

If the reference belongs to **Another operator**, that station is only a market-demand reference. ChargeSynth AI removes expansion of the other company's station as an available action and compares the current reference with opening the user's candidate site.

Distance is a user-provided planning assumption. Changing only 10 km to 50 km or 200 km changes the description, not future cohort size, arrivals or diversion. The application does not claim to discover an optimal distance. Candidate demand changes only through the explicitly entered diversion percentage.

Outputs name the selected reference and show source visits, future visits, candidate visits, average and maximum wait, waiting percentage, occupancy, candidate-site queue and all assumptions used. A real decision still requires actual road traffic, travel direction, nearby stations, grid capacity, land, road access, costs and permissions.

## What the charts mean

The hourly chart always represents the IST clock from `00:00` through `23:59`:

- **Arrivals Y-axis:** number of vehicles whose arrival timestamp falls in the hour.
- **Energy Y-axis:** kWh requested by those arriving vehicles, not instantaneous power in that hour.
- **Bar inspection:** exact hour, arrival count, requested energy and average wait for that group.

Mouse hover, click/tap and keyboard selection expose the same values. A small sample does not have to populate every hour; the important invariant is that the generator permits all 24 hours and does not systematically exclude early morning or night.

## Storage and source organization

The project separates customer-facing files, backend calculations, model artifacts, data, documentation and tests:

| Question | Path |
|---|---|
| Where are pages and navigation? | `frontend/templates/index.html` and `frontend/static/js/app.js` |
| Where are styling and responsive rules? | `frontend/static/css/style.css` |
| Where is the realistic EV/charger hero? | `frontend/static/assets/hero-ev-charger.png` |
| Where is its energy animation? | `frontend/static/js/scene.js` |
| Where are HTTP routes and CSV download? | `backend/app.py` |
| Where is demand generated? | `backend/generator.py` |
| Where is the physical queue? | `backend/scheduler.py` |
| Where are records validated? | `backend/validation.py` |
| Where is station planning? | `backend/planning.py` |
| Where is scenario interpretation? | `backend/assistant.py` |
| Where is the generative model? | `model/vae.py` |
| Where are trained weights? | `model/chargesynth_cvae.npz` |
| Where is training code? | `training/train_model.py` |
| Where are reference/example datasets? | `data/` |
| Where are automated checks? | `tests/test_project.py` |

No database is required. A small run cache holds recent generated sessions in memory while the server is running. CSV exports are saved to a location chosen by the user. Model weights remain in `model/`, and optional private configuration remains in `.env`. Adding SQLite solely to make the project look more complex would not improve this temporary workflow.

## Assumptions and limits

- All visits, demand shares, holidays, festivals and future cohorts are synthetic.
- The model does not forecast actual traffic at a city, road or proposed station.
- Total visits are distributed across the selected eligible dates; they are not repeated every day.
- Mixed charger percentages are configurable assumptions, not observed universal usage.
- Vehicles are assumed compatible with the selected session charger. Detailed tapering, power sharing, faults and maintenance are not modelled.
- Charging efficiency is a simplified assumption; temperature and vehicle-specific acceptance curves are outside scope.
- Vehicles do not abandon a queue in the simulation.
- Candidate distance does not model travel time, direction, rerouting, prices or site accessibility.
- A shorter simulated queue does not prove financial viability or planning permission.
- The 3D hero and its continuous cable-energy lines are decorative and do not represent an electrical engineering calculation.

## Short viva answers

**What is synthetic data?** Artificial records created to explore possible patterns rather than collected from real drivers.

**What is your generative component?** A conditional VAE trained on simulated reference features, combined with seeded numerical rules for physically consistent sessions.

**Why use a separate arrival mixture?** It permits all 24 hours and varied peaks while remaining bounded, configurable and reproducible.

**How do mixed chargers work?** Each session receives AC 7 kW, AC 22 kW or DC 60 kW from a validated 40/30/30 default distribution; the chosen rating affects duration.

**How is a queue calculated?** A vehicle starts at the later of arrival or the earliest plug availability, and the plug stays occupied until unplugging.

**Why can waiting be zero?** Sparse visits or generous capacity may create no simultaneous competition for a plug.

**Why can waits become very long?** The scheduler shows actual overload and assumes vehicles remain in line instead of abandoning the site.

**Why are station shares unequal?** Locations need not attract equal demand. Seeded shares total 100% and reproduce with the same seed.

**Why select a reference station?** Each station can have different demand and queues, so planning must use the chosen station instead of always assuming `ST-01`.

**Does 50 km create demand?** No. Distance is a label supplied by the user; growth and diversion are separate explicit assumptions.

**Can ChargeSynth AI recommend a real site?** No. It compares user-entered scenarios; real traffic, grid, land, access, cost and permission evidence is required.

## Five-minute demonstration

1. Generate 200 visits with **Mixed scenario** and **Mixed chargers**; inspect day-type and charger variety.
2. Select hourly bars in both chart modes and explain the IST axes and exact values.
3. Use **New sample** to show that seeded peak periods can change, including evening and overnight possibilities.
4. Compare a busy low-capacity case with more plugs while keeping the sample fixed; point out the physical queue measures.
5. Select a non-first reference station, compare expansion and candidate options, then choose **Another operator** to remove the unavailable expansion action.
6. Change distance alone and show that future and candidate cohorts remain unchanged.
7. Search, paginate, inspect a record and download the CSV.

## Terminology and planning references

- US Department of Energy, Alternative Fuels Data Center, charging infrastructure terminology: <https://afdc.energy.gov/fuels/electricity-stations>
- NITI Aayog, *Handbook of Electric Vehicle Charging Infrastructure Implementation*, location-planning framework: <https://www.niti.gov.in/sites/default/files/2021-08/HandbookforEVChargingInfrastructureImplementation081221.pdf>
- US Department of Transportation, EV Infrastructure Project Planning Checklist: <https://www.transportation.gov/rural/ev/toolkit/ev-infrastructure-planning/project-planning-checklist>

These references support terminology and the need for traffic, site and grid evidence. They are not sources of the synthetic rows and do not validate the application's traffic assumptions.
