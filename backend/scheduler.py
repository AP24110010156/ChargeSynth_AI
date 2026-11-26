"""Physical first-come-first-served scheduling for charging plugs."""
import heapq
from datetime import datetime, timedelta


def schedule(demand, capacities):
    """Assign each visit to the earliest free plug at its requested station.

    A plug remains occupied through ``plug_out_time``.  The scheduler never
    changes a requested arrival or adds a synthetic wait adjustment.
    """
    queues = {}
    for station, count in capacities.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("Every station must have at least one charging plug.")
        queue = [(float("-inf"), plug + 1) for plug in range(count)]
        heapq.heapify(queue)
        queues[station] = queue

    rows = []
    for request in sorted(demand, key=lambda row: (row["arrival_time"], row["session_id"])):
        row = {key: value for key, value in request.items() if not key.startswith("_")}
        station = row["station_id"]
        if station not in queues:
            raise ValueError(f"No plug capacity was configured for {station}.")
        available_timestamp, plug = heapq.heappop(queues[station])
        arrival = datetime.fromisoformat(row["arrival_time"])
        if arrival.tzinfo is None:
            raise ValueError("Arrival timestamps must include a timezone.")
        start = arrival if arrival.timestamp() >= available_timestamp else datetime.fromtimestamp(
            available_timestamp, arrival.tzinfo
        )
        end = start + timedelta(seconds=request["_seconds"])
        unplug = end + timedelta(seconds=request["_idle"])
        exit_time = unplug + timedelta(seconds=request["_exit"])
        heapq.heappush(queues[station], (unplug.timestamp(), plug))
        row.update(
            plug_id=f"{station}-P{plug:02d}",
            plug_in_time=start.isoformat(),
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            plug_out_time=unplug.isoformat(),
            exit_time=exit_time.isoformat(),
            duration_minutes=round(request["_seconds"] / 60, 2),
            connected_minutes=round((unplug - start).total_seconds() / 60, 2),
            queue_wait_minutes=round((start - arrival).total_seconds() / 60, 2),
        )
        rows.append(row)
    return rows
