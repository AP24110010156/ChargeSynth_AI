# Start ChargeSynth AI

ChargeSynth AI creates synthetic EV charging visits, calculates queues from actual plug availability and compares hypothetical station-capacity options. You do not need to collect or type a dataset before running it. The project includes trained model weights and example CSV files.

## Run a fresh copy on Windows

1. Right-click `ChargeSynth_AI_Professional_Updated.zip` and choose **Extract All**. Do not run the project inside the ZIP viewer.
2. Open the extracted `ChargeSynth_AI` folder.
3. Double-click `start_windows.bat`.
4. On first use, the launcher creates `.venv` and installs the required packages. Internet access is needed for that installation.
5. Your browser opens <http://127.0.0.1:5000>. Keep the terminal window open while using the studio.
6. If the browser does not open automatically, enter that address yourself.
7. To stop the app, select its terminal and press **Ctrl+C**.

Python 3.11 or newer must already be installed. If the launcher cannot find Python, install it from <https://www.python.org/downloads/windows/> and enable **Add python.exe to PATH**, then run the launcher again. VS Code is an editor; installing VS Code does not install Python.

## Run from VS Code

1. Choose **File → Open Folder** and select the extracted `ChargeSynth_AI` folder.
2. Choose **Terminal → New Terminal**.
3. Run:

```powershell
.\start_windows.bat
```

Manual setup is also supported:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

No PowerShell activation command or execution-policy change is required. On macOS/Linux, run `bash start_mac_linux.sh` from the project folder.

## Five-minute demonstration

1. Keep **200 visits**, **3 station locations**, **8 plugs per location** and **1 day**. Choose **Mixed scenario** and **Mixed chargers**, then select **Generate sessions**.
2. Open several session details and inspect `day_type` and `charger_type`. Mixed scenario can include weekdays, weekends, hypothetical holidays and hypothetical festivals. Mixed chargers uses the documented configurable assumptions: AC 7 kW 40%, AC 22 kW 30% and DC 60 kW 30%.
3. Select a bar in **When vehicles arrive**. Confirm the horizontal axis covers IST hours `00:00–23:59`. Switch between **Arrivals** and **Energy** and inspect the exact hour, visits, kWh and average wait shown for that bar.
4. Choose **Rush hour**, generate again and use **New sample** a few times. Different seeded samples can concentrate in the morning, afternoon, evening or late night; the peak is not permanently fixed.
5. Create a busy capacity case, such as **1 location** with **6 plugs**. Compare its average wait, longest wait, waiting percentage, occupancy and spillover with a higher-capacity version. All waits come from the physical queue. A sparse case may correctly show zero wait; severe overload may show long waits.
6. In **Station planning**, choose a reference station other than the first one. Confirm its visits and queue figures update, then compare current capacity, adding plugs and a candidate station using the same future cohort.
7. Switch the operator to **Another operator**. Expansion of that company's station is removed, while the candidate-site option remains. Change only distance and confirm the assumed number of future visits does not change.
8. Open **Session data**, search for a station or plug, view a record, move between pages and download the CSV.

Use **New sample** only when you want different synthetic vehicles, station shares and arrival patterns. Reusing the same seed and settings reproduces the same rows, which is essential when comparing capacity.

## Four definitions that prevent common confusion

- **Station location:** one physical site. A site with ten independently usable plugs is one station with ten plugs, not ten stations.
- **Plug:** one simultaneous charging space in this simplified model. Count independently usable ports, not connector cables that share one power port.
- **Session:** one synthetic EV visit. The EV is not an “AC car” or “DC car”; its session uses an AC or DC charging port.
- **Random seed:** a repeatable starting point for generation. It is not a station count or accuracy score. **New sample** changes the hidden seed.

## Day and charger choices

**Calendar Days** labels each visit as weekday or weekend from its selected date. **Weekday** and **Weekend** restrict dates to that category. **Holiday** and **Festival** are hypothetical scenarios. **Mixed scenario** creates a controlled combination of all four supported day types; it does not claim that a date is a verified public holiday.

**Mixed chargers** chooses a charger for each session from an editable probability distribution that totals 100%: AC 7 kW 40%, AC 22 kW 30% and DC 60 kW 30% by default. These percentages are simulation assumptions, not universal real-world usage. The selected charger's power changes the session duration.

## Why waiting can be zero—or very long

The scheduler processes arrivals in first-come-first-served order at each station:

`charging start = max(vehicle arrival, earliest available plug time)`

The plug remains unavailable until `plug_out_time`, including post-charge parking. The program does not add random waiting, impose a 20-minute minimum or cap legitimate queues. A few visits spread across many days, stations or plugs may have no wait. Concentrated demand at a small station may produce 20–30 minute average waits, waits above an hour or, under severe overload, multi-hour spillover. Those results describe the chosen synthetic assumptions rather than measured traffic.

## What the planner can and cannot say

The reference-station dropdown is populated from the current dataset. If a selected station still exists after regeneration it remains selected; otherwise the interface moves to the first available station. Planning comparisons reuse one future synthetic vehicle cohort and the same arrival times. Differences come only from capacity and the entered diversion share.

Distance is a user-entered label from 1 to 200 km. Changing it alone does not add demand or reveal an optimal site. If the reference belongs to **Another operator**, ChargeSynth AI uses it only as a demand reference and does not present expansion of that company's station as an action.

Before a real deployment, verify actual road traffic, travel direction, nearby stations, grid capacity, land, road access, costs and permissions.

## Where data is stored

- Recent generated runs are held temporarily in memory while the app is open.
- Downloaded datasets are CSV files saved wherever the user chooses.
- Trained weights are stored in `model/`.
- Optional private configuration is stored in `.env` and is not shown in the interface.
- No SQLite or other database is required for temporary sessions.

## Learn more

- `docs/PROJECT_GUIDE.md` — project design, assumptions, file locations and viva answers.
- `docs/DATA_DICTIONARY.md` — every exported field, equation and chart unit.
- `docs/VERIFICATION.md` — automated and browser verification checklist.
- `docs/PRIVATE_SETUP.md` — private developer configuration, separate from the customer interface.
