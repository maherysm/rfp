"""Find how each lane will be routed on the client's flight network."""

import heapq
from collections import defaultdict


def fastest_route(legs, origin, destination, required):
    """Dijkstra's shortest path: the quickest sequence of flights from origin to destination,
    using only legs that offer every service in `required`. Returns a list of legs or None."""
    by_origin = defaultdict(list)
    for leg in legs:
        if required.issubset(leg["services"]):
            by_origin[leg["origin"]].append(leg)

    queue = [(0, origin, [])]  # (days so far, airport, legs taken to get there)
    best_days = {origin: 0}
    while queue:
        days, airport, path = heapq.heappop(queue)
        if airport == destination:
            return path
        if days > best_days[airport]:
            continue  # stale entry: a faster path to this airport was already expanded
        for leg in by_origin[airport]:
            arrival = days + leg["days"]
            if arrival < best_days.get(leg["destination"], float("inf")):
                best_days[leg["destination"]] = arrival
                heapq.heappush(queue, (arrival, leg["destination"], path + [leg]))
    return None


def plan_route(legs, origin, destination, requirements, max_days):
    """Prefer a route where every leg supports every requirement (the cargo is on every flight).
    If none exists, take the fastest route and report which requirements it cannot meet."""
    path = fastest_route(legs, origin, destination, set(requirements))
    if path is None:
        path = fastest_route(legs, origin, destination, set())
    if path is None:
        return {"route": [], "transit_days": None, "met": [], "unmet": requirements,
                "issue": "No route on our network"}

    met = [r for r in requirements if all(r in leg["services"] for leg in path)]
    unmet = [r for r in requirements if r not in met]
    days = sum(leg["days"] for leg in path)

    issues = []
    if unmet:
        issues.append("Not available on every leg: " + ", ".join(unmet))
    if days > max_days:
        issues.append(f"Transit {days:g} days exceeds the {max_days:g}-day maximum")

    return {
        "route": [path[0]["origin"]] + [leg["destination"] for leg in path],
        "transit_days": days,
        "met": met,
        "unmet": unmet,
        "issue": "; ".join(issues) or None,
    }
