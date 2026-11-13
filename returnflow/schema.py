"""Relational table definitions shared by generation and validation."""

from __future__ import annotations

TABLE_ORDER = (
    "return_policies",
    "customers",
    "orders",
    "order_lines",
    "return_requests",
    "return_lines",
    "return_authorizations",
    "return_shipments",
    "inspections",
    "refunds",
    "inventory_dispositions",
    "workflow_events",
)

TABLE_COLUMNS = {
    "return_policies": (
        "policy_id", "category", "effective_from", "effective_to",
        "return_window_days", "final_sale", "restocking_fee_basis_points", "policy_version",
    ),
    "customers": ("customer_id", "created_at", "region", "segment"),
    "orders": (
        "order_id", "customer_id", "order_date", "channel", "currency", "subtotal_cents",
        "discount_cents", "tax_cents", "shipping_fee_cents", "total_paid_cents", "status",
    ),
    "order_lines": (
        "order_line_id", "order_id", "policy_id", "sku", "category", "quantity",
        "unit_price_cents", "discount_cents", "tax_cents", "line_paid_cents",
        "return_window_days", "final_sale",
    ),
    "return_requests": (
        "rma_id", "order_id", "customer_id", "requested_at", "reason", "request_type",
        "override_approved", "status",
    ),
    "return_lines": (
        "return_line_id", "rma_id", "order_line_id", "requested_qty", "approved_qty",
        "eligibility_status", "decision_reason",
    ),
    "return_authorizations": (
        "authorization_id", "rma_id", "authorized_at", "status", "override_used",
    ),
    "return_shipments": (
        "shipment_id", "rma_id", "shipped_at", "received_at", "status", "carrier",
    ),
    "inspections": (
        "inspection_id", "shipment_id", "return_line_id", "inspected_at", "condition",
        "notes_code",
    ),
    "refunds": (
        "refund_id", "rma_id", "return_line_id", "attempt_number", "attempted_at",
        "refund_method", "requested_amount_cents", "approved_amount_cents", "status",
        "blocked_reason",
    ),
    "inventory_dispositions": (
        "disposition_id", "inspection_id", "return_line_id", "decision", "quantity",
        "decided_at", "inventory_movement", "reason_code",
    ),
    "workflow_events": (
        "event_id", "rma_id", "return_line_id", "event_type", "from_state", "to_state",
        "event_at", "actor",
    ),
}

PRIMARY_KEYS = {
    table: columns[0] for table, columns in TABLE_COLUMNS.items()
}

FOREIGN_KEYS = {
    "orders": {"customer_id": ("customers", "customer_id")},
    "order_lines": {
        "order_id": ("orders", "order_id"),
        "policy_id": ("return_policies", "policy_id"),
    },
    "return_requests": {
        "order_id": ("orders", "order_id"),
        "customer_id": ("customers", "customer_id"),
    },
    "return_lines": {
        "rma_id": ("return_requests", "rma_id"),
        "order_line_id": ("order_lines", "order_line_id"),
    },
    "return_authorizations": {"rma_id": ("return_requests", "rma_id")},
    "return_shipments": {"rma_id": ("return_requests", "rma_id")},
    "inspections": {
        "shipment_id": ("return_shipments", "shipment_id"),
        "return_line_id": ("return_lines", "return_line_id"),
    },
    "refunds": {
        "rma_id": ("return_requests", "rma_id"),
        "return_line_id": ("return_lines", "return_line_id"),
    },
    "inventory_dispositions": {
        "inspection_id": ("inspections", "inspection_id"),
        "return_line_id": ("return_lines", "return_line_id"),
    },
    "workflow_events": {
        "rma_id": ("return_requests", "rma_id"),
        "return_line_id": ("return_lines", "return_line_id"),
    },
}

ENUMS = {
    ("customers", "region"): {"NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"},
    ("customers", "segment"): {"STANDARD", "LOYAL", "NEW"},
    ("orders", "channel"): {"WEB", "APP", "STORE"},
    ("orders", "status"): {"DELIVERED"},
    ("order_lines", "category"): {"APPAREL", "HOME", "ELECTRONICS", "BEAUTY"},
    ("return_requests", "reason"): {
        "CHANGED_MIND", "WRONG_ITEM", "DAMAGED", "DEFECTIVE", "NOT_AS_DESCRIBED",
        "SIZE_ISSUE",
    },
    ("return_requests", "request_type"): {"REFUND", "EXCHANGE"},
    ("return_requests", "status"): {"APPROVED", "PARTIALLY_APPROVED", "REJECTED"},
    ("return_lines", "eligibility_status"): {
        "APPROVED", "PARTIALLY_APPROVED", "REJECTED",
    },
    ("return_authorizations", "status"): {
        "AUTHORIZED", "PARTIALLY_AUTHORIZED", "REJECTED",
    },
    ("return_shipments", "status"): {"RECEIVED"},
    ("inspections", "condition"): {"GOOD", "OPEN_BOX", "DAMAGED", "DEFECTIVE"},
    ("refunds", "refund_method"): {"ORIGINAL_PAYMENT", "EXCHANGE_CREDIT"},
    ("refunds", "status"): {"ISSUED", "CREDIT_ISSUED", "BLOCKED_OVER_REFUND", "BLOCKED_DUPLICATE"},
    ("inventory_dispositions", "decision"): {"RESTOCK", "REFURBISH", "QUARANTINE", "SCRAP"},
    ("inventory_dispositions", "inventory_movement"): {
        "RESTOCKED", "REFURBISHMENT_QUEUE", "QUARANTINED", "SCRAPPED", "NO_MOVEMENT",
    },
}
