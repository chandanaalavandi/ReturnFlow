"""Relational, policy, lifecycle, and reconciliation checks."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from returnflow.schema import ENUMS, FOREIGN_KEYS, PRIMARY_KEYS, TABLE_COLUMNS, TABLE_ORDER


def validate_dataset(dataset: dict[str, Any]) -> dict[str, Any]:
    tables = dataset["tables"]
    truth = dataset["ground_truth"]
    errors: list[str] = []
    expected_exceptions: list[str] = []
    truth_types = {row["issue_type"] for row in truth}
    truth_entities = {(row["entity_type"], row["entity_id"], row["issue_type"]) for row in truth}

    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    ids_by_table: dict[str, set[str]] = {}
    rows_by_table: dict[str, dict[str, dict[str, Any]]] = {}
    for table in TABLE_ORDER:
        rows = tables[table]
        pk = PRIMARY_KEYS[table]
        ids = [row[pk] for row in rows]
        require(all(ids), f"{table}: empty primary key")
        require(len(ids) == len(set(ids)), f"{table}: duplicate primary key")
        require(all(set(row) == set(TABLE_COLUMNS[table]) for row in rows),
                f"{table}: row fields do not match table schema")
        ids_by_table[table] = set(ids)
        rows_by_table[table] = {row[pk]: row for row in rows}

    for child, foreign_keys in FOREIGN_KEYS.items():
        for field, (parent, _) in foreign_keys.items():
            for row in tables[child]:
                value = row.get(field)
                if value in ("", None):
                    if child == "workflow_events" and field == "return_line_id":
                        continue
                    require(False, f"{child}.{field}: required foreign key is empty")
                elif value not in ids_by_table[parent]:
                    require(False, f"{child}.{field}: orphan reference {value}")

    for (table, field), allowed in ENUMS.items():
        require(
            all(row[field] in allowed for row in tables[table]),
            f"{table}.{field}: unsupported enum value",
        )

    orders = rows_by_table["orders"]
    order_lines = tables["order_lines"]
    order_lines_by_order: dict[str, list[dict[str, Any]]] = {}
    for line in order_lines:
        order_lines_by_order.setdefault(line["order_id"], []).append(line)
        expected_line_paid = (
            line["quantity"] * line["unit_price_cents"] - line["discount_cents"] + line["tax_cents"]
        )
        require(line["quantity"] > 0, f"{line['order_line_id']}: nonpositive purchased quantity")
        require(line["discount_cents"] <= line["quantity"] * line["unit_price_cents"],
                f"{line['order_line_id']}: discount exceeds merchandise")
        require(line["line_paid_cents"] == expected_line_paid,
                f"{line['order_line_id']}: line payment arithmetic mismatch")
        require(line["return_window_days"] > 0, f"{line['order_line_id']}: invalid return window")

    for order_id, order in orders.items():
        lines = order_lines_by_order.get(order_id, [])
        require(bool(lines), f"{order_id}: order has no lines")
        expected = (
            sum(row["quantity"] * row["unit_price_cents"] for row in lines),
            sum(row["discount_cents"] for row in lines),
            sum(row["tax_cents"] for row in lines),
        )
        require(order["subtotal_cents"] == expected[0], f"{order_id}: subtotal mismatch")
        require(order["discount_cents"] == expected[1], f"{order_id}: discount mismatch")
        require(order["tax_cents"] == expected[2], f"{order_id}: tax mismatch")
        require(
            order["total_paid_cents"] == expected[0] - expected[1] + expected[2] + order["shipping_fee_cents"],
            f"{order_id}: total paid reconciliation mismatch",
        )

    policies = {row["policy_id"]: row for row in tables["return_policies"]}
    for line in order_lines:
        policy = policies[line["policy_id"]]
        require(line["category"] == policy["category"], f"{line['order_line_id']}: category/policy mismatch")
        require(line["return_window_days"] == policy["return_window_days"],
                f"{line['order_line_id']}: policy window mismatch")
        if policy["final_sale"]:
            require(line["final_sale"], f"{line['order_line_id']}: excluded category is not final sale")
        require(
            date.fromisoformat(policy["effective_from"]) <= date.fromisoformat(orders[line["order_id"]]["order_date"])
            <= date.fromisoformat(policy["effective_to"]),
            f"{line['order_line_id']}: order outside policy effective dates",
        )

    requests = rows_by_table["return_requests"]
    request_lines: dict[str, list[dict[str, Any]]] = {}
    line_ids = rows_by_table["return_lines"]
    for line in tables["return_lines"]:
        request = requests[line["rma_id"]]
        purchased = rows_by_table["order_lines"][line["order_line_id"]]
        require(request["order_id"] == purchased["order_id"],
                f"{line['return_line_id']}: returned item is not on the requested order")
        request_lines.setdefault(line["rma_id"], []).append(line)
        require(line["requested_qty"] > 0, f"{line['return_line_id']}: nonpositive requested quantity")
        require(0 <= line["approved_qty"] <= min(line["requested_qty"], purchased["quantity"]),
                f"{line['return_line_id']}: approved quantity is outside purchased/requested bounds")
        if line["requested_qty"] > purchased["quantity"]:
            key = ("RETURN_LINE", line["return_line_id"], "RETURN_QTY_EXCEEDS_PURCHASE")
            require(key in truth_entities, f"{line['return_line_id']}: unlabelled quantity overage")
            require(line["approved_qty"] <= purchased["quantity"],
                    f"{line['return_line_id']}: overage exceeds purchased cap")
            expected_exceptions.append(f"{line['return_line_id']}: requested quantity exceeds purchase; capped")

    auth_by_request = {row["rma_id"]: row for row in tables["return_authorizations"]}
    require(len(auth_by_request) == len(requests), "each request must have exactly one authorization")
    for rma_id, request in requests.items():
        lines = request_lines.get(rma_id, [])
        approved = sum(line["approved_qty"] for line in lines)
        requested = sum(line["requested_qty"] for line in lines)
        expected_status = (
            "REJECTED" if approved == 0 else
            "APPROVED" if approved == requested else "PARTIALLY_APPROVED"
        )
        require(request["status"] == expected_status, f"{rma_id}: request status does not match line decisions")
        auth_status = {
            "APPROVED": "AUTHORIZED",
            "PARTIALLY_APPROVED": "PARTIALLY_AUTHORIZED",
            "REJECTED": "REJECTED",
        }[expected_status]
        require(auth_by_request[rma_id]["status"] == auth_status,
                f"{rma_id}: authorization status does not match request")
        require(auth_by_request[rma_id]["override_used"] == request["override_approved"],
                f"{rma_id}: authorization override history mismatch")
        require(auth_by_request[rma_id]["authorized_at"][:10] >= request["requested_at"],
                f"{rma_id}: authorization predates request")
        order = orders[request["order_id"]]
        require(request["customer_id"] == order["customer_id"],
                f"{rma_id}: request customer differs from order customer")
        require(request["requested_at"] >= order["order_date"],
                f"{rma_id}: request predates source order")
        age = (
            date.fromisoformat(request["requested_at"]) - date.fromisoformat(order["order_date"])
        ).days
        for line in lines:
            purchased = rows_by_table["order_lines"][line["order_line_id"]]
            if purchased["final_sale"]:
                require(line["approved_qty"] == 0, f"{line['return_line_id']}: final-sale line approved")
            elif age > purchased["return_window_days"] and not request["override_approved"]:
                require(line["approved_qty"] == 0, f"{line['return_line_id']}: late line approved without override")

    shipments = {row["rma_id"]: row for row in tables["return_shipments"]}
    inspections = {row["return_line_id"]: row for row in tables["inspections"]}
    dispositions = {row["return_line_id"]: row for row in tables["inventory_dispositions"]}
    shipment_by_id = {row["shipment_id"]: row for row in tables["return_shipments"]}
    inspection_by_id = {row["inspection_id"]: row for row in tables["inspections"]}
    for inspection in tables["inspections"]:
        shipment = shipment_by_id[inspection["shipment_id"]]
        require(requests[shipment["rma_id"]]["requested_at"] <= shipment["shipped_at"],
                f"{inspection['inspection_id']}: shipment precedes request")
        require(shipment["received_at"] <= inspection["inspected_at"],
                f"{inspection['inspection_id']}: inspection precedes receipt")
        require(line_ids[inspection["return_line_id"]]["rma_id"] == shipment["rma_id"],
                f"{inspection['inspection_id']}: inspection line and shipment RMA mismatch")
        require(line_ids[inspection["return_line_id"]]["approved_qty"] > 0,
                f"{inspection['inspection_id']}: unapproved line was inspected")
    for disposition in tables["inventory_dispositions"]:
        inspection = inspection_by_id[disposition["inspection_id"]]
        require(inspection["return_line_id"] == disposition["return_line_id"],
                f"{disposition['disposition_id']}: disposition inspection and return line mismatch")
        require(disposition["quantity"] == line_ids[disposition["return_line_id"]]["approved_qty"],
                f"{disposition['disposition_id']}: disposition quantity mismatch")
        expected_decision = {
            "GOOD": "RESTOCK",
            "OPEN_BOX": "REFURBISH",
            "DAMAGED": "QUARANTINE",
            "DEFECTIVE": "SCRAP",
        }[inspection["condition"]]
        require(disposition["decision"] == expected_decision,
                f"{disposition['disposition_id']}: decision does not match inspection condition")
        if disposition["decided_at"] < inspection["inspected_at"]:
            key = ("INVENTORY_DISPOSITION", disposition["disposition_id"], "RESTOCK_BEFORE_INSPECTION")
            require(key in truth_entities, f"{disposition['disposition_id']}: unlabelled early disposition")
            require(disposition["decision"] == "RESTOCK", "early-disposition test must target restock")
            require(disposition["inventory_movement"] == "NO_MOVEMENT",
                    f"{disposition['disposition_id']}: early restock was not held")
            expected_exceptions.append(f"{disposition['disposition_id']}: restock predates inspection")
        require(
            (disposition["decision"], disposition["inventory_movement"]) in {
                ("RESTOCK", "RESTOCKED"),
                ("REFURBISH", "REFURBISHMENT_QUEUE"),
                ("QUARANTINE", "QUARANTINED"),
                ("SCRAP", "SCRAPPED"),
            } | ({("RESTOCK", "NO_MOVEMENT")} if disposition["decided_at"] < inspection["inspected_at"] else set()),
            f"{disposition['disposition_id']}: disposition/movement mismatch",
        )
        if disposition["decision"] == "RESTOCK" and disposition["decided_at"] >= inspection["inspected_at"]:
            require(inspection["condition"] == "GOOD",
                    f"{disposition['disposition_id']}: only good condition may be restocked")

    refunds_by_line: dict[str, list[dict[str, Any]]] = {}
    for refund in tables["refunds"]:
        line = line_ids[refund["return_line_id"]]
        order_line = rows_by_table["order_lines"][line["order_line_id"]]
        order = orders[requests[refund["rma_id"]]["order_id"]]
        require(line["rma_id"] == refund["rma_id"], f"{refund['refund_id']}: refund RMA mismatch")
        require(refund["return_line_id"] in inspections,
                f"{refund['refund_id']}: refund has no completed inspection")
        require(refund["attempted_at"] >= inspections[refund["return_line_id"]]["inspected_at"],
                f"{refund['refund_id']}: refund attempt predates inspection")
        expected_method = (
            "EXCHANGE_CREDIT" if requests[refund["rma_id"]]["request_type"] == "EXCHANGE"
            else "ORIGINAL_PAYMENT"
        )
        require(refund["refund_method"] == expected_method,
                f"{refund['refund_id']}: refund method does not match request type")
        if refund["status"] in {"BLOCKED_OVER_REFUND", "BLOCKED_DUPLICATE"}:
            require(refund["approved_amount_cents"] == 0,
                    f"{refund['refund_id']}: blocked attempt paid a positive amount")
        if refund["status"] == "BLOCKED_OVER_REFUND":
            require(refund["requested_amount_cents"] > order["total_paid_cents"],
                    f"{refund['refund_id']}: over-refund attempt does not exceed paid amount")
            key = ("REFUND", refund["refund_id"], "REFUND_EXCEEDS_PAID_AMOUNT")
            require(key in truth_entities, f"{refund['refund_id']}: unlabelled over-refund")
            expected_exceptions.append(f"{refund['refund_id']}: over-refund attempt blocked")
        refunds_by_line.setdefault(refund["return_line_id"], []).append(refund)
        require(refund["attempt_number"] >= 1, f"{refund['refund_id']}: invalid attempt number")
        require(refund["approved_amount_cents"] >= 0, f"{refund['refund_id']}: negative payout")
        if refund["status"] in {"ISSUED", "CREDIT_ISSUED"}:
            require(refund["requested_amount_cents"] == refund["approved_amount_cents"],
                    f"{refund['refund_id']}: issued amount differs from requested amount")
            require(refund["approved_amount_cents"] <= order_line["line_paid_cents"],
                    f"{refund['refund_id']}: refund exceeds paid line value")
            request = requests[refund["rma_id"]]
            policy = policies[order_line["policy_id"]]
            quantity = line["approved_qty"]
            gross = (
                order_line["unit_price_cents"] * quantity
                - round(order_line["discount_cents"] * quantity / order_line["quantity"])
                + round(order_line["tax_cents"] * quantity / order_line["quantity"])
            )
            fee_rate = (
                0 if request["reason"] in {"DAMAGED", "DEFECTIVE", "WRONG_ITEM"}
                else policy["restocking_fee_basis_points"]
            )
            fee = round(
                max(
                    0,
                    order_line["unit_price_cents"] * quantity
                    - round(order_line["discount_cents"] * quantity / order_line["quantity"]),
                )
                * fee_rate / 10_000
            )
            expected_refund = max(0, gross - fee)
            require(refund["approved_amount_cents"] == expected_refund,
                    f"{refund['refund_id']}: refund math does not reconcile to price, discount, tax, and fee")

    issued_by_request: Counter[str] = Counter()
    for refund in tables["refunds"]:
        if refund["status"] in {"ISSUED", "CREDIT_ISSUED"}:
            issued_by_request[refund["rma_id"]] += refund["approved_amount_cents"]
    for rma_id, issued in issued_by_request.items():
        order = orders[requests[rma_id]["order_id"]]
        require(issued <= order["total_paid_cents"],
                f"{rma_id}: cumulative refunds exceed order paid amount")

    for line_id, attempts in refunds_by_line.items():
        attempt_numbers = [row["attempt_number"] for row in attempts]
        require(len(attempt_numbers) == len(set(attempt_numbers)),
                f"{line_id}: duplicate attempt number")
        paid_attempts = [row for row in attempts if row["status"] in {"ISSUED", "CREDIT_ISSUED"}]
        require(len(paid_attempts) <= 1, f"{line_id}: multiple successful payouts")
        if len(attempts) > 1:
            require(all(row["status"] != "BLOCKED_DUPLICATE" for row in attempts[1:]) or len(attempts) == 2,
                    f"{line_id}: duplicate refund attempt was not blocked")
        for row in attempts:
            if row["status"] == "BLOCKED_DUPLICATE":
                key = ("REFUND", row["refund_id"], "DUPLICATE_REFUND_ATTEMPT")
                require(key in truth_entities, f"{row['refund_id']}: unlabelled duplicate attempt")
                expected_exceptions.append(f"{row['refund_id']}: duplicate payout attempt blocked")

    for rma_id in requests:
        if rma_id in shipments:
            require(any(
                line["approved_qty"] > 0 for line in request_lines.get(rma_id, [])
            ), f"{rma_id}: shipment exists without an approved return line")
        if rma_id not in shipments:
            key = ("RETURN_REQUEST", rma_id, "MISSING_RETURN_SHIPMENT")
            if key in truth_entities:
                expected_exceptions.append(f"{rma_id}: approved return shipment is missing")
            elif any(line["approved_qty"] > 0 for line in request_lines.get(rma_id, [])):
                require(False, f"{rma_id}: approved return has no shipment and no exception label")
        else:
            require(shipments[rma_id]["shipped_at"] >= requests[rma_id]["requested_at"],
                    f"{rma_id}: shipment predates request")
        for line in request_lines.get(rma_id, []):
            if line["approved_qty"] > 0 and rma_id in shipments:
                require(line["return_line_id"] in inspections,
                        f"{line['return_line_id']}: received approved line lacks inspection")
                require(line["return_line_id"] in dispositions,
                        f"{line['return_line_id']}: inspected line lacks disposition")
                require(line["return_line_id"] in refunds_by_line,
                        f"{line['return_line_id']}: inspected line lacks refund attempt")

        request = requests[rma_id]
        age_days = (
            date.fromisoformat(request["requested_at"])
            - date.fromisoformat(orders[request["order_id"]]["order_date"])
        ).days
        late_lines = [
            line for line in request_lines.get(rma_id, [])
            if not rows_by_table["order_lines"][line["order_line_id"]]["final_sale"]
            and age_days > rows_by_table["order_lines"][line["order_line_id"]]["return_window_days"]
        ]
        if late_lines and not request["override_approved"]:
            require(
                all(line["approved_qty"] == 0 for line in late_lines),
                f"{rma_id}: late request without override was approved",
            )
            if ("RETURN_REQUEST", rma_id, "LATE_WITHOUT_OVERRIDE") in truth_entities:
                expected_exceptions.append(f"{rma_id}: late request rejected without override")
    for event in tables["workflow_events"]:
        require(event["event_at"][:10] >= requests[event["rma_id"]]["requested_at"],
                f"{event['event_id']}: event predates return request")

    required_issues = {
        "RETURN_QTY_EXCEEDS_PURCHASE",
        "REFUND_EXCEEDS_PAID_AMOUNT",
        "RESTOCK_BEFORE_INSPECTION",
        "LATE_WITHOUT_OVERRIDE",
        "DUPLICATE_REFUND_ATTEMPT",
        "MISSING_RETURN_SHIPMENT",
    }
    missing_issues = sorted(required_issues - truth_types)
    require(not missing_issues, f"required edge cases missing: {', '.join(missing_issues)}")
    for label in (row for row in truth if row["issue_type"] == "LATE_WITHOUT_OVERRIDE"):
        request = requests.get(label["entity_id"])
        if request is None:
            require(False, f"{label['entity_id']}: late-request label references no request")
            continue
        age_days = (
            date.fromisoformat(request["requested_at"])
            - date.fromisoformat(orders[request["order_id"]]["order_date"])
        ).days
        require(not request["override_approved"], f"{label['entity_id']}: labelled late request has override")
        require(any(
            not rows_by_table["order_lines"][line["order_line_id"]]["final_sale"]
            and age_days > rows_by_table["order_lines"][line["order_line_id"]]["return_window_days"]
            for line in request_lines.get(label["entity_id"], [])
        ), f"{label['entity_id']}: labelled request is not actually outside policy")

    condition_counts = Counter(row["condition"] for row in tables["inspections"])
    disposition_counts = Counter(row["decision"] for row in tables["inventory_dispositions"])
    request_status_counts = Counter(row["status"] for row in tables["return_requests"])
    refund_status_counts = Counter(row["status"] for row in tables["refunds"])
    issued_cents = sum(
        row["approved_amount_cents"] for row in tables["refunds"]
        if row["status"] in {"ISSUED", "CREDIT_ISSUED"}
    )
    metrics = {
        "orders": len(tables["orders"]),
        "return_requests": len(tables["return_requests"]),
        "return_lines": len(tables["return_lines"]),
        "authorized_requests": sum(row["status"] != "REJECTED" for row in tables["return_authorizations"]),
        "requests_by_status": dict(sorted(request_status_counts.items())),
        "inspection_conditions": dict(sorted(condition_counts.items())),
        "inventory_dispositions": dict(sorted(disposition_counts.items())),
        "refund_attempts_by_status": dict(sorted(refund_status_counts.items())),
        "refund_amount_issued_cents": issued_cents,
        "missing_shipments": sum(
            row["rma_id"] not in shipments and any(
                line["approved_qty"] > 0 for line in request_lines.get(row["rma_id"], [])
            )
            for row in tables["return_requests"]
        ),
        "ground_truth_labels": len(truth),
        "expected_exception_checks": len(expected_exceptions),
        "expected_exceptions": expected_exceptions,
        "structural_error_count": len(errors),
        "structural_errors": errors,
        "pass": not errors,
    }
    return metrics
