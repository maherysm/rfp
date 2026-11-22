"""Stand-in for the Pricing team: answers a pricing request with an unstructured email."""

import random

SURCHARGE_PER_TON = {
    "Temperature controlled (2-8 C)": 650,
    "Dangerous goods": 900,
    "High-value security": 500,
    "Fragile handling": 300,
    "Oversized cargo": 700,
}

# Varied wording, like a real person writing the email.
TEMPLATES = [
    "{origin}-{destination}: ${price:,} per ton",
    "For {origin} to {destination} we recommend ${price:,}/ton including the requested services.",
    "{origin}-{destination} - suggest ${price:,} a ton",
]


def pricing_team_reply(lanes, seed):
    random_gen = random.Random(seed)
    # Leave one lane unpriced so a human has to step in.
    unpriced = random_gen.choice(lanes) if lanes else None

    lines = ["Hi team,", "", "Here are our recommendations:", ""]
    for lane in lanes:
        if lane is unpriced:
            lines.append(f"{lane['origin']}-{lane['destination']}: still checking capacity, will revert.")
            continue
        connections = len(lane["route"]) - 2
        price = 2000 + 400 * connections + sum(SURCHARGE_PER_TON[r] for r in lane["met"])
        price = int(round(price * random_gen.uniform(0.9, 1.1), -1))
        template = random_gen.choice(TEMPLATES)
        lines.append(template.format(origin=lane["origin"], destination=lane["destination"], price=price))
    lines += ["", "Rates valid for 30 days.", "Priya, Pricing team"]
    return "\n".join(lines)
