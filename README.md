# ChargeSynth AI — Synthetic EV Charging Session Generator and Station Planning Studio

ChargeSynth AI is a ready-to-run local application for creating synthetic EV charging sessions and comparing hypothetical station-capacity options. Start with **START_HERE.md**.

- One-page professional interface with Session studio, Station planning and Session data sections.
- Dark charcoal styling, restrained green accents and a theme-matched 3D EV-to-charger hero with continuous flowing energy lines.
- Seeded, reproducible synthetic demand with weekday, weekend and explicitly hypothetical special-day scenarios.
- A configurable mixed-charger assumption alongside AC 7 kW, AC 22 kW and DC 60 kW single-charger modes.
- Seeded arrival patterns that can peak in the morning, afternoon, evening or overnight while allowing demand in every hour of the day.
- Independent plugs, first-come-first-served queues, full IST timestamps and validation against overlapping plug use.
- Seeded station demand shares, per-station capacity measures and fair comparisons that reuse the same future vehicle cohort.
- A reference-station selector for comparing current capacity, added plugs and a proposed station along a named road.
- Interactive hourly arrival and energy charts, record details, search, pagination and CSV export.
- No provider names, secret-entry fields, model-quality controls or private configuration in the customer interface.

## Quick start

On Windows, extract the ZIP, open the `ChargeSynth_AI` folder and double-click `start_windows.bat`.

Manual start:

```bash
python -m venv .venv
# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
# macOS/Linux
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Open <http://127.0.0.1:5000>. The launcher runs an educational application on your own computer; it is not an Internet production server.

## Important simulation assumptions

**Day scenarios.** Calendar Days derives weekday or weekend from the selected dates. Mixed scenario creates a controlled, seeded combination of weekdays, weekends, hypothetical holidays and hypothetical festivals. Holiday and festival labels are simulation labels, not verified public-calendar entries.

**Charger mix.** Mixed chargers defaults to AC 7 kW 40%, AC 22 kW 30% and DC 60 kW 30%. These percentages total 100%, live in one editable backend configuration object and are assumptions for this simulation—not universal usage statistics. Each session's selected charger controls its power and duration.

**Arrival patterns.** Spread out, Typical and Rush hour all permit arrivals across the full 24-hour IST clock. Seeded mixture components vary peak centres and weights, so Rush hour can represent a morning, afternoon, evening or late-night concentration instead of one permanent peak. The same settings and seed reproduce the same rows; **New sample** changes the hidden seed.

**Capacity queues.** Waiting is produced by the plug scheduler, not added afterwards:

`charging start = later of vehicle arrival or earliest available plug time`

A plug remains occupied until `plug_out_time`. Quiet or high-capacity cases can correctly have no wait. Concentrated or overloaded cases can produce substantial or multi-hour waits; the application reports those values rather than imposing a minimum, multiplier or cosmetic cap.

## Project structure

| Path | Purpose |
|---|---|
| `frontend/templates/index.html` | One-page screen structure |
| `frontend/static/css/style.css` | Existing colours, spacing and responsive layout |
| `frontend/static/js/app.js` | Navigation, forms, charts, planning, table and CSV actions |
| `frontend/static/assets/hero-ev-charger.png` | Local theme-matched 3D EV and fast-charger hero asset |
| `frontend/static/js/scene.js` | Continuous cable-energy lines with reduced-motion and offscreen handling |
| `backend/app.py` | Flask routes, in-memory run cache, request handling and CSV download |
| `backend/generator.py` | Seeded demand, day/charger assumptions and summaries |
| `backend/scheduler.py` | Physical first-come-first-served plug scheduling |
| `backend/planning.py` | Reference-station and candidate-site comparisons |
| `backend/validation.py` | Record and plug-overlap validation |
| `backend/assistant.py` | ChargeSynth AI scenario interpretation and safe calculated fallback |
| `model/vae.py` | Conditional VAE implemented with NumPy |
| `model/chargesynth_cvae.npz` | Bundled trained weights and scaling values |
| `training/train_model.py` | Reproduce simulated reference data and train the model |
| `data/` | Reference features and example CSV datasets |
| `docs/` | Project, data, verification and private-setup guides |
| `tests/test_project.py` | Observable behavior and invariant tests |
| `run.py` | Project-root launcher |

There is deliberately no database. Recent generated runs may remain in a small in-memory cache while the application is open. A user saves a generated dataset by downloading its CSV. Model weights live in `model/`; optional private developer configuration lives in `.env`. Closing the application clears the in-memory cache.

## Verify or retrain

```bash
python -m pip install pytest
python -m pytest -q
python training/train_model.py
```

Training is optional because trained weights are included. Queue time is never taken from a learned queue feature; the scheduler calculates it from arrival time, plug capacity, charging duration and connected time.

## Scope

All visits, station shares, holiday/festival labels and planning cohorts are synthetic. The planner evaluates assumptions supplied by the user; it does not discover demand, optimize distance or recommend an actual site. A real deployment still requires actual road traffic, travel direction, nearby stations, grid capacity, land, road access, costs and permissions.

Private setup is documented in `docs/PRIVATE_SETUP.md` and is not exposed in product HTML or browser responses.
