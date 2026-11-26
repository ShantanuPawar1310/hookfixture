"""Run from the repository root after installation: python examples/idempotent_consumer.py."""

from hookfixture import create_scenario

events = [
    {"id": "evt_demo_paid", "type": "invoice.paid", "data": {"amount_minor": 1500}},
    {"id": "evt_demo_refund", "type": "invoice.refunded", "data": {"amount_minor": 500}},
]
scenario = create_scenario(events, copies=3, order="shuffle", seed=42)
seen = set()
balance = 0
for delivery in scenario.deliveries:
    event = delivery.event
    if event["id"] in seen:
        continue
    seen.add(event["id"])
    amount = event["data"]["amount_minor"]
    balance += amount if event["type"] == "invoice.paid" else -amount

assert balance == 1000, balance
print(f"{len(scenario.deliveries)} deliveries; {len(seen)} unique events; balance={balance} minor units")

# This in-memory example demonstrates event identity only. A production consumer
# needs transactional, durable idempotency storage and provider verification.
