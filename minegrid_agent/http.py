from __future__ import annotations

import json
import time
import urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0 (minegrid-agent)", "Accept": "application/json"}


def get_json(url: str, timeout: int = 15, retries: int = 3) -> dict:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # network errors, 429, bad JSON
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed after {retries} tries: {last_exc}")


def post_json(url: str, payload: dict, timeout: int = 10) -> int:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**HEADERS, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status
