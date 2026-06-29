"""
config.py — central settings and shared helpers for the TLDCRM dashboard.

Loads credentials from .env once, exposes them as constants, and provides the
small request helpers that the probe scripts each used to re-define. Import
from here instead of re-reading os.environ or re-writing unwrap()/get() in
every file.
"""
import os
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# --- Credentials (from .env) -------------------------------------------------
TLD_BASE_URL = os.getenv("TLD_BASE_URL", "").strip().rstrip("/")
TLD_API_ID   = os.getenv("TLD_API_ID", "").strip()
TLD_API_KEY  = os.getenv("TLD_API_KEY", "").strip()

# --- Server (used by app.py) -------------------------------------------------
PORT       = int(os.getenv("PORT", "5050"))
NO_BROWSER = bool(os.getenv("NO_BROWSER"))

# --- Business constants ------------------------------------------------------
FALCON_VENDOR_ID   = 14646                 # the "Falcon" lead source
CONVERTED_STATUSES = {"active", "sale"}    # a billable Falcon lead = converted if its status is one of these
EXCLUDED_POLICY_CARRIERS = {"GTL"}         # carriers NOT counted in "Policies Sold" (separate product line); compared uppercased

# --- HTTP --------------------------------------------------------------------
TIMEOUT = 30                               # seconds — standardized across all callers
POLICY_TIMEOUT = 60                        # probe_policy.py pulls one big joined record — give it longer

API_ID_HEADER  = "tld-api-id"
API_KEY_HEADER = "tld-api-key"

# Full headers for egress calls sent as GET with a JSON body.
HEADERS = {
    API_ID_HEADER:  TLD_API_ID,
    API_KEY_HEADER: TLD_API_KEY,
    "Content-Type": "application/json",
    "Accept":       "application/json",
}

# Headers for plain GETs (e.g. /docs/columns or param-based queries).
HEADERS_GET = {
    API_ID_HEADER:  TLD_API_ID,
    API_KEY_HEADER: TLD_API_KEY,
    "Accept":       "application/json",
}


def have_creds():
    """True when all three TLD credentials are present."""
    return bool(TLD_BASE_URL and TLD_API_ID and TLD_API_KEY)


def require_creds():
    """Exit with a friendly message if credentials aren't configured."""
    if not have_creds():
        raise SystemExit("Fill TLD_BASE_URL / TLD_API_ID / TLD_API_KEY in .env first.")


def unwrap(payload):
    """TLD wraps data as {"response": {"results": [...]}}. Return the inner list/object."""
    if isinstance(payload, dict):
        inner = payload.get("response", payload)
        return inner.get("results", inner) if isinstance(inner, dict) else inner
    return payload


def egress_get(path, body=None, timeout=TIMEOUT):
    """GET /api/egress/<path> with an optional JSON body; returns unwrapped JSON."""
    r = requests.get(f"{TLD_BASE_URL}/api/egress/{path.lstrip('/')}",
                     headers=HEADERS, json=body, timeout=timeout)
    return unwrap(r.json())
