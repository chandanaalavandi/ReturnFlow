"""Dependency-free local dashboard for exploring generated returns data."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from returnflow.cli import SCALES
from returnflow.export import load_export, write_exports
from returnflow.generator import SEED, generate_dataset
from returnflow.validation import validate_dataset

EXCEPTION_TYPES = {
    "RETURN_QTY_EXCEEDS_PURCHASE",
    "REFUND_EXCEEDS_PAID_AMOUNT",
    "RESTOCK_BEFORE_INSPECTION",
    "LATE_WITHOUT_OVERRIDE",
    "DUPLICATE_REFUND_ATTEMPT",
    "MISSING_RETURN_SHIPMENT",
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class DatasetView:
    """Indexed, input-only view of one exported profile for API requests."""

    def __init__(self, profile: str, directory: Path) -> None:
        self.profile = profile
        self.directory = directory
        self.manifest = json.loads((directory / "dataset_manifest.json").read_text(encoding="utf-8"))
        self.metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        self.orders = {row["order_id"]: row for row in _read_csv(directory / "orders.csv")}
        self.requests = _read_csv(directory / "return_requests.csv")
        self.lines_by_rma: dict[str, list[dict[str, str]]] = defaultdict(list)
        for line in _read_csv(directory / "return_lines.csv"):
            self.lines_by_rma[line["rma_id"]].append(line)
        self.shipments = {row["rma_id"]: row for row in _read_csv(directory / "return_shipments.csv")}
        self.refunds_by_rma: dict[str, list[dict[str, str]]] = defaultdict(list)
        for refund in _read_csv(directory / "refunds.csv"):
            self.refunds_by_rma[refund["rma_id"]].append(refund)
        self.dispositions_by_line = {
            row["return_line_id"]: row for row in _read_csv(directory / "inventory_dispositions.csv")
        }
        self.exceptions = [
            row for row in json.loads((directory / "ground_truth.json").read_text(encoding="utf-8"))
            if row["issue_type"] in EXCEPTION_TYPES
        ]

    def summary(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "seed": self.manifest["seed"],
            "as_of_date": self.manifest["as_of_date"],
            "counts": self.manifest["counts"],
            "metrics": self.metrics,
            "exceptions": self.exceptions,
        }

    def return_records(
        self,
        status_filter: str = "ALL",
        search: str = "",
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        status_filter = status_filter.upper()
        if status_filter not in {"ALL", "APPROVED", "PARTIALLY_APPROVED", "REJECTED"}:
            raise ValueError("Unsupported return status filter")
        if not 1 <= page_size <= 100:
            raise ValueError("Page size must be between 1 and 100")
        if page < 1:
            raise ValueError("Page must be a positive integer")
        search = search.casefold().strip()
        records: list[dict[str, Any]] = []
        for request in self.requests:
            status = request["status"]
            if status_filter != "ALL" and status != status_filter:
                continue
            order = self.orders[request["order_id"]]
            if search and not any(
                search in value.casefold()
                for value in (request["rma_id"], request["order_id"], request["customer_id"])
            ):
                continue
            lines = self.lines_by_rma[request["rma_id"]]
            refunds = self.refunds_by_rma.get(request["rma_id"], [])
            paid = sum(
                int(row["approved_amount_cents"])
                for row in refunds if row["status"] in {"ISSUED", "CREDIT_ISSUED"}
            )
            records.append({
                "rma_id": request["rma_id"],
                "order_id": request["order_id"],
                "requested_at": request["requested_at"],
                "customer_id": request["customer_id"],
                "reason": request["reason"],
                "request_type": request["request_type"],
                "status": status,
                "override_approved": request["override_approved"].lower() == "true",
                "requested_qty": sum(int(line["requested_qty"]) for line in lines),
                "approved_qty": sum(int(line["approved_qty"]) for line in lines),
                "shipment_status": self.shipments.get(request["rma_id"], {}).get(
                    "status", "MISSING" if status != "REJECTED" else "NOT_REQUIRED"
                ),
                "refund_amount_cents": paid,
                "refund_statuses": sorted({row["status"] for row in refunds}),
                "dispositions": sorted({
                    disposition["decision"]
                    for line in lines
                    if (disposition := self.dispositions_by_line.get(line["return_line_id"]))
                }),
                "currency": order["currency"],
            })
        records.sort(key=lambda row: row["requested_at"], reverse=True)
        start = (page - 1) * page_size
        return {
            "items": records[start:start + page_size],
            "page": page,
            "page_size": page_size,
            "total": len(records),
            "pages": max(1, (len(records) + page_size - 1) // page_size),
        }


class DashboardService:
    def __init__(self, data_dir: Path, default_scale: str) -> None:
        self.data_dir = data_dir.resolve()
        self.default_scale = default_scale
        self.views: dict[str, DatasetView] = {}
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not (self.data_dir / default_scale / "metrics.json").is_file():
            self.generate(default_scale)

    def _profile_path(self, scale: str) -> Path:
        if scale not in SCALES:
            raise ValueError("Scale must be starter or full")
        return self.data_dir / scale

    def view(self, scale: str) -> DatasetView:
        directory = self._profile_path(scale)
        if not (directory / "metrics.json").is_file():
            raise FileNotFoundError(f"No {scale} dataset found. Generate it first.")
        if scale not in self.views:
            self.views[scale] = DatasetView(scale, directory)
        return self.views[scale]

    def generate(self, scale: str) -> dict[str, Any]:
        orders, requests, lines = SCALES[scale]
        result = write_exports(
            generate_dataset(orders, requests, lines, SEED),
            self._profile_path(scale),
        )
        self.views[scale] = DatasetView(scale, self._profile_path(scale))
        return result

    def validate(self, scale: str) -> dict[str, Any]:
        result = validate_dataset(load_export(self._profile_path(scale)))
        return result


def create_dashboard_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    data_dir: str | Path = "data",
    scale: str = "starter",
) -> ThreadingHTTPServer:
    if not 0 <= port <= 65535:
        raise ValueError("Port must be between 0 and 65535")
    service = DashboardService(Path(data_dir), scale)
    static_dir = Path(__file__).with_name("static")
    static_files = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/index.html": ("index.html", "text/html; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    }

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "ReturnFlowDashboard/1.0"

        def _send_json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_error_json(self, status: int, message: str) -> None:
            self._send_json(status, {"error": message})

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/"):
                query = parse_qs(parsed.query)
                scale_name = query.get("scale", [service.default_scale])[0]
                try:
                    view = service.view(scale_name)
                    if parsed.path == "/api/summary":
                        self._send_json(200, view.summary())
                    elif parsed.path == "/api/returns":
                        page = int(query.get("page", ["1"])[0])
                        page_size = int(query.get("page_size", ["25"])[0])
                        payload = view.return_records(
                            query.get("status", ["ALL"])[0],
                            query.get("q", [""])[0],
                            page,
                            page_size,
                        )
                        self._send_json(200, payload)
                    else:
                        self._send_error_json(404, "API endpoint not found")
                except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
                    self._send_error_json(400, str(error))
                return

            asset = static_files.get(parsed.path)
            if asset is None:
                self.send_error(404)
                return
            filename, content_type = asset
            body = (static_dir / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path not in {"/api/generate", "/api/validate"}:
                self._send_error_json(404, "API endpoint not found")
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length > 4096:
                    self._send_error_json(413, "Request body is too large")
                    return
                raw_body = self.rfile.read(content_length)
                payload = json.loads(raw_body) if raw_body else {}
                if not isinstance(payload, dict):
                    raise ValueError("JSON request body must be an object")
                scale_name = payload.get("scale", service.default_scale)
                if not isinstance(scale_name, str) or scale_name not in SCALES:
                    raise ValueError("Scale must be starter or full")
                if parsed.path == "/api/generate":
                    result = service.generate(scale_name)
                    self._send_json(200, {
                        "message": f"{scale_name.title()} dataset generated",
                        "counts": result["counts"],
                        "seed": result["seed"],
                        "validation_passed": result["validation_passed"],
                    })
                else:
                    self._send_json(200, service.validate(scale_name))
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
                self._send_error_json(400, str(error))

        def log_message(self, format_string: str, *args: Any) -> None:
            super().log_message(format_string, *args)

    return ThreadingHTTPServer((host, port), DashboardHandler)


def serve_dashboard(host: str, port: int, data_dir: Path, scale: str) -> None:
    server = create_dashboard_server(host, port, data_dir, scale)
    address, bound_port = server.server_address[:2]
    print(f"ReturnFlow dashboard running at http://{address}:{bound_port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping ReturnFlow dashboard.")
    finally:
        server.server_close()
