import pytest
from fastapi.testclient import TestClient

import ai
import db
import workflow
from main import app

client = TestClient(app)
LANE = {"origin": "HKG", "destination": "LHR"}


@pytest.mark.parametrize("line", [
    "HKG-LHR: $2,500 per ton",
    "For HKG to LHR we recommend $2,500/ton including the requested services.",
    "HKG-LHR - suggest $2,500 a ton",
])
def test_usd_per_ton_prices_are_used(line):
    price = ai.parse_pricing_email(line)["HKG-LHR"]
    assert price == 2500
    assert workflow.price_problem(LANE, price, line) is None


@pytest.mark.parametrize("line, reason", [
    ("HKG-LHR: -$2,500 per ton", "not a positive price"),
    ("HKG-LHR: $-2,500 per ton", "not a positive price"),
    ("HKG-LHR: $0 per ton", "not a positive price"),
    ("HKG-LHR: HK$19,500 per ton", "another currency (HK$)"),
    ("HKG-LHR: \u20ac2,300 (about $2,500) per ton", "another currency (\u20ac)"),
    ("HKG-LHR: EUR 2,300 or $2,500 per ton", "another currency (EUR)"),
    ("HKG-LHR: $2.45 per kg", "not per ton (per kg)"),
    ("HKG-LHR: $2.45/kg", "not per ton (/kg)"),
    ("HKG-LHR: $48,000 total for the lane", "not per ton (total)"),
])
def test_wrong_sign_currency_or_unit_is_rejected(line, reason):
    price = ai.parse_pricing_email(line)["HKG-LHR"]
    assert reason in workflow.price_problem(LANE, price, line)


def test_rejected_price_is_left_for_a_human(monkeypatch):
    def reply(lanes, seed):
        first, rest = lanes[0], lanes[1:]
        lines = [f"{first['origin']}-{first['destination']}: \u20ac2,800 (about $3,000) per ton"]
        return "\n".join(lines + [f"{l['origin']}-{l['destination']}: $3,000 per ton" for l in rest])

    monkeypatch.setattr(workflow.mock_pricing, "pricing_team_reply", reply)
    rfp_id = client.post("/api/rfps/sample").json()["id"]
    client.post(f"/api/rfps/{rfp_id}/approve-plan")

    rfp = client.get(f"/api/rfps/{rfp_id}").json()
    first = next(l for l in rfp["lanes"] if l["route"])
    name = f"{first['origin']}-{first['destination']}"
    assert rfp["missing_prices"] == [name]
    assert first["price"] is None
    events = [e["message"] for e in client.get(f"/api/rfps/{rfp_id}/events").json()]
    assert any(m.startswith(f"Ignored the price for {name}") for m in events)
    assert client.post(f"/api/rfps/{rfp_id}/approve-prices").status_code == 400


def test_prices_cannot_be_approved_unless_positive():
    rfp_id = client.post("/api/rfps/sample").json()["id"]
    client.post(f"/api/rfps/{rfp_id}/approve-plan")
    lanes = [l for l in client.get(f"/api/rfps/{rfp_id}").json()["lanes"] if l["route"]]
    for lane in lanes:
        db.update("lanes", lane["id"], price=3000)
    db.update("lanes", lanes[0]["id"], price=-5)

    response = client.post(f"/api/rfps/{rfp_id}/approve-prices")
    assert response.status_code == 400
    assert f"{lanes[0]['origin']}-{lanes[0]['destination']}" in response.json()["detail"]
    assert client.get(f"/api/rfps/{rfp_id}").json()["status"] == "review_prices"
