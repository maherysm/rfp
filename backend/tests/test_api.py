from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def status_of(rfp_id):
    return client.get(f"/api/rfps/{rfp_id}").json()["status"]


def lane_named(rfp_id, name):
    return next(l for l in client.get(f"/api/rfps/{rfp_id}").json()["lanes"]
                if f"{l['origin']}-{l['destination']}" == name)


def draft_quote_for_sample():
    rfp_id = client.post("/api/rfps/sample").json()["id"]
    client.post(f"/api/rfps/{rfp_id}/approve-plan")
    for name in client.get(f"/api/rfps/{rfp_id}").json()["missing_prices"]:
        client.put(f"/api/lanes/{lane_named(rfp_id, name)['id']}/price", json={"price": 3000})
    client.post(f"/api/rfps/{rfp_id}/approve-prices")
    assert status_of(rfp_id) == "review_quote"
    return rfp_id


def test_full_workflow_from_rfp_to_logged_proposal():
    rfp_id = client.post("/api/rfps/sample").json()["id"]
    rfp = client.get(f"/api/rfps/{rfp_id}").json()
    assert rfp["status"] == "review_plan"
    assert len(rfp["lanes"]) == 100
    assert "Pricing team" in rfp["pricing_draft"]

    assert client.post(f"/api/rfps/{rfp_id}/approve-plan").status_code == 200
    assert status_of(rfp_id) == "review_prices"

    # The mock Pricing team leaves one lane unpriced, so approval is blocked until a human fills it in.
    missing = client.get(f"/api/rfps/{rfp_id}").json()["missing_prices"]
    assert len(missing) == 1
    assert client.post(f"/api/rfps/{rfp_id}/approve-prices").status_code == 400
    lane = next(l for l in client.get(f"/api/rfps/{rfp_id}").json()["lanes"]
                if f"{l['origin']}-{l['destination']}" == missing[0])
    assert client.put(f"/api/lanes/{lane['id']}/price", json={"price": 3000}).status_code == 200

    assert client.post(f"/api/rfps/{rfp_id}/approve-prices").status_code == 200
    draft = client.get(f"/api/rfps/{rfp_id}").json()["quote_draft"]
    assert "per ton" in draft["lane_details"]

    body = {"intro": draft["intro"], "closing": draft["closing"]}
    assert client.post(f"/api/rfps/{rfp_id}/approve-quote", json=body).status_code == 200
    assert status_of(rfp_id) == "awaiting_customer"

    reply = {"text": "We accept the proposal, please go ahead."}
    assert client.post(f"/api/rfps/{rfp_id}/customer-reply", json=reply).status_code == 200
    rfp = client.get(f"/api/rfps/{rfp_id}").json()
    assert rfp["status"] == "won"
    assert rfp["proposal"]["lane_count"] == sum(1 for l in rfp["lanes"] if l["route"])
    assert rfp["meeting"]["title"] == "Contract kickoff"


def test_unclear_reply_goes_to_a_human():
    rfp_id = draft_quote_for_sample()
    client.post(f"/api/rfps/{rfp_id}/approve-quote", json={"intro": "Hello", "closing": "Thanks"})

    client.post(f"/api/rfps/{rfp_id}/customer-reply", json={"text": "Can you lower the price?"})
    assert status_of(rfp_id) == "review_reply"
    client.post(f"/api/rfps/{rfp_id}/decide", json={"decision": "declined"})
    assert status_of(rfp_id) == "lost"


def test_sent_quote_prices_always_match_the_lane_table():
    rfp_id = draft_quote_for_sample()
    lane = next(l for l in client.get(f"/api/rfps/{rfp_id}").json()["lanes"] if l["route"])
    name = f"{lane['origin']}-{lane['destination']}"

    # Prices can't be changed during quote review, and the old free-text quote body is rejected.
    assert client.put(f"/api/lanes/{lane['id']}/price", json={"price": 1234}).status_code == 409
    assert client.post(f"/api/rfps/{rfp_id}/approve-quote", json={"text": "$1 per ton"}).status_code == 422

    assert client.post(f"/api/rfps/{rfp_id}/reopen-prices").status_code == 200
    assert status_of(rfp_id) == "review_prices"
    assert client.put(f"/api/lanes/{lane['id']}/price", json={"price": 1234}).status_code == 200
    client.post(f"/api/rfps/{rfp_id}/approve-prices")
    body = {"intro": "Hi Maya,", "closing": "Best, the RFP team"}
    assert client.post(f"/api/rfps/{rfp_id}/approve-quote", json=body).status_code == 200

    sent = client.get(f"/api/rfps/{rfp_id}").json()["emails"][-1]["body"]
    assert sent.startswith("Hi Maya,") and sent.endswith("Best, the RFP team")
    assert f"{name}: route" in sent and "$1,234 per ton" in sent

    client.post(f"/api/rfps/{rfp_id}/customer-reply", json={"text": "We accept the proposal."})
    details = client.get(f"/api/rfps/{rfp_id}").json()["proposal"]["details"]
    assert next(d for d in details if d["lane"] == name)["price_per_ton"] == 1234


def test_a_step_cannot_run_twice():
    rfp_id = client.post("/api/rfps/sample").json()["id"]
    assert client.post(f"/api/rfps/{rfp_id}/approve-plan").status_code == 200
    assert client.post(f"/api/rfps/{rfp_id}/approve-plan").status_code == 409


def test_requirements_can_only_be_edited_during_plan_review():
    rfp_id = client.post("/api/rfps/sample").json()["id"]
    lane_id = client.get(f"/api/rfps/{rfp_id}").json()["lanes"][0]["id"]
    body = {"requirements": ["Fragile handling"]}
    assert client.put(f"/api/lanes/{lane_id}/requirements", json=body).status_code == 200
    client.post(f"/api/rfps/{rfp_id}/approve-plan")
    assert client.put(f"/api/lanes/{lane_id}/requirements", json=body).status_code == 409
