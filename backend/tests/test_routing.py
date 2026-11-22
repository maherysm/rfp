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


def test_suggests_faster_route_when_compliant_one_is_too_slow():
    legs = [
        leg("AAA", "BBB", 2, DG),  # on time, but no fragile handling
        leg("AAA", "HUB", 4, DG, FRAGILE),
        leg("HUB", "BBB", 4, DG, FRAGILE),
    ]
    plan = plan_route(legs, "AAA", "BBB", [DG, FRAGILE], max_days=5)
    assert plan["route"] == ["AAA", "HUB", "BBB"]
    assert plan["unmet"] == []
    assert "exceeds" in plan["issue"]
    assert "Faster option: AAA > BBB in 2 days, without Fragile handling" in plan["issue"]
    assert plan["alternative"]["route"] == ["AAA", "BBB"]
    assert plan["alternative"]["transit_days"] == 2
    assert plan["alternative"]["unmet"] == [FRAGILE]
    assert plan["alternative"]["issue"] == "Not available on every leg: Fragile handling"


def test_no_faster_option_when_nothing_fits():
    legs = [leg("AAA", "BBB", 6, DG), leg("AAA", "HUB", 4, DG, FRAGILE), leg("HUB", "BBB", 4, DG, FRAGILE)]
    plan = plan_route(legs, "AAA", "BBB", [DG, FRAGILE], max_days=5)
    assert "exceeds" in plan["issue"]
    assert "Faster option" not in plan["issue"]
    assert plan["alternative"] is None


def partial_network():
    """No leg offers fragile handling. AAA > BBB is fastest but has no dangerous goods handling;
    AAA > CCC > BBB keeps dangerous goods; AAA > HUB > BBB does too but is slower."""
    return [
        leg("AAA", "BBB", 1),
        leg("AAA", "CCC", 2, DG),
        leg("CCC", "BBB", 2, DG),
        leg("AAA", "HUB", 4, DG),
        leg("HUB", "BBB", 4, DG),
    ]


def test_when_nothing_meets_everything_take_the_route_meeting_the_most():
    plan = plan_route(partial_network(), "AAA", "BBB", [DG, FRAGILE], max_days=5)
    assert plan["route"] == ["AAA", "CCC", "BBB"]
    assert (plan["met"], plan["unmet"]) == ([DG], [FRAGILE])
    assert plan["alternative"] is None


def test_too_slow_partial_route_offers_the_on_time_one():
    plan = plan_route(partial_network(), "AAA", "BBB", [DG, FRAGILE], max_days=3)
    assert plan["route"] == ["AAA", "CCC", "BBB"]
    assert plan["alternative"]["route"] == ["AAA", "BBB"]
    assert "Faster option: AAA > BBB in 1 days, without Dangerous goods, Fragile handling" in plan["issue"]


def test_alternative_drops_as_few_requirements_as_possible():
    legs = partial_network() + [leg("AAA", "HUB", 4, DG, FRAGILE), leg("HUB", "BBB", 4, DG, FRAGILE)]
    plan = plan_route(legs, "AAA", "BBB", [DG, FRAGILE], max_days=5)
    assert plan["route"] == ["AAA", "HUB", "BBB"]
    assert plan["unmet"] == []
    assert plan["alternative"]["route"] == ["AAA", "CCC", "BBB"]
    assert plan["alternative"]["unmet"] == [FRAGILE]


def test_no_route():
    plan = plan_route([leg("AAA", "BBB", 1)], "BBB", "AAA", [], max_days=5)
    assert plan["route"] == []
    assert plan["issue"] == "No route on our network"


def test_same_origin_and_destination_is_rejected():
    plan = plan_route([leg("AAA", "BBB", 1, DG)], "AAA", "AAA", [DG], max_days=5)
    assert plan["route"] == []
    assert plan["transit_days"] is None
    assert plan["unmet"] == [DG]
    assert plan["issue"] == "Origin and destination are the same"
