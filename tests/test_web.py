from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from returnflow.export import write_exports
from returnflow.generator import generate_dataset
from returnflow.web import create_dashboard_server


class DashboardApiTests(unittest.TestCase):
    def test_dashboard_assets_and_workflow_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary) / "data"
            write_exports(generate_dataset(60, 12, 18, seed=20261022), data_dir / "starter")
            server = create_dashboard_server("127.0.0.1", 0, data_dir, "starter")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(f"{base_url}/") as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(b"Returns overview", response.read())
                with urlopen(f"{base_url}/app.js") as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn(b"/api/summary", response.read())
                with urlopen(f"{base_url}/api/summary?scale=starter") as response:
                    summary = json.loads(response.read())
                self.assertEqual(summary["counts"]["orders"], 60)
                self.assertEqual(len(summary["exceptions"]), 6)

                with urlopen(f"{base_url}/api/returns?status=REJECTED&page_size=5") as response:
                    returns = json.loads(response.read())
                self.assertLessEqual(len(returns["items"]), 5)
                self.assertTrue(all(row["status"] == "REJECTED" for row in returns["items"]))
                self.assertTrue(all(row["shipment_status"] == "NOT_REQUIRED" for row in returns["items"]))

                request = Request(
                    f"{base_url}/api/validate",
                    data=json.dumps({"scale": "starter"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urlopen(request) as response:
                    validation = json.loads(response.read())
                self.assertTrue(validation["pass"])
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()


if __name__ == "__main__":
    unittest.main()
