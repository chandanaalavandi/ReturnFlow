# Data dictionary

All monetary amounts are integer **USD cents**; all quantities are integer
units. Dates are ISO-8601 `YYYY-MM-DD`; event timestamps are UTC ISO-8601.
`required` means non-null in the generated and SQL data. Primary keys are
unique; foreign keys are validated against the referenced table. Boolean
values export as `true`/`false` in JSON and `0`/`1` in SQL.

## ReturnPolicy

Effective-dated policy snapshot referenced by each purchased line.

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| policy_id | string | Yes | `POL-2026-NN` | PK | Immutable policy identifier |
| category | string | Yes | APPAREL, HOME, ELECTRONICS, BEAUTY | Yes | One active generated policy per category |
| effective_from | date | Yes | ISO date | No | Must not exceed effective_to |
| effective_to | date | Yes | ISO date | No | Order date must be within the period |
| return_window_days | integer | Yes | Days, positive | No | Eligibility uses this snapshot |
| final_sale | boolean | Yes | true/false | No | Category-wide exclusion |
| restocking_fee_basis_points | integer | Yes | 0–10,000 bps | No | Applied only to eligible reasons |
| policy_version | string | Yes | `2026.1` | No | Nonempty version |

## Customer

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| customer_id | string | Yes | `CUS-2026-NNNNNN` | PK | Stable synthetic ID |
| created_at | date | Yes | ISO date | No | No personal/contact information |
| region | enum | Yes | NORTH, SOUTH, EAST, WEST, CENTRAL | No | Must be an allowed region |
| segment | enum | Yes | STANDARD, LOYAL, NEW | No | Must be an allowed segment |

## Order

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| order_id | string | Yes | `ORD-2026-NNNNNN` | PK | Sequential immutable ID |
| customer_id | string | Yes | Customer ID | FK | Must exist in Customer |
| order_date | date | Yes | ISO date | No | Within the 2026 policy period |
| channel | enum | Yes | WEB, APP, STORE | No | Must be an allowed channel |
| currency | string | Yes | USD | No | Single-currency dataset |
| subtotal_cents | integer | Yes | USD cents | No | Sum quantity × unit price |
| discount_cents | integer | Yes | USD cents, nonnegative | No | Sum of line discounts |
| tax_cents | integer | Yes | USD cents, nonnegative | No | Sum of line taxes |
| shipping_fee_cents | integer | Yes | USD cents, nonnegative | No | Not refunded by policy |
| total_paid_cents | integer | Yes | USD cents | No | subtotal − discount + tax + shipping |
| status | enum | Yes | DELIVERED | No | Only delivered orders can be returned |

## OrderLine

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| order_line_id | string | Yes | `OL-NNNNNN-NN` | PK | Stable line ID |
| order_id | string | Yes | Order ID | FK | Parent order must exist |
| policy_id | string | Yes | ReturnPolicy ID | FK | Category and effective policy must match |
| sku | string | Yes | Synthetic SKU | No | Nonempty product code |
| category | enum | Yes | APPAREL, HOME, ELECTRONICS, BEAUTY | No | Matches referenced policy |
| quantity | integer | Yes | Units, positive | No | Purchased quantity |
| unit_price_cents | integer | Yes | USD cents, positive | No | Source price for reconciliation |
| discount_cents | integer | Yes | USD cents | No | Cannot exceed merchandise value |
| tax_cents | integer | Yes | USD cents | No | Generated at 8.25%, truncated to cents |
| line_paid_cents | integer | Yes | USD cents | No | quantity × price − discount + tax |
| return_window_days | integer | Yes | Days, positive | No | Snapshot equals policy value |
| final_sale | boolean | Yes | true/false | No | True if policy excludes category or item is marked final sale |

## ReturnRequest

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| rma_id | string | Yes | `RMA-2026-NNNNNN` | PK | Sequential immutable authorization reference |
| order_id | string | Yes | Order ID | FK | Must be the source order for each return line |
| customer_id | string | Yes | Customer ID | FK | Must match source order customer |
| requested_at | date | Yes | ISO date | No | Cannot precede order date |
| reason | enum | Yes | CHANGED_MIND, WRONG_ITEM, DAMAGED, DEFECTIVE, NOT_AS_DESCRIBED, SIZE_ISSUE | No | Drives fee and inspection distributions |
| request_type | enum | Yes | REFUND, EXCHANGE | No | Exchange is fulfilled as exchange credit |
| override_approved | boolean | Yes | true/false | No | Only an explicit override waives lateness |
| status | enum | Yes | APPROVED, PARTIALLY_APPROVED, REJECTED | No | Aggregated from approved/requested line units |

## ReturnLine

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| return_line_id | string | Yes | `RMAL-<rma-id>-NN` | PK | Sequential line number within RMA |
| rma_id | string | Yes | ReturnRequest ID | FK | Parent request must exist |
| order_line_id | string | Yes | OrderLine ID | FK | Must belong to request's order |
| requested_qty | integer | Yes | Units, positive | No | May exceed purchase only in labelled test case |
| approved_qty | integer | Yes | Units, nonnegative | No | At most requested and purchased quantity |
| eligibility_status | enum | Yes | APPROVED, PARTIALLY_APPROVED, REJECTED | No | Must match requested vs approved quantity |
| decision_reason | string | Yes | ELIGIBLE, OUTSIDE_RETURN_WINDOW, CATEGORY_EXCLUDED_FINAL_SALE, QUANTITY_EXCEEDED_CAPPED | No | Derived from policy and source values |

## ReturnAuthorization

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| authorization_id | string | Yes | `AUTH-2026-NNNNNN` | PK | Immutable authorization ID |
| rma_id | string | Yes | ReturnRequest ID | FK, unique | Exactly one decision per request |
| authorized_at | timestamp | Yes | UTC timestamp | No | At/after request submission |
| status | enum | Yes | AUTHORIZED, PARTIALLY_AUTHORIZED, REJECTED | No | Maps to request status |
| override_used | boolean | Yes | true/false | No | Copies the explicit operator override |

## ReturnShipment

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| shipment_id | string | Yes | `RTS-2026-NNNNNN` | PK | Sequential immutable shipment ID |
| rma_id | string | Yes | ReturnRequest ID | FK, unique | At most one shipment per request |
| shipped_at | date | Yes | ISO date | No | At/after request |
| received_at | date | Yes | ISO date | No | At/after shipment |
| status | enum | Yes | RECEIVED | No | Missing shipment is represented by no shipment row |
| carrier | string | Yes | UPS, USPS, FEDEX, DHL | No | Nonempty carrier |

## Inspection

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| inspection_id | string | Yes | `INSP-2026-NNNNNN` | PK | Immutable inspection ID |
| shipment_id | string | Yes | ReturnShipment ID | FK | Shipment must exist |
| return_line_id | string | Yes | ReturnLine ID | FK, unique | One inspection per received return line |
| inspected_at | date | Yes | ISO date | No | At/after shipment receipt |
| condition | enum | Yes | GOOD, OPEN_BOX, DAMAGED, DEFECTIVE | No | Drives disposition |
| notes_code | string | Yes | Condition/reason code | No | Nonempty inspection note code |

## Refund

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| refund_id | string | Yes | `REF-2026-NNNNNN` | PK | Sequential immutable attempt ID |
| rma_id | string | Yes | ReturnRequest ID | FK | Must match return line's request |
| return_line_id | string | Yes | ReturnLine ID | FK | Must reference approved inspected line |
| attempt_number | integer | Yes | Positive integer | Unique with return_line_id | Duplicate attempts are retained, never paid twice |
| attempted_at | date | Yes | ISO date | No | At/after request |
| refund_method | enum | Yes | ORIGINAL_PAYMENT, EXCHANGE_CREDIT | No | Follows request type |
| requested_amount_cents | integer | Yes | USD cents, nonnegative | No | Calculated amount or labelled over-refund attempt |
| approved_amount_cents | integer | Yes | USD cents, nonnegative | No | Zero for every blocked attempt |
| status | enum | Yes | ISSUED, CREDIT_ISSUED, BLOCKED_OVER_REFUND, BLOCKED_DUPLICATE | No | Issued payouts reconcile to price/discount/tax/fee |
| blocked_reason | string | Yes | Empty or rule code | No | Required explanation for blocked attempts |

## InventoryDisposition

| Field | Type | Req. | Allowed / unit | Unique | Validation |
|---|---|---:|---|---|---|
| disposition_id | string | Yes | `DSP-2026-NNNNNN` | PK | Immutable decision ID |
| inspection_id | string | Yes | Inspection ID | FK, unique | Decision must reference inspection |
| return_line_id | string | Yes | ReturnLine ID | FK, unique | Must match inspection line |
| decision | enum | Yes | RESTOCK, REFURBISH, QUARANTINE, SCRAP | No | Derived from inspection condition |
| quantity | integer | Yes | Units, positive | No | Equals approved return quantity |
| decided_at | date | Yes | ISO date | No | Any actual inventory movement must follow inspection |
| inventory_movement | enum | Yes | RESTOCKED, REFURBISHMENT_QUEUE, QUARANTINED, SCRAPPED, NO_MOVEMENT | No | Early-restock test is held as NO_MOVEMENT |
| reason_code | string | Yes | SELLABLE, OPEN_BOX, DAMAGE_REVIEW, NON_REPAIRABLE, BLOCKED_PRE_INSPECTION | No | Explains disposition outcome |

## WorkflowEvent and GroundTruth

`WorkflowEvent(event_id, rma_id, return_line_id?, event_type, from_state,
to_state, event_at, actor)` is append-only. `event_id` is the PK; `rma_id` is
required FK; `return_line_id` is an optional FK. Timestamps never precede the
request. State values are recorded as event data rather than overwritten.

`GroundTruth(ground_truth_id, entity_type, entity_id, issue_type,
expected_outcome, severity)` is exported only to separate ground-truth files
and a separate SQL table. IDs are unique. Labels include expected line decisions
and the intentional policy/quantity/refund/shipment/disposition edge cases.
Since labels can target several entity types, `entity_id` is resolved using
`entity_type` and is not an input feature.
