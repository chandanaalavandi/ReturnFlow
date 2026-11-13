"""Stable CSV, JSON Lines, JSON, and SQLite-compatible SQL exports."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from returnflow.generator import SOURCE_MANIFEST
from returnflow.schema import TABLE_COLUMNS, TABLE_ORDER
from returnflow.validation import validate_dataset

GROUND_TRUTH_COLUMNS = (
    "ground_truth_id", "entity_type", "entity_id", "issue_type",
    "expected_outcome", "severity",
)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_exports(dataset: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    """Write all products after a structural and business-rule validation pass."""
    metrics = validate_dataset(dataset)
    if not metrics["pass"]:
        details = "; ".join(metrics["structural_errors"][:10])
        raise ValueError(f"Dataset validation failed: {details}")

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    tables = dataset["tables"]
    ground_truth = dataset["ground_truth"]

    for table in TABLE_ORDER:
        with (destination / f"{table}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=TABLE_COLUMNS[table], lineterminator="\n")
            writer.writeheader()
            writer.writerows(tables[table])
    with (destination / "ground_truth.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=GROUND_TRUTH_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(ground_truth)

    with (destination / "records.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for table in TABLE_ORDER:
            for record in tables[table]:
                stream.write(_json_text({"table": table, "record": record}) + "\n")
    (destination / "ground_truth.json").write_text(
        _json_text(ground_truth) + "\n", encoding="utf-8", newline="\n"
    )
    (destination / "metrics.json").write_text(
        _json_text(metrics) + "\n", encoding="utf-8", newline="\n"
    )
    (destination / "validation_summary.json").write_text(
        _json_text({
            "pass": metrics["pass"],
            "structural_error_count": metrics["structural_error_count"],
            "structural_errors": metrics["structural_errors"],
            "expected_exception_checks": metrics["expected_exception_checks"],
            "expected_exceptions": metrics["expected_exceptions"],
        }) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (destination / "source_manifest.json").write_text(
        _json_text(SOURCE_MANIFEST) + "\n", encoding="utf-8", newline="\n"
    )

    schema_path = Path(__file__).with_name("schema.sql")
    shutil.copyfile(schema_path, destination / "schema.sql")
    with (destination / "seed.sql").open("w", encoding="utf-8", newline="\n") as stream:
        stream.write("PRAGMA foreign_keys = ON;\nBEGIN TRANSACTION;\n")
        for table in TABLE_ORDER:
            fields = TABLE_COLUMNS[table]
            columns = ", ".join(f'"{field}"' for field in fields)
            for record in tables[table]:
                values = ", ".join(_sql_value(record[field]) for field in fields)
                stream.write(f'INSERT INTO "{table}" ({columns}) VALUES ({values});\n')
        for record in ground_truth:
            columns = ", ".join(f'"{field}"' for field in GROUND_TRUTH_COLUMNS)
            values = ", ".join(_sql_value(record[field]) for field in GROUND_TRUTH_COLUMNS)
            stream.write(f'INSERT INTO "ground_truth" ({columns}) VALUES ({values});\n')
        stream.write("COMMIT;\n")

    artifacts = sorted(
        path for path in destination.iterdir()
        if path.is_file() and path.name not in {"dataset_manifest.json", "checksums.sha256"}
    )
    manifest = {
        "seed": dataset["seed"],
        "as_of_date": dataset["as_of_date"],
        "counts": dataset["counts"],
        "validation_passed": metrics["pass"],
        "sha256": {path.name: _sha256(path) for path in artifacts},
    }
    (destination / "dataset_manifest.json").write_text(
        _json_text(manifest) + "\n", encoding="utf-8", newline="\n"
    )
    checksum_files = sorted(
        path for path in destination.iterdir()
        if path.is_file() and path.name != "checksums.sha256"
    )
    with (destination / "checksums.sha256").open("w", encoding="utf-8", newline="\n") as stream:
        for path in checksum_files:
            stream.write(f"{_sha256(path)}  {path.name}\n")
    return manifest
