# Data and chart guide

One exported row represents one synthetic EV visit. All 25 fields are populated, and every timestamp includes the IST offset `+05:30`.

## CSV fields

| Field | Meaning / unit |
|---|---|
| `session_id` | Unique synthetic visit identifier |
| `station_id` | Assigned physical location, for example `ST-01` |
| `plug_id` | Independently usable port, for example `ST-01-P03` |
| `day_type` | Assigned `weekday`, `weekend`, `holiday` or `festival` scenario |
| `day_of_week` | Calendar weekday name for the arrival date |
| `calendar_basis` | Whether the label came from the calendar or a hypothetical special-day scenario |
| `arrival_time` | Vehicle arrival at its assigned station |
| `plug_in_time` | Time a plug becomes available and the vehicle connects |
| `start_time` | Charging start; equal to plug-in in this simplified model |
| `end_time` | End of active energy transfer |
| `plug_out_time` | Disconnect time; the plug becomes available at this moment |
| `exit_time` | Vehicle departure; post-unplug exit delay does not occupy the plug |
| `duration_minutes` | Active charging duration in minutes |
| `connected_minutes` | Charging plus post-charge parking in minutes |
| `queue_wait_minutes` | Minutes from arrival to plug-in |
| `kwh_consumed` | Grid energy delivered during the session, in kWh |
| `vehicle_type` | Synthetic compact EV, sedan EV or SUV EV category |
| `charger_type` | Session port: AC 7 kW, AC 22 kW or DC 60 kW |
| `charger_power_kw` | Maximum rating of the session's selected port, in kW |
| `average_power_kw` | Mean charging power during active energy transfer, in kW |
| `battery_capacity_kwh` | Assumed vehicle battery capacity, in kWh |
| `soc_in` | Battery state of charge on arrival, percent |
| `soc_out` | Battery state of charge after charging, percent |
| `charging_efficiency` | Assumed grid-to-battery efficiency as a fraction |
| `source` | Synthetic-data and capacity-queue provenance label |

Mixed scenario never writes `mixed` as a row's day type. It assigns each row one explicit supported type. Holiday and festival rows are hypothetical unless a verified calendar is separately implemented.

Mixed chargers never changes the vehicle into an “AC car” or “DC car.” It assigns the session a charging port. The default probabilities are AC 7 kW 40%, AC 22 kW 30% and DC 60 kW 30%. They total 100%, are configurable backend assumptions and are not universal usage statistics.

## Timestamp order and equations

Every valid record follows:

`arrival ≤ plug-in = charging start < charging end ≤ unplug ≤ exit`

Core relationships are:

- `grid energy = battery size × (SOC out − SOC in) / 100 / efficiency`
- `active charging seconds = ceil(3600 × grid energy / sampled average charging power)`
- `average power ≤ selected charger rating`
- `charging start = max(arrival, earliest availability at the assigned station)`
- `queue minutes = (charging start − arrival) / 60`
- `connected minutes = (plug-out − plug-in) / 60`
- `next plug availability = plug-out time`

The scheduler processes arrivals in chronological, first-come-first-served order. No two vehicles may have overlapping intervals from `plug_in_time` to `plug_out_time` on the same `plug_id`.

## Day and arrival data

**Calendar Days** derives weekday/weekend from selected dates. **Weekday** and **Weekend** restrict the calendar dates. **Holiday** and **Festival** assign explicitly hypothetical special-day scenarios. **Mixed scenario** uses a controlled, seeded combination of weekday, weekend, hypothetical holiday and hypothetical festival rows.

Arrival timestamps can occur in any of the 24 IST hours. The generator uses seeded morning, afternoon, evening, late-night/overnight and all-day background components:

- **Spread out:** broad distribution with background demand.
- **Typical:** several possible daily peaks plus background demand.
- **Rush hour:** a concentrated peak whose period is seeded rather than permanently fixed.

A small dataset need not contain a visit in every hour. Across suitable seeds, however, all hours are possible. The same seed and settings reproduce the same times; **New sample** changes the hidden seed and can change the peak.

## Station assignment and capacity

A station is one physical location; a plug is one independently usable charging position at that location. Simultaneous capacity is the sum of the available plugs, not the number of cables printed on hardware.

Stations receive configurable or generated demand shares that total 100%. The shares and row assignments use the hidden seed, so they are transparent and reproducible rather than silently assumed equal. Demand share is a simulation-routing assumption, not a geographic model or measured market share.

Per-station output includes:

- station ID and plug count;
- assigned visits;
- average wait;
- longest wait;
- percentage of visits that waited; and
- connected-time occupancy/utilization during the selected period.

Plug occupancy includes active charging and post-charge parking through `plug_out_time`. Exit delay after unplugging is not plug occupancy.

## Screen measures

| Display | Exact meaning |
|---|---|
| Charging visits | Total validated rows across all locations and selected eligible dates |
| Session energy | Grid kWh for complete sessions, including sessions that finish after the arrival period |
| Average charging time | Mean active charging duration, excluding queue and post-charge parking |
| Average queue wait | Mean wait across all visits, including visits with zero wait |
| Longest wait | Maximum `queue_wait_minutes` |
| Visits that waited | Percentage of visits with a wait greater than zero |
| Total plugs | Sum of independently usable plugs across the generated locations |
| Plug occupancy | Connected time inside the selected period divided by total available plug-time |
| Finishing outside period | Sessions whose `plug_out_time` is after the selected arrival window |
| Station rows | Visits, average/maximum wait, waiting percentage and occupancy for each station |

A 1-day sample and a 14-day sample with the same total visit count have very different density. “200 visits over 14 days” does not mean “200 visits every day.” Low density can correctly produce zero waiting.

## Hourly chart

| Chart element | Exact meaning |
|---|---|
| Horizontal axis | Arrival hour in IST, covering `00:00–23:59` |
| Arrivals vertical axis | Number of vehicles whose `arrival_time` falls in the hour |
| Energy vertical axis | kWh requested by vehicles arriving in the hour, not instantaneous power |
| Selected-bar hour | Exact one-hour IST interval |
| Selected-bar arrivals | Row count for that interval |
| Selected-bar energy | Sum of `kwh_consumed` for those arrivals |
| Selected-bar wait | Average `queue_wait_minutes` for those arrivals |

Hover, click/tap and keyboard selection expose the same exact values. An empty hour shows zero visits, zero energy and zero wait. An hour with visits can also legitimately show zero wait.

## Planning output

The reference-station selector comes from the current dataset. Its displayed source measures—visits, plugs, average and maximum wait, waiting percentage and occupancy—must match that station's generated rows.

Planning creates one future cohort from the selected station and reuses the exact same synthetic vehicles and arrival times for every option. Output fields describe:

- selected reference station and source visits;
- assumed future visits after explicit growth;
- candidate visits after explicit diversion;
- current-capacity queue measures;
- added-plug queue measures when the reference belongs to Our Network;
- combined and candidate-site queue measures for the proposed station;
- occupancy and waiting measures; and
- the road, owner, distance, plug, growth and diversion assumptions.

If the reference belongs to Another operator, its expansion result is unavailable rather than shown as an action. Distance from 1 to 200 km is descriptive only. Changing distance alone must not change source visits, future visits, candidate visits or arrival times.

## Validation summary

Before a result is returned or exported, checks cover:

- all required fields populated;
- unique session IDs;
- timezone-aware timestamps in valid order;
- queue, active and connected duration arithmetic;
- `SOC in < SOC out` and valid efficiency;
- battery/energy consistency;
- average power within the charger limit;
- no overlapping use of a plug; and
- summary totals matching the dataset rows.

These are software and physical-consistency checks. They do not establish measured traffic accuracy, an optimal station location or commercial feasibility.
