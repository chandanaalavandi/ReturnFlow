from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from returnflow.export import write_exports
from returnflow.generator import generate_dataset
from returnflow.validation import validate_dataset


class ReturnFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = generate_dataset(60, 12, 18, seed=20261022)

    def test_scale_ids_joins_and_policy_decisions(self) -> None:
        tables = self.dataset["tables"]
        self.assertEqual(len(tables["orders"]), 60)
        self.assertEqual(len(tables["return_requests"]), 12)
        self.assertEqual(len(tables["return_lines"]), 18)
        self.assertEqual(tables["orders"][0]["order_id"], "ORD-2026-000001")
        self.assertEqual(tables["return_requests"][0]["rma_id"], "RMA-2026-000001")
        self.assertEqual(tables["return_lines"][0]["return_line_id"], "RMAL-RMA-2026-000001-01")
        self.assertTrue(validate_dataset(self.dataset)["pass"])

    def test_required_negative_scenarios_are_labelled_and_controlled(self) -> None:
        truth_types = {row["issue_type"] for row in self.dataset["ground_truth"]}
        self.assertTrue({
            "RETURN_QTY_EXCEEDS_PURCHASE",
            "REFUND_EXCEEDS_PAID_AMOUNT",
            "RESTOCK_BEFORE_INSPECTION",
            "LATE_WITHOUT_OVERRIDE",
            "DUPLICATE_REFUND_ATTEMPT",
            "MISSING_RETURN_SHIPMENT",
        }.issubset(truth_types))

        metrics = validate_dataset(self.dataset)
        self.assertEqual(metrics["missing_shipments"], 1)
        self.assertEqual(metrics["expected_exception_checks"], 6)
        tables = self.dataset["tables"]
        blocked = [row for row in tables["refunds"] if row["status"].startswith("BLOCKED")]
        self.assertTrue(blocked)
        self.assertTrue(all(row["approved_amount_cents"] == 0 for row in blocked))
        for disposition in tables["inventory_dispositions"]:
            inspection = next(
                row for row in tables["inspections"]
                if row["inspection_id"] == disposition["inspection_id"]
            )
            if disposition["decided_at"] < inspection["inspected_at"]:
                self.assertEqual(disposition["inventory_movement"], "NO_MOVEMENT")

    def test_regeneration_has_identical_export_checksums_and_valid_sql(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            write_exports(self.dataset, first)
            write_exports(generate_dataset(60, 12, 18, seed=20261022), second)

            first_hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in first.iterdir() if path.is_file()
            }
            second_hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in second.iterdir() if path.is_file()
            }
            self.assertEqual(first_hashes, second_hashes)
            self.assertTrue((first / "ground_truth.csv").is_file())
            self.assertNotIn('"ground_truth"', (first / "records.jsonl").read_text(encoding="utf-8"))

            connection = sqlite3.connect(":memory:")
            connection.executescript((first / "schema.sql").read_text(encoding="utf-8"))
            connection.executescript((first / "seed.sql").read_text(encoding="utf-8"))
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 60)
            connection.close()


if __name__ == "__main__":
    unittest.main()
