"""One HTTP helper for every public market-data venue.

Retries transient failures (connection resets, timeouts, 429/5xx) with a
short backoff, because a multi-hundred-request history build shouldn't die on
one dropped connection. Sends a browser-style User-Agent: some venues (Yahoo,
Bitstamp) reset connections from unfamiliar clients.
"""

from __future__ import annotations

import time

import requests

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
RETRY_STATUS = {429, 500, 502, 503, 504}
ATTEMPTS = 4

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


def get_json(url: str, params: dict | None = None, timeout: float = 20):
    delay = 1.0
    for attempt in range(1, ATTEMPTS + 1):
        try:
            response = _session.get(url, params=params, timeout=timeout)
            if response.status_code in RETRY_STATUS and attempt < ATTEMPTS:
                time.sleep(delay)
                delay *= 2
                continue
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout):
            if attempt == ATTEMPTS:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")
