"""HTTP API used by the React app. Run with: uvicorn main:app --reload"""

from typing import Literal

from fastapi import FastAPI, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

import ai
import db
import excel
import workflow

app = FastAPI(title="RFP Copilot")
db.init()


def find_rfp(rfp_id):
    rfp = workflow.get_rfp(rfp_id)
    if rfp is None:
        raise HTTPException(404, "RFP not found")
    return rfp


def find_lane(lane_id, required_status):
    rows = db.query("SELECT * FROM lanes WHERE id = ?", (lane_id,))
    if not rows:
        raise HTTPException(404, "Lane not found")
    if find_rfp(rows[0]["rfp_id"])["status"] != required_status:
        raise HTTPException(409, "This lane can't be edited at this stage")
    return rows[0]


def run_step(rfp_id, expected_status, step, *args):
    """Run a workflow step only if the RFP is waiting for it."""
    find_rfp(rfp_id)
    if not workflow.claim(rfp_id, expected_status):
        raise HTTPException(409, f"The RFP is not waiting for '{expected_status}'. Refresh the page.")
    try:
        step(rfp_id, *args)
    except Exception:
        db.update("rfps", rfp_id, status=expected_status)  # let the user retry
        raise
    return {"ok": True}


# ---------- reading ----------

@app.get("/api/rfps")
def list_rfps():
    return db.query("SELECT id, customer_email, status, created_at FROM rfps ORDER BY id DESC")


@app.get("/api/rfps/{rfp_id}")
def get_rfp(rfp_id: int):
    rfp = find_rfp(rfp_id)
    lanes = workflow.lanes_of(rfp_id)
    proposals = db.query("SELECT * FROM proposals WHERE rfp_id = ?", (rfp_id,))
    meetings = db.query("SELECT * FROM meetings WHERE rfp_id = ?", (rfp_id,))
    return {
        **rfp,
        "lanes": lanes,
        "emails": db.query("SELECT * FROM emails WHERE rfp_id = ? ORDER BY id", (rfp_id,)),
        "pricing_draft": workflow.pricing_request_email(lanes) if rfp["status"] == "review_plan" else None,
        "quote_draft": {
            "intro": workflow.QUOTE_INTRO,
            "lane_details": workflow.quote_lane_details(lanes),
            "closing": workflow.QUOTE_CLOSING,
        } if rfp["status"] == "review_quote" else None,
        "missing_prices": workflow.missing_prices(rfp_id),
        "proposal": proposals[0] if proposals else None,
        "meeting": meetings[0] if meetings else None,
    }


@app.get("/api/rfps/{rfp_id}/events")
def list_events(rfp_id: int):
    return db.query("SELECT * FROM events WHERE rfp_id = ? ORDER BY id", (rfp_id,))


# ---------- creating an RFP ----------

@app.post("/api/rfps/sample")
def create_sample():
    lanes = excel.read_rfp(workflow.DATA_FILE)
    return {"id": workflow.start_rfp(lanes, "maya@shipper.example")}


@app.post("/api/rfps")
def upload_rfp(file: UploadFile, customer_email: str = Form(...)):
    try:
        lanes = excel.read_rfp(file.file.read())
    except Exception as error:
        raise HTTPException(400, f"Could not read the RFP spreadsheet: {error}")
    if not lanes:
        raise HTTPException(400, "The spreadsheet has no lanes")
    return {"id": workflow.start_rfp(lanes, customer_email)}


# ---------- human edits ----------

class RequirementsIn(BaseModel):
    requirements: list[str]


class PriceIn(BaseModel):
    price: float = Field(gt=0)


class RouteIn(BaseModel):
    route: list[str]


@app.put("/api/lanes/{lane_id}/requirements")
def set_requirements(lane_id: int, body: RequirementsIn):
    lane = find_lane(lane_id, "review_plan")
    unknown = set(body.requirements) - set(ai.REQUIREMENTS)
    if unknown:
        raise HTTPException(400, f"Unknown requirements: {unknown}")
    workflow.update_requirements(lane, body.requirements)
    return {"ok": True}


@app.put("/api/lanes/{lane_id}/route")
def choose_route(lane_id: int, body: RouteIn):
    """Switch the lane to its alternative route. The body names the route wanted, so a repeated
    click or a stale page can't silently swap back to the other option."""
    lane = find_lane(lane_id, "review_plan")
    if lane["route"] == body.route:
        return {"ok": True}
    if not lane["alternative"] or lane["alternative"]["route"] != body.route:
        raise HTTPException(409, "That route is not an option for this lane. Refresh the page.")
    workflow.use_alternative_route(lane)
    return {"ok": True}


@app.put("/api/lanes/{lane_id}/price")
def set_price(lane_id: int, body: PriceIn):
    workflow.set_price(find_lane(lane_id, "review_prices"), body.price)
    return {"ok": True}


# ---------- human approvals: each one starts the next agent step ----------

class QuoteIn(BaseModel):
    """Only the free text around the lane details; prices can't be changed here."""
    intro: str = Field(min_length=1)
    closing: str = Field(min_length=1)


class ReplyIn(BaseModel):
    text: str = Field(min_length=1)


class DecisionIn(BaseModel):
    decision: Literal["accepted", "declined"]


@app.post("/api/rfps/{rfp_id}/approve-plan")
def approve_plan(rfp_id: int):
    return run_step(rfp_id, "review_plan", workflow.request_pricing)


@app.post("/api/rfps/{rfp_id}/approve-prices")
def approve_prices(rfp_id: int):
    missing = workflow.missing_prices(rfp_id)
    if missing:
        raise HTTPException(400, f"Enter a positive price for: {', '.join(missing)}")
    return run_step(rfp_id, "review_prices", workflow.draft_quote)


@app.post("/api/rfps/{rfp_id}/approve-quote")
def approve_quote(rfp_id: int, body: QuoteIn):
    return run_step(rfp_id, "review_quote", workflow.send_quote, body.intro, body.closing)


@app.post("/api/rfps/{rfp_id}/reopen-prices")
def reopen_prices(rfp_id: int):
    return run_step(rfp_id, "review_quote", workflow.reopen_prices)


@app.post("/api/rfps/{rfp_id}/customer-reply")
def customer_reply(rfp_id: int, body: ReplyIn):
    return run_step(rfp_id, "awaiting_customer", workflow.handle_reply, body.text)


@app.post("/api/rfps/{rfp_id}/decide")
def decide(rfp_id: int, body: DecisionIn):
    return run_step(rfp_id, "review_reply", workflow.close_rfp, body.decision)
