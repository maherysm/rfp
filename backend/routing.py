"""Find how each lane will be routed on the client's flight network."""

import heapq
from collections import defaultdict
from itertools import combinations


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
    return {"route": [], "transit_days": None, "met": [], "unmet": requirements, "issue": issue,
            "alternative": None}


def describe(path, requirements, max_days):
    """What a route offers the customer: its airports, transit time, requirements met and issues."""
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


def most_requirements(options):
    """The option that meets the most requirements (all count equally); the fastest one if tied."""
    return max(options, key=lambda option: (len(option["met"]), -option["transit_days"]))


def route_options(legs, origin, destination, requirements, max_days):
    """The fastest route that keeps each combination of requirements on every leg. A lane has at
    most a handful of requirements, so trying every combination stays cheap."""
    options = {}
    for count in range(len(requirements) + 1):
        for kept in combinations(requirements, count):
            path = fastest_route(legs, origin, destination, set(kept))
            if path:
                option = describe(path, requirements, max_days)
                key = tuple(option["route"])
                options[key] = most_requirements([options[key], option]) if key in options else option
    return list(options.values())


def plan_route(legs, origin, destination, requirements, max_days):
    """Take the route that meets the most requirements on every leg (the cargo is on every flight),
    the fastest one if several tie, and report which requirements it cannot meet.

    When that route is too slow but an on-time route exists, the on-time route meeting the most
    requirements is returned as `alternative` so a human can choose. The trade-off is never made
    automatically."""
    if origin == destination:
        return unroutable(requirements, "Origin and destination are the same")

    options = route_options(legs, origin, destination, requirements, max_days)
    if not options:
        return unroutable(requirements, "No route on our network")

    plan = {**most_requirements(options), "alternative": None}
    on_time = [option for option in options if option["transit_days"] <= max_days]
    if plan["transit_days"] > max_days and on_time:
        faster = most_requirements(on_time)
        plan["alternative"] = faster
        plan["issue"] += (f"; Faster option: {' > '.join(faster['route'])} in "
                          f"{faster['transit_days']:g} days, without {', '.join(faster['unmet'])}")
    return plan
