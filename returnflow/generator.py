"""Fixed-seed generation of a complete, policy-driven returns workflow."""

from __future__ import annotations

import random
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

from returnflow.schema import TABLE_ORDER

SEED = 20261022
AS_OF_DATE = date(2026, 12, 31)
SOURCE_MANIFEST = {
    "provenance": "Entirely synthetic records; no external or personal data used.",
    "external_sources": [],
    "seed_default": SEED,
    "generator_version": "1.0.0",
    "policy_effective_period": ["2026-01-01", "2026-12-31"],
}

POLICIES = (
    ("APPAREL", 30, False, 0),
    ("HOME", 45, False, 0),
    ("ELECTRONICS", 30, False, 500),
    ("BEAUTY", 14, True, 0),
)

REASONS = (
    "CHANGED_MIND", "WRONG_ITEM", "DAMAGED", "DEFECTIVE",
    "NOT_AS_DESCRIBED", "SIZE_ISSUE",
)


def _iso_day(value: date) -> str:
    return value.isoformat()


def _iso_timestamp(value: date, hour: int = 12) -> str:
    return datetime(value.year, value.month, value.day, hour, tzinfo=timezone.utc).isoformat()


def _line_refund(
    order_line: dict[str, Any],
    quantity: int,
    reason: str,
    fee_basis_points: int,
) -> tuple[int, int]:
    """Return (gross paid allocation, restocking fee) in integer cents."""
    qty = order_line["quantity"]
    merchandise = order_line["unit_price_cents"] * quantity
    discount = round(order_line["discount_cents"] * quantity / qty)
    tax = round(order_line["tax_cents"] * quantity / qty)
    gross_paid = merchandise - discount + tax
    fee_rate = 0 if reason in {"DAMAGED", "DEFECTIVE", "WRONG_ITEM"} else fee_basis_points
    fee = round(max(0, merchandise - discount) * fee_rate / 10_000)
    return max(0, gross_paid - fee), fee


def generate_dataset(
    orders_count: int = 300,
    requests_count: int = 50,
    return_lines_count: int = 80,
    seed: int = SEED,
) -> dict[str, Any]:
    """Generate valid baseline rows, then inject five documented edge cases."""
    if orders_count < 1:
        raise ValueError("orders_count must be positive")
    if requests_count < 5 or requests_count > orders_count:
        raise ValueError("requests_count must be between 5 and orders_count")
    if not requests_count <= return_lines_count <= requests_count * 4:
        raise ValueError("return_lines_count must be between requests_count and 4x requests_count")

    rng = random.Random(seed)
    data: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLE_ORDER}
    truth: list[dict[str, Any]] = []
    counters = Counter()

    def ident(prefix: str, key: str, width: int = 6) -> str:
        counters[key] += 1
        return f"{prefix}-2026-{counters[key]:0{width}d}"

    for index, (category, days, final_sale, fee_bps) in enumerate(POLICIES, start=1):
        data["return_policies"].append({
            "policy_id": f"POL-2026-{index:02d}",
            "category": category,
            "effective_from": "2026-01-01",
            "effective_to": "2026-12-31",
            "return_window_days": days,
            "final_sale": final_sale,
            "restocking_fee_basis_points": fee_bps,
            "policy_version": "2026.1",
        })
    policy_by_category = {row["category"]: row for row in data["return_policies"]}
    policies_by_id = {row["policy_id"]: row for row in data["return_policies"]}

    customer_count = max(10, min(orders_count, round(orders_count * 0.62)))
    for number in range(1, customer_count + 1):
        created = date(2025, 1, 1) + timedelta(days=rng.randrange(365))
        data["customers"].append({
            "customer_id": f"CUS-2026-{number:06d}",
            "created_at": _iso_day(created),
            "region": rng.choice(("NORTH", "SOUTH", "EAST", "WEST", "CENTRAL")),
            "segment": rng.choices(("STANDARD", "LOYAL", "NEW"), (65, 25, 10))[0],
        })

    customer_ids = [row["customer_id"] for row in data["customers"]]
    orders_by_id: dict[str, dict[str, Any]] = {}
    lines_by_id: dict[str, dict[str, Any]] = {}
    order_lines_by_order: dict[str, list[dict[str, Any]]] = {}
    for order_number in range(1, orders_count + 1):
        order_id = f"ORD-2026-{order_number:06d}"
        order_date = date(2026, 1, 1) + timedelta(days=rng.randrange(280))
        line_rows = []
        subtotal = discount_total = tax_total = 0
        for line_number in range(1, rng.randint(2, 4) + 1):
            category = rng.choices(
                ("APPAREL", "HOME", "ELECTRONICS", "BEAUTY"), (35, 25, 25, 15)
            )[0]
            policy = policy_by_category[category]
            quantity = rng.randint(1, 5)
            unit_price = rng.randrange(1_000, 30_001, 100)
            line_subtotal = quantity * unit_price
            discount = line_subtotal * rng.choice((0, 0, 500, 1000)) // 10_000
            tax = (line_subtotal - discount) * 825 // 10_000
            line_id = f"OL-{order_number:06d}-{line_number:02d}"
            line = {
                "order_line_id": line_id,
                "order_id": order_id,
                "policy_id": policy["policy_id"],
                "sku": f"SKU-{category[:3]}-{rng.randrange(1, 401):04d}",
                "category": category,
                "quantity": quantity,
                "unit_price_cents": unit_price,
                "discount_cents": discount,
                "tax_cents": tax,
                "line_paid_cents": line_subtotal - discount + tax,
                "return_window_days": policy["return_window_days"],
                "final_sale": policy["final_sale"] or rng.random() < 0.04,
            }
            line_rows.append(line)
            lines_by_id[line_id] = line
            data["order_lines"].append(line)
            subtotal += line_subtotal
            discount_total += discount
            tax_total += tax
        shipping = rng.choice((0, 499, 699))
        order = {
            "order_id": order_id,
            "customer_id": rng.choice(customer_ids),
            "order_date": _iso_day(order_date),
            "channel": rng.choices(("WEB", "APP", "STORE"), (55, 30, 15))[0],
            "currency": "USD",
            "subtotal_cents": subtotal,
            "discount_cents": discount_total,
            "tax_cents": tax_total,
            "shipping_fee_cents": shipping,
            "total_paid_cents": subtotal - discount_total + tax_total + shipping,
            "status": "DELIVERED",
        }
        data["orders"].append(order)
        orders_by_id[order_id] = order
        order_lines_by_order[order_id] = line_rows

    chosen_orders = rng.sample(data["orders"], requests_count)
    line_total, extra_lines = divmod(return_lines_count, requests_count)
    request_line_pairs: dict[str, list[dict[str, Any]]] = {}
    for request_index, order in enumerate(chosen_orders, start=1):
        rma_id = f"RMA-2026-{request_index:06d}"
        order_lines = order_lines_by_order[order["order_id"]]
        count = line_total + (request_index <= extra_lines)
        chosen_lines = rng.sample(order_lines, count)
        request_date = date.fromisoformat(order["order_date"]) + timedelta(days=rng.randint(1, 70))
        override = rng.random() < 0.04
        data["return_requests"].append({
            "rma_id": rma_id,
            "order_id": order["order_id"],
            "customer_id": order["customer_id"],
            "requested_at": _iso_day(request_date),
            "reason": rng.choices(REASONS, (28, 12, 12, 12, 16, 20))[0],
            "request_type": rng.choices(("REFUND", "EXCHANGE"), (88, 12))[0],
            "override_approved": override,
            "status": "REJECTED",
        })
        request_line_pairs[rma_id] = []
        for line_index, line in enumerate(chosen_lines, start=1):
            requested_qty = rng.randint(1, line["quantity"])
            if requested_qty < line["quantity"]:
                truth.append({
                    "entity_type": "RETURN_LINE",
                    "entity_id": f"RMAL-{rma_id}-{line_index:02d}",
                    "issue_type": "PARTIAL_RETURN",
                    "expected_outcome": f"Requested {requested_qty} of {line['quantity']} purchased",
                    "severity": "INFO",
                })
            request_line_pairs[rma_id].append({
                "return_line_id": f"RMAL-{rma_id}-{line_index:02d}",
                "rma_id": rma_id,
                "order_line_id": line["order_line_id"],
                "requested_qty": requested_qty,
                "approved_qty": 0,
                "eligibility_status": "REJECTED",
                "decision_reason": "PENDING",
            })

    request_by_id = {row["rma_id"]: row for row in data["return_requests"]}
    # Guarantee the no-override, post-window policy boundary case.
    late_rma = next(
        rma for rma, rows in request_line_pairs.items()
        if any(not lines_by_id[row["order_line_id"]]["final_sale"] for row in rows)
    )
    late_request = request_by_id[late_rma]
    late_order = orders_by_id[late_request["order_id"]]
    longest_window = max(
        lines_by_id[row["order_line_id"]]["return_window_days"]
        for row in request_line_pairs[late_rma]
        if not lines_by_id[row["order_line_id"]]["final_sale"]
    )
    late_request["requested_at"] = _iso_day(
        date.fromisoformat(late_order["order_date"]) + timedelta(days=longest_window + 10)
    )
    late_request["override_approved"] = False
    truth.append({
        "entity_type": "RETURN_REQUEST",
        "entity_id": late_rma,
        "issue_type": "LATE_WITHOUT_OVERRIDE",
        "expected_outcome": "Reject every non-final-sale line outside its effective return window",
        "severity": "HIGH",
    })

    # Establish line-level eligibility before creating any dependent records.
    for request in data["return_requests"]:
        order = orders_by_id[request["order_id"]]
        for line in request_line_pairs[request["rma_id"]]:
            purchased = lines_by_id[line["order_line_id"]]
            age_days = (
                date.fromisoformat(request["requested_at"]) - date.fromisoformat(order["order_date"])
            ).days
            if purchased["final_sale"]:
                reason, approved = "CATEGORY_EXCLUDED_FINAL_SALE", 0
            elif age_days > purchased["return_window_days"] and not request["override_approved"]:
                reason, approved = "OUTSIDE_RETURN_WINDOW", 0
            else:
                reason = "ELIGIBLE"
                approved = line["requested_qty"]
            line["approved_qty"] = approved
            line["eligibility_status"] = (
                "APPROVED" if approved == line["requested_qty"] else
                "PARTIALLY_APPROVED" if approved else "REJECTED"
            )
            line["decision_reason"] = reason
            if reason == "CATEGORY_EXCLUDED_FINAL_SALE":
                truth.append({
                    "entity_type": "RETURN_LINE",
                    "entity_id": line["return_line_id"],
                    "issue_type": "CATEGORY_EXCLUSION",
                    "expected_outcome": "Reject final-sale item",
                    "severity": "INFO",
                })
            elif reason == "OUTSIDE_RETURN_WINDOW":
                truth.append({
                    "entity_type": "RETURN_LINE",
                    "entity_id": line["return_line_id"],
                    "issue_type": "LATE_NO_OVERRIDE",
                    "expected_outcome": "Reject: request is outside the policy window",
                    "severity": "HIGH",
                })

    # Inject a clearly labelled quantity overage; authorize no more than purchased.
    over_qty_line = next(
        line for rows in request_line_pairs.values() for line in rows
        if line["approved_qty"] > 0 and line["requested_qty"] == lines_by_id[line["order_line_id"]]["quantity"]
    )
    purchased_qty = lines_by_id[over_qty_line["order_line_id"]]["quantity"]
    over_qty_line["requested_qty"] = purchased_qty + 1
    over_qty_line["approved_qty"] = purchased_qty
    over_qty_line["eligibility_status"] = "PARTIALLY_APPROVED"
    over_qty_line["decision_reason"] = "QUANTITY_EXCEEDED_CAPPED"
    truth.append({
        "entity_type": "RETURN_LINE",
        "entity_id": over_qty_line["return_line_id"],
        "issue_type": "RETURN_QTY_EXCEEDS_PURCHASE",
        "expected_outcome": f"Cap approval at purchased quantity {purchased_qty}",
        "severity": "HIGH",
    })

    requests_with_approval = set()
    for request in data["return_requests"]:
        rows = request_line_pairs[request["rma_id"]]
        approved_sum = sum(row["approved_qty"] for row in rows)
        requested_sum = sum(row["requested_qty"] for row in rows)
        request["status"] = (
            "REJECTED" if approved_sum == 0 else
            "APPROVED" if approved_sum == requested_sum else "PARTIALLY_APPROVED"
        )
        if approved_sum:
            requests_with_approval.add(request["rma_id"])
        data["return_lines"].extend({k: v for k, v in row.items() if not k.startswith("_")} for row in rows)
        data["return_authorizations"].append({
            "authorization_id": f"AUTH-2026-{len(data['return_authorizations']) + 1:06d}",
            "rma_id": request["rma_id"],
            "authorized_at": _iso_timestamp(date.fromisoformat(request["requested_at"]), 13),
            "status": {
                "APPROVED": "AUTHORIZED",
                "PARTIALLY_APPROVED": "PARTIALLY_AUTHORIZED",
                "REJECTED": "REJECTED",
            }[request["status"]],
            "override_used": request["override_approved"],
        })

    # Missing-shipment case is an explicit absence with a truth label, not a broken FK.
    missing_shipment_rma = next(
        request["rma_id"] for request in data["return_requests"]
        if request["rma_id"] in requests_with_approval and request["rma_id"] != late_rma
    )
    truth.append({
        "entity_type": "RETURN_REQUEST",
        "entity_id": missing_shipment_rma,
        "issue_type": "MISSING_RETURN_SHIPMENT",
        "expected_outcome": "Keep approved return open; do not inspect, refund, or move inventory",
        "severity": "MEDIUM",
    })

    line_rows_by_request: dict[str, list[dict[str, Any]]] = {}
    for line in data["return_lines"]:
        line_rows_by_request.setdefault(line["rma_id"], []).append(line)
    inspections_by_line: dict[str, dict[str, Any]] = {}
    refund_rows_by_line: dict[str, list[dict[str, Any]]] = {}
    disposition_rows_by_line: dict[str, dict[str, Any]] = {}
    event_specs: list[tuple[str, str | None, str, str, str, date, str]] = []

    for request in data["return_requests"]:
        rma_id = request["rma_id"]
        request_date = date.fromisoformat(request["requested_at"])
        event_specs.append((rma_id, None, "REQUEST_SUBMITTED", "", "SUBMITTED", request_date, "CUSTOMER"))
        for line in line_rows_by_request[rma_id]:
            event_specs.append((
                rma_id, line["return_line_id"], "ELIGIBILITY_DECIDED", "PENDING",
                line["eligibility_status"], request_date, "POLICY_ENGINE",
            ))
        auth = next(row for row in data["return_authorizations"] if row["rma_id"] == rma_id)
        event_specs.append((
            rma_id, None, "AUTHORIZATION_DECIDED", "PENDING", auth["status"],
            request_date, "RETURNS_OPERATOR",
        ))
        if rma_id not in requests_with_approval or rma_id == missing_shipment_rma:
            continue
        shipment_day = request_date + timedelta(days=rng.randint(1, 4))
        received_day = shipment_day + timedelta(days=rng.randint(1, 7))
        shipment = {
            "shipment_id": ident("RTS", "shipment"),
            "rma_id": rma_id,
            "shipped_at": _iso_day(shipment_day),
            "received_at": _iso_day(received_day),
            "status": "RECEIVED",
            "carrier": rng.choice(("UPS", "USPS", "FEDEX", "DHL")),
        }
        data["return_shipments"].append(shipment)
        event_specs.append((rma_id, None, "SHIPMENT_DISPATCHED", "AUTHORIZED", "IN_TRANSIT", shipment_day, "CARRIER"))
        event_specs.append((rma_id, None, "SHIPMENT_RECEIVED", "IN_TRANSIT", "RECEIVED", received_day, "WAREHOUSE"))

        approved_lines = [line for line in line_rows_by_request[rma_id] if line["approved_qty"] > 0]
        for line in approved_lines:
            purchased_line = lines_by_id[line["order_line_id"]]
            reason = request["reason"]
            condition_weights = (
                (25, 15, 38, 22)
                if reason in {"DAMAGED", "DEFECTIVE"}
                else (66, 20, 10, 4)
            )
            condition = rng.choices(
                ("GOOD", "OPEN_BOX", "DAMAGED", "DEFECTIVE"), condition_weights
            )[0]
            inspection_day = received_day + timedelta(days=rng.randint(0, 2))
            inspection = {
                "inspection_id": ident("INSP", "inspection"),
                "shipment_id": shipment["shipment_id"],
                "return_line_id": line["return_line_id"],
                "inspected_at": _iso_day(inspection_day),
                "condition": condition,
                "notes_code": f"{condition}_{reason}",
            }
            data["inspections"].append(inspection)
            inspections_by_line[line["return_line_id"]] = inspection
            event_specs.append((
                rma_id, line["return_line_id"], "INSPECTION_COMPLETED", "RECEIVED",
                condition, inspection_day, "INSPECTOR",
            ))

            decision = {
                "GOOD": ("RESTOCK", "RESTOCKED", "SELLABLE"),
                "OPEN_BOX": ("REFURBISH", "REFURBISHMENT_QUEUE", "OPEN_BOX"),
                "DAMAGED": ("QUARANTINE", "QUARANTINED", "DAMAGE_REVIEW"),
                "DEFECTIVE": ("SCRAP", "SCRAPPED", "NON_REPAIRABLE"),
            }[condition]
            disposition_day = inspection_day + timedelta(days=1)
            disposition = {
                "disposition_id": ident("DSP", "disposition"),
                "inspection_id": inspection["inspection_id"],
                "return_line_id": line["return_line_id"],
                "decision": decision[0],
                "quantity": line["approved_qty"],
                "decided_at": _iso_day(disposition_day),
                "inventory_movement": decision[1],
                "reason_code": decision[2],
            }
            data["inventory_dispositions"].append(disposition)
            disposition_rows_by_line[line["return_line_id"]] = disposition
            event_specs.append((
                rma_id, line["return_line_id"], "INVENTORY_DISPOSITION", "INSPECTED",
                decision[0], disposition_day, "WAREHOUSE_OPERATOR",
            ))

            amount, fee = _line_refund(
                purchased_line,
                line["approved_qty"],
                reason,
                policies_by_id[purchased_line["policy_id"]]["restocking_fee_basis_points"],
            )
            attempt_id = ident("REF", "refund")
            refund = {
                "refund_id": attempt_id,
                "rma_id": rma_id,
                "return_line_id": line["return_line_id"],
                "attempt_number": 1,
                "attempted_at": _iso_day(inspection_day + timedelta(days=1)),
                "refund_method": "EXCHANGE_CREDIT" if request["request_type"] == "EXCHANGE" else "ORIGINAL_PAYMENT",
                "requested_amount_cents": amount,
                "approved_amount_cents": amount,
                "status": "CREDIT_ISSUED" if request["request_type"] == "EXCHANGE" else "ISSUED",
                "blocked_reason": "",
            }
            data["refunds"].append(refund)
            refund_rows_by_line[line["return_line_id"]] = [refund]
            event_specs.append((
                rma_id, line["return_line_id"], "REFUND_ISSUED", "PENDING",
                refund["status"], inspection_day + timedelta(days=1), "PAYMENTS_SERVICE",
            ))
            # Retain derived fee with the decision label rather than injecting it into inputs.
            if fee:
                truth.append({
                    "entity_type": "RETURN_LINE",
                    "entity_id": line["return_line_id"],
                    "issue_type": "RESTOCKING_FEE_APPLIED",
                    "expected_outcome": f"Deduct {fee} cents from refund",
                    "severity": "INFO",
                })

    # Force one inspectable line to be sellable so the early-restock case is guaranteed.
    early_line_id = next(iter(inspections_by_line))
    early_inspection = inspections_by_line[early_line_id]
    early_inspection["condition"] = "GOOD"
    early_inspection["notes_code"] = "GOOD_EDGE_CASE"
    early_disposition = disposition_rows_by_line[early_line_id]
    early_disposition["decision"] = "RESTOCK"
    early_disposition["inventory_movement"] = "NO_MOVEMENT"
    early_disposition["reason_code"] = "BLOCKED_PRE_INSPECTION"
    early_disposition["decided_at"] = _iso_day(
        date.fromisoformat(early_inspection["inspected_at"]) - timedelta(days=1)
    )
    early_rma_id = next(
        line["rma_id"] for line in data["return_lines"]
        if line["return_line_id"] == early_line_id
    )
    for event_index, spec in enumerate(event_specs):
        if (
            spec[0] == early_rma_id
            and spec[1] == early_line_id
            and spec[2] == "INVENTORY_DISPOSITION"
        ):
            event_specs[event_index] = (
                spec[0], spec[1], spec[2], spec[3], spec[4],
                date.fromisoformat(early_disposition["decided_at"]), spec[6],
            )
            break
    truth.append({
        "entity_type": "INVENTORY_DISPOSITION",
        "entity_id": early_disposition["disposition_id"],
        "issue_type": "RESTOCK_BEFORE_INSPECTION",
        "expected_outcome": "Flag and hold inventory movement until inspection is complete",
        "severity": "CRITICAL",
    })

    # Inject an over-limit payment attempt; the payout is blocked and remains zero.
    over_refund_line_id = next(iter(refund_rows_by_line))
    over_refund = refund_rows_by_line[over_refund_line_id][0]
    over_refund["requested_amount_cents"] = (
        orders_by_id[request_by_id[over_refund["rma_id"]]["order_id"]]["total_paid_cents"] + 1
    )
    over_refund["approved_amount_cents"] = 0
    over_refund["status"] = "BLOCKED_OVER_REFUND"
    over_refund["blocked_reason"] = "EXCEEDS_ORDER_PAID_AMOUNT"
    truth.append({
        "entity_type": "REFUND",
        "entity_id": over_refund["refund_id"],
        "issue_type": "REFUND_EXCEEDS_PAID_AMOUNT",
        "expected_outcome": "Block attempt; approve zero cents",
        "severity": "CRITICAL",
    })
    for index, spec in enumerate(event_specs):
        if spec[0] == over_refund["rma_id"] and spec[1] == over_refund_line_id and spec[2] == "REFUND_ISSUED":
            event_specs[index] = (
                spec[0], spec[1], "REFUND_BLOCKED", "PENDING", "BLOCKED_OVER_REFUND",
                spec[5], "PAYMENTS_SERVICE",
            )
            break

    # Add a second attempt for a successful line; idempotency blocks the duplicate.
    duplicate_line_id = next(
        line_id for line_id in refund_rows_by_line if line_id != over_refund_line_id
    )
    original_refund = refund_rows_by_line[duplicate_line_id][0]
    duplicate = dict(original_refund)
    duplicate.update({
        "refund_id": ident("REF", "refund"),
        "attempt_number": 2,
        "status": "BLOCKED_DUPLICATE",
        "approved_amount_cents": 0,
        "blocked_reason": "DUPLICATE_PAYOUT_ATTEMPT",
    })
    data["refunds"].append(duplicate)
    truth.append({
        "entity_type": "REFUND",
        "entity_id": duplicate["refund_id"],
        "issue_type": "DUPLICATE_REFUND_ATTEMPT",
        "expected_outcome": "Block second attempt; do not create a second payout",
        "severity": "CRITICAL",
    })
    event_specs.append((
        duplicate["rma_id"], duplicate_line_id, "REFUND_BLOCKED", "ISSUED",
        "BLOCKED_DUPLICATE", date.fromisoformat(duplicate["attempted_at"]), "PAYMENTS_SERVICE",
    ))

    for event_index, (rma_id, line_id, event_type, from_state, to_state, day, actor) in enumerate(event_specs, start=1):
        data["workflow_events"].append({
            "event_id": f"EVT-2026-{event_index:08d}",
            "rma_id": rma_id,
            "return_line_id": line_id,
            "event_type": event_type,
            "from_state": from_state,
            "to_state": to_state,
            "event_at": _iso_timestamp(day),
            "actor": actor,
        })

    # Every return line gets an expected business decision in this separate label file.
    decision_types = {
        "CATEGORY_EXCLUDED_FINAL_SALE": "CATEGORY_EXCLUSION",
        "OUTSIDE_RETURN_WINDOW": "LATE_NO_OVERRIDE",
        "QUANTITY_EXCEEDED_CAPPED": "RETURN_QTY_EXCEEDS_PURCHASE",
    }
    truth_ids = {(row["entity_type"], row["entity_id"], row["issue_type"]) for row in truth}
    for line in data["return_lines"]:
        issue = decision_types.get(line["decision_reason"], line["eligibility_status"])
        expected = (
            f"approved_qty={line['approved_qty']}; status={line['eligibility_status']}; "
            f"reason={line['decision_reason']}"
        )
        label = {
            "entity_type": "RETURN_LINE",
            "entity_id": line["return_line_id"],
            "issue_type": f"EXPECTED_{issue}",
            "expected_outcome": expected,
            "severity": "INFO",
        }
        key = (label["entity_type"], label["entity_id"], label["issue_type"])
        if key not in truth_ids:
            truth.append(label)
            truth_ids.add(key)

    return {
        "tables": data,
        "ground_truth": [
            {"ground_truth_id": f"GT-{i:06d}", **row}
            for i, row in enumerate(truth, start=1)
        ],
        "seed": seed,
        "counts": {name: len(data[name]) for name in TABLE_ORDER},
        "as_of_date": _iso_day(AS_OF_DATE),
    }
