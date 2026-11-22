from routing import plan_route

DG = "Dangerous goods"
FRAGILE = "Fragile handling"


def leg(origin, destination, days, *services):
    return {"origin": origin, "destination": destination, "days": days, "services": list(services)}


def test_direct_route():
    plan = plan_route([leg("AAA", "BBB", 2, DG)], "AAA", "BBB", [DG], max_days=5)
    assert plan["route"] == ["AAA", "BBB"]
    assert plan["met"] == [DG]
    assert plan["issue"] is None


def test_requirement_must_hold_on_every_leg():
    legs = [
        leg("AAA", "BBB", 1, DG),  # faster, but no fragile handling
        leg("AAA", "HUB", 1, DG, FRAGILE),
        leg("HUB", "BBB", 1, DG, FRAGILE),
    ]
    plan = plan_route(legs, "AAA", "BBB", [DG, FRAGILE], max_days=5)
    assert plan["route"] == ["AAA", "HUB", "BBB"]
    assert plan["unmet"] == []


def test_reports_unmet_requirements_and_slow_transit():
    plan = plan_route([leg("AAA", "BBB", 9)], "AAA", "BBB", [DG], max_days=5)
    assert plan["route"] == ["AAA", "BBB"]
    assert plan["unmet"] == [DG]
    assert "Dangerous goods" in plan["issue"] and "exceeds" in plan["issue"]


def test_no_route():
    plan = plan_route([leg("AAA", "BBB", 1)], "BBB", "AAA", [], max_days=5)
    assert plan["route"] == []
    assert plan["issue"] == "No route on our network"
