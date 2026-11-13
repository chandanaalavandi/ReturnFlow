PRAGMA foreign_keys = ON;

CREATE TABLE return_policies (
    policy_id TEXT PRIMARY KEY,
    category TEXT NOT NULL UNIQUE,
    effective_from TEXT NOT NULL,
    effective_to TEXT NOT NULL,
    return_window_days INTEGER NOT NULL CHECK (return_window_days > 0),
    final_sale INTEGER NOT NULL CHECK (final_sale IN (0, 1)),
    restocking_fee_basis_points INTEGER NOT NULL CHECK (restocking_fee_basis_points BETWEEN 0 AND 10000),
    policy_version TEXT NOT NULL,
    CHECK (effective_from <= effective_to)
);

CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    region TEXT NOT NULL CHECK (region IN ('NORTH', 'SOUTH', 'EAST', 'WEST', 'CENTRAL')),
    segment TEXT NOT NULL CHECK (segment IN ('STANDARD', 'LOYAL', 'NEW'))
);

CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    order_date TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('WEB', 'APP', 'STORE')),
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),
    discount_cents INTEGER NOT NULL CHECK (discount_cents >= 0),
    tax_cents INTEGER NOT NULL CHECK (tax_cents >= 0),
    shipping_fee_cents INTEGER NOT NULL CHECK (shipping_fee_cents >= 0),
    total_paid_cents INTEGER NOT NULL CHECK (total_paid_cents >= 0),
    status TEXT NOT NULL CHECK (status = 'DELIVERED')
);

CREATE TABLE order_lines (
    order_line_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    policy_id TEXT NOT NULL REFERENCES return_policies(policy_id),
    sku TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('APPAREL', 'HOME', 'ELECTRONICS', 'BEAUTY')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents > 0),
    discount_cents INTEGER NOT NULL CHECK (discount_cents >= 0),
    tax_cents INTEGER NOT NULL CHECK (tax_cents >= 0),
    line_paid_cents INTEGER NOT NULL CHECK (line_paid_cents >= 0),
    return_window_days INTEGER NOT NULL CHECK (return_window_days > 0),
    final_sale INTEGER NOT NULL CHECK (final_sale IN (0, 1))
);

CREATE TABLE return_requests (
    rma_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    requested_at TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('CHANGED_MIND', 'WRONG_ITEM', 'DAMAGED', 'DEFECTIVE', 'NOT_AS_DESCRIBED', 'SIZE_ISSUE')),
    request_type TEXT NOT NULL CHECK (request_type IN ('REFUND', 'EXCHANGE')),
    override_approved INTEGER NOT NULL CHECK (override_approved IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('APPROVED', 'PARTIALLY_APPROVED', 'REJECTED'))
);

CREATE TABLE return_lines (
    return_line_id TEXT PRIMARY KEY,
    rma_id TEXT NOT NULL REFERENCES return_requests(rma_id),
    order_line_id TEXT NOT NULL REFERENCES order_lines(order_line_id),
    requested_qty INTEGER NOT NULL CHECK (requested_qty > 0),
    approved_qty INTEGER NOT NULL CHECK (approved_qty >= 0),
    eligibility_status TEXT NOT NULL CHECK (eligibility_status IN ('APPROVED', 'PARTIALLY_APPROVED', 'REJECTED')),
    decision_reason TEXT NOT NULL,
    UNIQUE (rma_id, order_line_id)
);

CREATE TABLE return_authorizations (
    authorization_id TEXT PRIMARY KEY,
    rma_id TEXT NOT NULL UNIQUE REFERENCES return_requests(rma_id),
    authorized_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('AUTHORIZED', 'PARTIALLY_AUTHORIZED', 'REJECTED')),
    override_used INTEGER NOT NULL CHECK (override_used IN (0, 1))
);

CREATE TABLE return_shipments (
    shipment_id TEXT PRIMARY KEY,
    rma_id TEXT NOT NULL UNIQUE REFERENCES return_requests(rma_id),
    shipped_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'RECEIVED'),
    carrier TEXT NOT NULL,
    CHECK (shipped_at <= received_at)
);

CREATE TABLE inspections (
    inspection_id TEXT PRIMARY KEY,
    shipment_id TEXT NOT NULL REFERENCES return_shipments(shipment_id),
    return_line_id TEXT NOT NULL UNIQUE REFERENCES return_lines(return_line_id),
    inspected_at TEXT NOT NULL,
    condition TEXT NOT NULL CHECK (condition IN ('GOOD', 'OPEN_BOX', 'DAMAGED', 'DEFECTIVE')),
    notes_code TEXT NOT NULL
);

CREATE TABLE refunds (
    refund_id TEXT PRIMARY KEY,
    rma_id TEXT NOT NULL REFERENCES return_requests(rma_id),
    return_line_id TEXT NOT NULL REFERENCES return_lines(return_line_id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    attempted_at TEXT NOT NULL,
    refund_method TEXT NOT NULL CHECK (refund_method IN ('ORIGINAL_PAYMENT', 'EXCHANGE_CREDIT')),
    requested_amount_cents INTEGER NOT NULL CHECK (requested_amount_cents >= 0),
    approved_amount_cents INTEGER NOT NULL CHECK (approved_amount_cents >= 0),
    status TEXT NOT NULL CHECK (status IN ('ISSUED', 'CREDIT_ISSUED', 'BLOCKED_OVER_REFUND', 'BLOCKED_DUPLICATE')),
    blocked_reason TEXT NOT NULL,
    UNIQUE (return_line_id, attempt_number)
);

CREATE TABLE inventory_dispositions (
    disposition_id TEXT PRIMARY KEY,
    inspection_id TEXT NOT NULL UNIQUE REFERENCES inspections(inspection_id),
    return_line_id TEXT NOT NULL UNIQUE REFERENCES return_lines(return_line_id),
    decision TEXT NOT NULL CHECK (decision IN ('RESTOCK', 'REFURBISH', 'QUARANTINE', 'SCRAP')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    decided_at TEXT NOT NULL,
    inventory_movement TEXT NOT NULL CHECK (inventory_movement IN ('RESTOCKED', 'REFURBISHMENT_QUEUE', 'QUARANTINED', 'SCRAPPED', 'NO_MOVEMENT')),
    reason_code TEXT NOT NULL
);

CREATE TABLE workflow_events (
    event_id TEXT PRIMARY KEY,
    rma_id TEXT NOT NULL REFERENCES return_requests(rma_id),
    return_line_id TEXT REFERENCES return_lines(return_line_id),
    event_type TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    event_at TEXT NOT NULL,
    actor TEXT NOT NULL
);

CREATE TABLE ground_truth (
    ground_truth_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    expected_outcome TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'MEDIUM', 'HIGH', 'CRITICAL'))
);

CREATE INDEX idx_orders_customer_date ON orders(customer_id, order_date);
CREATE INDEX idx_return_requests_order ON return_requests(order_id);
CREATE INDEX idx_return_lines_rma ON return_lines(rma_id);
CREATE INDEX idx_refunds_rma ON refunds(rma_id);
CREATE INDEX idx_events_rma_time ON workflow_events(rma_id, event_at);
