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

    queue = [(0, origin)]  # (days so far, airport)
    best_days = {origin: 0}
    came_by = {}  # airport -> leg used to reach it on the fastest known path
    while queue:
        days, airport = heapq.heappop(queue)
        if airport == destination:
            path = []
            while airport != origin:
                leg = came_by[airport]
                path.append(leg)
                airport = leg["origin"]
            return path[::-1]
        if days > best_days[airport]:
            continue  # stale entry: a faster path to this airport was already expanded
        for leg in by_origin[airport]:
            arrival = days + leg["days"]
            if arrival < best_days.get(leg["destination"], float("inf")):
                best_days[leg["destination"]] = arrival
                came_by[leg["destination"]] = leg
                heapq.heappush(queue, (arrival, leg["destination"]))
    return None


def unroutable(requirements, issue):
    return {"route": [], "transit_days": None, "met": [], "unmet": requirements, "issue": issue}


def faster_option(legs, origin, destination, requirements, max_days):
    """When the compliant route is too slow, point out an on-time route that drops some
    requirements, so a human can choose. The trade-off is never made automatically."""
    path = fastest_route(legs, origin, destination, set())
    days = sum(leg["days"] for leg in path)
    if days > max_days:
        return []
    route = " > ".join([path[0]["origin"]] + [leg["destination"] for leg in path])
    dropped = [r for r in requirements if not all(r in leg["services"] for leg in path)]
    return [f"Faster option: {route} in {days:g} days, without {', '.join(dropped)}"]


def plan_route(legs, origin, destination, requirements, max_days):
    """Prefer a route where every leg supports every requirement (the cargo is on every flight).
    If none exists, take the fastest route and report which requirements it cannot meet."""
    if origin == destination:
        return unroutable(requirements, "Origin and destination are the same")

    path = fastest_route(legs, origin, destination, set(requirements))
    if path is None:
        path = fastest_route(legs, origin, destination, set())
    if path is None:
        return unroutable(requirements, "No route on our network")

    met = [r for r in requirements if all(r in leg["services"] for leg in path)]
    unmet = [r for r in requirements if r not in met]
    days = sum(leg["days"] for leg in path)

    issues = []
    if unmet:
        issues.append("Not available on every leg: " + ", ".join(unmet))
    if days > max_days:
        issues.append(f"Transit {days:g} days exceeds the {max_days:g}-day maximum")
        if requirements and not unmet:
            issues += faster_option(legs, origin, destination, requirements, max_days)

    return {
        "route": [path[0]["origin"]] + [leg["destination"] for leg in path],
        "transit_days": days,
        "met": met,
        "unmet": unmet,
        "issue": "; ".join(issues) or None,
    }
