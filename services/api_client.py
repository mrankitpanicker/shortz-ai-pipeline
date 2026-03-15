"""
api_client.py — HTTP client wrapper for the Shortz FastAPI server.

Provides a clean Python interface for the /generate and /status endpoints
so that other modules (especially the GUI bridge) never construct raw HTTP
requests themselves.

Usage:
    from services.api_client import ShortzAPIClient

    client = ShortzAPIClient()              # defaults to localhost:8000
    job    = client.submit_job()            # POST /generate
    status = client.get_status(job["job_id"])  # GET /status/{id}
"""

import json
import urllib.request
import urllib.error
from typing import Any


class ShortzAPIClient:
    """Thin HTTP client for the Shortz FastAPI server."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def submit_job(self) -> dict[str, Any]:
        """
        POST /generate  →  {"job_id": "...", "status": "queued"}

        Raises ConnectionError if the API is unreachable.
        """
        return self._post("/generate")

    def get_status(self, job_id: str) -> dict[str, Any]:
        """
        GET /status/{job_id}  →  {"status": "running", ...}

        Returns {"error": "job not found"} if the job_id doesn't exist.
        Raises ConnectionError if the API is unreachable.
        """
        return self._get(f"/status/{job_id}")

    def health_check(self) -> bool:
        """Return True if the API responds to any request."""
        try:
            self._get("/docs")
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # INTERNAL
    # ------------------------------------------------------------------

    def _get(self, path: str, timeout: int = 10) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ConnectionError(f"API unreachable: {exc}") from exc

    def _post(self, path: str, data: bytes = b"", timeout: int = 10) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            req = urllib.request.Request(
                url,
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ConnectionError(f"API unreachable: {exc}") from exc
