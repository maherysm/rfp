"""The RFP workflow. Each function is one agent step. A step ends by setting the RFP's status,
which tells the UI which human action is needed next:

  review_plan -> review_prices -> review_quote -> awaiting_customer -> (review_reply) -> won / lost
"""

import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ai
import db
import excel
import mock_pricing
import routing

TEAM_EMAIL = "rfp-team@carrier.example"
PRICING_EMAIL = "pricing@carrier.example"
DATA_FILE = Path(__file__).parent.parent / "data" / "Air_Freight_RFP_Mock_Data.xlsx"
TRANSIT_LEGS = excel.read_transit_table(DATA_FILE)


# ---------- helpers ----------

def log(rfp_id, agent, message, needs_human=False):
    """Record what an agent did; the UI's agent panel shows these events."""
    db.insert("events", rfp_id=rfp_id, agent=agent, message=message, needs_human=int(needs_human))


def wait_for_human(rfp_id, status, what):
    db.update("rfps", rfp_id, status=status)
    log(rfp_id, "Orchestrator", f"Waiting for a human: {what}", needs_human=True)


def claim(rfp_id, expected_status):
    """Move the RFP from the expected status to 'working' in one atomic UPDATE.
    Returns False if it was not in that status (e.g. a double click), so a step never runs twice."""
    _, changed = db.execute(
        "UPDATE rfps SET status = 'working' WHERE id = ? AND status = ?", (rfp_id, expected_status)
    )
    return changed == 1


def get_rfp(rfp_id):
    rows = db.query("SELECT * FROM rfps WHERE id = ?", (rfp_id,))
    return rows[0] if rows else None


def lanes_of(rfp_id):
    return db.query("SELECT * FROM lanes WHERE rfp_id = ? ORDER BY id", (rfp_id,))


def lane_name(lane):
    return f"{lane['origin']}-{lane['destination']}"


def send_email(rfp_id, direction, party, subject, body):
    """The 'mail server' is the emails table; the UI shows it as a mailbox."""
    db.insert("emails", rfp_id=rfp_id, direction=direction, party=party, subject=subject, body=body)


def route_lane(lane):
    plan = routing.plan_route(
        TRANSIT_LEGS, lane["origin"], lane["destination"], lane["requirements"], lane["max_days"]
    )
    db.update("lanes", lane["id"], **plan)


# ---------- step 1: read the RFP, extract requirements, plan routes ----------

def start_rfp(lanes, customer_email):
    rfp_id = db.insert("rfps", customer_email=customer_email, status="working")
    for lane in lanes:
        db.insert("lanes", rfp_id=rfp_id, **lane)
    log(rfp_id, "Intake Agent", f"Received an RFP with {len(lanes)} lanes from {customer_email}")

    lanes = lanes_of(rfp_id)
    log(rfp_id, "Requirements Agent", f"Reading {len(lanes)} shipper emails using {ai.mode()}")
    found = ai.extract_requirements({lane["id"]: lane["email"] for lane in lanes})
    for lane in lanes:
        lane["requirements"] = found[lane["id"]]
        db.update("lanes", lane["id"], requirements=lane["requirements"])
    special = sum(1 for lane in lanes if lane["requirements"])
    log(rfp_id, "Requirements Agent", f"{special} lanes need special handling")

    log(rfp_id, "Routing Agent", f"Finding routes on {len(TRANSIT_LEGS)} flight legs")
    for lane in lanes:
        route_lane(lane)
    with_issues = sum(1 for lane in lanes_of(rfp_id) if lane["issue"])
    log(rfp_id, "Routing Agent", f"Routed {len(lanes)} lanes; {with_issues} have issues to check")

    wait_for_human(rfp_id, "review_plan", "check requirements and routes, then approve the pricing request")
    return rfp_id


def update_requirements(lane, requirements):
    """A human corrected a lane's requirements, so plan its route again."""
    lane["requirements"] = requirements
    db.update("lanes", lane["id"], requirements=requirements)
    route_lane(lane)
    log(lane["rfp_id"], "Human", f"Set requirements for {lane_name(lane)}: {', '.join(requirements) or 'none'}")


ROUTE_FIELDS = ("route", "transit_days", "met", "unmet", "issue")


def use_alternative_route(lane):
    """A human chose the lane's other route option. The route it replaces becomes the alternative,
    so the choice can be undone."""
    current = {field: lane[field] for field in ROUTE_FIELDS}
    chosen = {field: lane["alternative"][field] for field in ROUTE_FIELDS}
    db.update("lanes", lane["id"], **chosen, alternative=current)
    dropped = ", ".join(chosen["unmet"]) or "nothing"
    log(lane["rfp_id"], "Human",
        f"Chose route {' > '.join(chosen['route'])} for {lane_name(lane)} "
        f"({chosen['transit_days']:g} days, not available: {dropped})")


def pricing_request_email(lanes):
    lines = ["Hi Pricing team,", "", "Please recommend a price per ton (USD) for each lane below,",
             "including the special services listed.", ""]
    for lane in lanes:
        if lane["route"]:
            services = ", ".join(lane["met"]) or "general cargo"
            lines.append(f"{lane_name(lane)}  {lane['tons']:g} t  via {' > '.join(lane['route'])}  ({services})")
    lines += ["", "Thanks,", "RFP Response Team"]
    return "\n".join(lines)


# ---------- step 2: ask the Pricing team and read their reply ----------

# Prices must be USD per ton. A reply line that says otherwise is not trusted, whatever number was read.
OTHER_CURRENCY = re.compile(
    r"[€£¥₹₩฿]|\b(?:HK|S|SG|A|AU|C|CA|NZ|NT|R|MX)\$"
    r"|\b(?:EUR|GBP|JPY|CNY|RMB|HKD|SGD|AUD|CAD|NZD|CHF|INR|THB|KRW|MYR|AED|MXN|BRL|COP)\b"
    r"|\b(?i:euros?|yen|yuan|renminbi|sterling|pesos?|reais)\b"
)
OTHER_UNIT = re.compile(
    r"(?:\bper\s+|/\s*|\ba\s+)(?:kgs?|kilos?|kilograms?|lbs?|pounds?|shipments?|containers?|pallets?|lane)\b"
    r"|\b(?:total|lump[- ]?sum|flat (?:fee|rate))\b",
    re.IGNORECASE,
)


def price_problem(lane, price, reply):
    """Why a price read from the Pricing team's reply can't be used for this lane, or None if it can."""
    if not (math.isfinite(price) and price > 0):
        return f"{price:g} is not a positive price"
    for line in reply.splitlines():
        if not any(f"{m[1]}-{m[2]}" == lane_name(lane) for m in ai.LANE_PATTERN.finditer(line)):
            continue
        text = ai.LANE_PATTERN.sub(" ", line)  # airport codes must not be mistaken for currency codes
        if found := OTHER_CURRENCY.search(text):
            return f"the reply uses another currency ({found[0]}), not USD"
        if found := OTHER_UNIT.search(text):
            return f"the reply is not per ton ({found[0].strip()})"
    return None


def request_pricing(rfp_id):
    lanes = [lane for lane in lanes_of(rfp_id) if lane["route"]]
    send_email(rfp_id, "out", PRICING_EMAIL, "Pricing request", pricing_request_email(lanes))
    log(rfp_id, "Pricing Agent", f"Emailed the Pricing team for {len(lanes)} lanes")

    reply = mock_pricing.pricing_team_reply(lanes, seed=rfp_id)
    send_email(rfp_id, "in", PRICING_EMAIL, "Re: Pricing request", reply)
    log(rfp_id, "Pricing Agent", f"Pricing team replied; reading prices using {ai.mode()}")

    prices = ai.parse_pricing_email(reply)
    for lane in lanes:
        price = prices.get(lane_name(lane))
        problem = price_problem(lane, price, reply) if price is not None else None
        if problem:
            log(rfp_id, "Pricing Agent", f"Ignored the price for {lane_name(lane)}: {problem}")
            price = None
        db.update("lanes", lane["id"], price=price)
    missing = missing_prices(rfp_id)
    log(rfp_id, "Pricing Agent", f"Found usable prices for {len(lanes) - len(missing)} of {len(lanes)} lanes")

    todo = f"enter the missing price for {', '.join(missing)}, then approve" if missing else "check the prices"
    wait_for_human(rfp_id, "review_prices", todo)


def set_price(lane, price):
    db.update("lanes", lane["id"], price=price)
    log(lane["rfp_id"], "Human", f"Set price for {lane_name(lane)} to ${price:,.0f}/ton")


def missing_prices(rfp_id):
    """Routed lanes that still need a usable (positive) price before the quote can be drafted."""
    return [lane_name(lane) for lane in lanes_of(rfp_id) if lane["route"] and (lane["price"] or 0) <= 0]


# ---------- step 3: draft the quote ----------
# The human may edit only the intro and closing. The lane details (routes, days, prices) are always
# rebuilt from the lanes table, so the email the customer gets matches what log_proposal saves.

QUOTE_INTRO = "Dear customer,\n\nThank you for your RFP. Our proposal for each lane:"
QUOTE_CLOSING = "Please reply to this email to accept the proposal.\n\nKind regards,\nRFP Response Team"


def quote_lane_details(lanes):
    lines = []
    for lane in lanes:
        if not lane["route"]:
            continue
        if lane["transit_days"] > lane["max_days"]:
            days = f"{lane['transit_days']:g} days, over your {lane['max_days']:g}-day maximum"
        else:
            days = f"{lane['transit_days']:g} days (your max {lane['max_days']:g})"
        lines.append(f"{lane_name(lane)}: route {' > '.join(lane['route'])}, {days}, ${lane['price']:,.0f} per ton")
        lines.append(f"    Special requirements met: {', '.join(lane['met']) or 'none requested'}")
        if lane["unmet"]:
            lines.append(f"    Not available: {', '.join(lane['unmet'])}")
    unserved = [lane_name(lane) for lane in lanes if not lane["route"]]
    if unserved:
        lines += ["", f"We cannot serve these lanes on our network: {', '.join(unserved)}"]
    return "\n".join(lines).strip("\n")


def quote_email(lanes, intro=QUOTE_INTRO, closing=QUOTE_CLOSING):
    parts = [intro.strip(), quote_lane_details(lanes), closing.strip()]
    return "\n\n".join(part for part in parts if part)


def draft_quote(rfp_id):
    db.update("rfps", rfp_id, quote=quote_email(lanes_of(rfp_id)))
    log(rfp_id, "Quote Agent", "Drafted the quote email")
    wait_for_human(rfp_id, "review_quote", "edit the quote's intro and closing if needed, then approve sending it")


def reopen_prices(rfp_id):
    """A human wants to change a price after the quote was drafted; prices are only edited in price review."""
    log(rfp_id, "Human", "Went back to price review")
    wait_for_human(rfp_id, "review_prices", "check the prices")


# ---------- step 4: send the quote and handle the customer's reply ----------

def send_quote(rfp_id, intro, closing):
    rfp = get_rfp(rfp_id)
    text = quote_email(lanes_of(rfp_id), intro, closing)
    db.update("rfps", rfp_id, quote=text)
    send_email(rfp_id, "out", rfp["customer_email"], "Your air freight proposal", text)
    log(rfp_id, "Quote Agent", f"Sent the quote to {rfp['customer_email']}")
    wait_for_human(rfp_id, "awaiting_customer", "the customer's reply (use the simulator)")


def handle_reply(rfp_id, text):
    rfp = get_rfp(rfp_id)
    send_email(rfp_id, "in", rfp["customer_email"], "Re: Your air freight proposal", text)
    decision = ai.classify_reply(text)
    log(rfp_id, "Customer Agent", f"Read the customer's reply using {ai.mode()}: {decision}")
    if decision == "unclear":
        wait_for_human(rfp_id, "review_reply", "the reply is unclear; decide if the customer accepted")
    else:
        close_rfp(rfp_id, decision)


def close_rfp(rfp_id, decision):
    if decision == "declined":
        db.update("rfps", rfp_id, status="lost")
        log(rfp_id, "Orchestrator", "Customer declined; RFP closed")
        return
    schedule_kickoff(rfp_id)
    log_proposal(rfp_id)
    db.update("rfps", rfp_id, status="won")


def schedule_kickoff(rfp_id):
    customer = get_rfp(rfp_id)["customer_email"]
    start = datetime.now(timezone.utc).replace(hour=15, minute=0, second=0, microsecond=0)
    start += timedelta(days=2)
    while start.weekday() >= 5:  # skip Saturday and Sunday
        start += timedelta(days=1)
    attendees = [customer, TEAM_EMAIL, PRICING_EMAIL]
    db.insert("meetings", rfp_id=rfp_id, title="Contract kickoff", starts_at=start.isoformat(),
              attendees=attendees)
    when = start.strftime("%A %d %B at %H:%M UTC")
    send_email(rfp_id, "out", ", ".join(attendees), "Invitation: contract kickoff",
               f"Thank you for accepting our proposal. Let's kick off on {when}.")
    log(rfp_id, "Customer Agent", f"Scheduled the kickoff meeting for {when}")


def log_proposal(rfp_id):
    quoted = [lane for lane in lanes_of(rfp_id) if lane["route"] and lane["price"] is not None]
    details = [
        {"lane": lane_name(lane), "route": lane["route"], "tons": lane["tons"],
         "transit_days": lane["transit_days"], "max_days": lane["max_days"],
         "price_per_ton": lane["price"], "met": lane["met"], "unmet": lane["unmet"]}
        for lane in quoted
    ]
    total_tons = sum(lane["tons"] for lane in quoted)
    total_value = sum(lane["tons"] * lane["price"] for lane in quoted)
    db.insert("proposals", rfp_id=rfp_id, customer_email=get_rfp(rfp_id)["customer_email"],
              lane_count=len(quoted), total_tons=total_tons, total_value=total_value, details=details)
    log(rfp_id, "Orchestrator", f"Logged the proposal to the database: {len(quoted)} lanes, ${total_value:,.0f}")
