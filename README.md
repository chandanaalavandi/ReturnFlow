# ReturnFlow

ReturnFlow is a reproducible synthetic-data project and executable reference
workflow for retail returns: policy eligibility, return authorization,
shipment receipt, inspection, refunds/exchange credit, and inventory
disposition. It uses only Python's standard library and fictional records.
No customer names, email addresses, or external datasets are used.

## Run it

Python 3.11 or newer is required. No runtime packages or frontend build tools
are needed. From the project root, generate a small dataset and start the
local dashboard:

```powershell
python -m returnflow.cli generate --scale starter
python -m returnflow.cli serve --scale starter --port 8000
```

Open **http://127.0.0.1:8000** in your browser. The server binds to localhost
by default and serves a responsive frontend alongside the Python API. Stop it
with `Ctrl+C`.

The dashboard includes request status filters, RMA/order search, paginated
return requests, refund and shipment state, disposition metrics, labelled
exception cases, dataset generation, and an on-demand validation action. To
use the full dataset in the dashboard, generate it and select the Full dataset
profile (or start the app directly against it):

```powershell
python -m returnflow.cli generate --scale full
python -m returnflow.cli serve --scale full --port 8000
```

You can generate either dataset from the dashboard's **Generate data** button.
The first launch automatically creates the selected profile if it is missing.
The UI and backend use only local project assets and Python's standard
library; no third-party font/CDN requests are made.

To run tests or check data while the dashboard is stopped:

```powershell
python -m unittest discover -s tests -v
python -m returnflow.cli validate data\starter
```

The starter data has 300 orders, 50 return requests, and 80 return lines.
Generate the requested full baseline with the same code and seed:

```powershell
python -m returnflow.cli generate --scale full
python -m returnflow.cli validate data\full
```

The full profile creates exactly 30,000 orders, 5,000 return requests, and
8,000 return lines. Override counts or seed for experiments:

```powershell
python -m returnflow.cli generate --scale starter --orders 1000 `
  --requests 150 --return-lines 240 --seed 20261022 --output data\custom
```

The request count must be between 5 and the order count; return lines must be
between one and four per request. The default seed is `20261022`. Generated
files go into `data\`; the checked-in starter export is included for review,
while full/custom exports are git-ignored because they are large.

## Workflow and decisions

1. Generate effective-dated category policies and synthetic customers.
2. Generate delivered orders and item lines with integer-cent prices,
   discounts, tax, shipping, and policy snapshots.
3. Generate customer requests against actual order lines. A request can cover
   multiple lines; a line cannot be requested twice on the same RMA.
4. Approve only purchased quantities that are in-window and not final-sale.
   A recorded operator override can waive lateness but not a final-sale
   exclusion. Excess quantities are capped at the purchased amount.
5. Create one authorization per request. Approved requests may have one
   shipment; a deliberately missing shipment does not receive inspection,
   refund, or inventory movement.
6. Inspect received approved lines. `GOOD` is restocked, `OPEN_BOX` refurbished,
   `DAMAGED` quarantined, and `DEFECTIVE` scrapped.
7. Calculate refunds in cents from approved quantity, line price, allocated
   discount, allocated tax, and applicable category restocking fee. Shipping is
   not refunded. Defective, damaged, and wrong-item returns have no restocking
   fee. Exchanges receive exchange credit rather than a cash payout.
8. Block over-limit and duplicate payout attempts. Record lifecycle events
   rather than overwriting event history.

Policies are effective for 2026. Return windows are apparel 30 days, home
45 days, electronics 30 days, and beauty 14 days. Beauty and individually
marked final-sale items are excluded. Electronics have a 5% restocking fee
where the reason is not damaged, defective, or wrong item. The 8.25% tax is
calculated at the order-line level, truncated to cents; returns receive the
proportional tax allocation.

## Data products

Every input entity is exported as a headered CSV. `records.jsonl` contains the
same input entities as one JSON record per line; it deliberately excludes
ground-truth labels. `seed.sql` contains SQLite-compatible inserts, while
`schema.sql` defines tables, primary/foreign keys, checks, and indexes. Load
the SQL export into SQLite:

```powershell
sqlite3 returns.db ".read data\starter\schema.sql"
sqlite3 returns.db ".read data\starter\seed.sql"
```

`ground_truth.csv` and `ground_truth.json` are separate evaluation labels:
expected line decisions plus labelled edge cases. They are not features in
the input exports. `metrics.json` contains counts, refund totals, outcomes,
and expected exception checks. `validation_summary.json` reports structural
checks; known negative scenarios are surfaced separately as expected
exceptions, so a valid test fixture can contain labelled adversarial records.
`dataset_manifest.json` records seed, row counts, and SHA-256 digests;
`checksums.sha256` covers every exported file. `source_manifest.json` records
synthetic-only provenance and the effective policy period.

The validator checks primary-key uniqueness, foreign-key integrity, allowed
enums, policy and quantity rules, date order, order arithmetic, refund math,
authorization/status agreement, disposition control, event references, and
duplicate payout blocking. `validate` exits nonzero for structural errors.

## Entities and relationships

`Customer 1:N Order`; `Order 1:N OrderLine`; `Order 1:N ReturnRequest`;
`ReturnRequest 1:N ReturnLine`; `OrderLine 1:N ReturnLine` over time;
`ReturnRequest 1:1 ReturnAuthorization`; `ReturnRequest 0:1 ReturnShipment`;
`ReturnShipment 1:N Inspection`; `ReturnLine 0:1 Inspection`;
`ReturnLine 0:N Refund` (attempt history); and `Inspection 0:1
InventoryDisposition`. Each order line references one effective-dated
`ReturnPolicy`. `WorkflowEvent` is an append-only event table, required to
reference its RMA and optionally a specific return line. The relationships in
this dataset do not require a many-to-many bridge table.

Lifecycle values and field-level types, requiredness, units, uniqueness, enums,
and validation constraints are specified in
[docs/data_dictionary.md](docs/data_dictionary.md). The executable relational
schema is [returnflow/schema.sql](returnflow/schema.sql).

## Reproducibility

Generation uses a local `random.Random(seed)` instance and stable ID counters.
The test suite generates the same small dataset into two independent output
folders and compares every file digest. Full-scale reproducibility is
demonstrated by:

```powershell
python -m returnflow.cli generate --scale full --output data\full-a
python -m returnflow.cli generate --scale full --output data\full-b
Get-FileHash data\full-a\*.csv,data\full-a\*.json,data\full-a\*.jsonl,data\full-a\*.sql
Get-FileHash data\full-b\*.csv,data\full-b\*.json,data\full-b\*.jsonl,data\full-b\*.sql
```

Compare matching file hashes or `checksums.sha256`; manifests are stable
across output directories. Run full-scale generation when a complete evaluation
dataset is needed; tests use a smaller scale to remain fast.
