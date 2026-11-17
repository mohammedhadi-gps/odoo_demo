#!/usr/bin/env python3
"""
Odoo API key smoke-test
========================
Run:
    python scripts/test_odoo_api_key.py

Set these environment variables (or edit the constants below):
    ODOO_URL      e.g. https://odoo17-dr.greenpowersystems.co.in/jsonrpc
    ODOO_DB       your database name
    ODOO_USER_ID  numeric user ID (integer)
    ODOO_API_KEY  API key from Odoo user preferences

What this script does
---------------------
1. Authenticates using the API key (no password needed).
2. Lists every non-transient model, then runs search_count on each to show
   which are readable and which are denied.
3. Prints record counts for models you likely care about:
   res.partner, purchase.order, account.move, account.tax, project.project
4. Tries to create a test partner — this SHOULD be rejected if the user is
   read-only.  If it succeeds, the script warns you and deletes the record.
"""

import json
import os
import sys
import urllib.request

# ── Configuration ────────────────────────────────────────────────────────────
URL      = os.environ.get("ODOO_URL",     "https://odoo17-dr.greenpowersystems.co.in/jsonrpc")
DB       = os.environ.get("ODOO_DB",      "")
USER_ID  = int(os.environ.get("ODOO_USER_ID", "0"))
API_KEY  = os.environ.get("ODOO_API_KEY", "")

# Models to show counts for in Step 3
MODELS_OF_INTEREST = [
    "res.partner",
    "purchase.order",
    "purchase.order.line",
    "stock.picking",
    "account.move",
    "account.tax",
    "project.project",
    "purchase.requisition",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def rpc(model: str, method: str, args: list, kwargs: dict | None = None) -> object:
    """Send one JSON-RPC execute_kw call. Raises RuntimeError on Odoo-level errors."""
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "id": 1,
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [DB, USER_ID, API_KEY, model, method, args, kwargs or {}],
        },
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # ignore SSL for self-signed certs on internal servers
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        result = json.loads(resp.read())

    if "error" in result:
        msg = result["error"].get("data", {}).get("message") or str(result["error"])
        raise RuntimeError(msg)
    return result.get("result")


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


# ── Step 0: Validate config ───────────────────────────────────────────────────
section("0 · Config check")
missing = [k for k, v in [("ODOO_URL", URL), ("ODOO_DB", DB),
                           ("ODOO_USER_ID", USER_ID), ("ODOO_API_KEY", API_KEY)]
           if not v]
if missing:
    print(f"  ✗  Missing: {', '.join(missing)}")
    print("     Set them as environment variables or edit the constants at the top of this file.")
    sys.exit(1)
print(f"  URL      : {URL}")
print(f"  DB       : {DB}")
print(f"  USER_ID  : {USER_ID}")
print(f"  API_KEY  : {API_KEY[:6]}{'*' * (len(API_KEY) - 6)}")


# ── Step 1: Authenticate ──────────────────────────────────────────────────────
section("1 · Authentication")
try:
    # Read the user record — if the API key is wrong this raises an error
    user = rpc("res.users", "read", [[USER_ID]], {"fields": ["name", "login", "groups_id"]})
    print(f"  ✓  Authenticated as: {user[0]['name']} ({user[0]['login']})")
except RuntimeError as e:
    print(f"  ✗  Authentication failed: {e}")
    sys.exit(1)


# ── Step 2: Scan all non-transient models ─────────────────────────────────────
section("2 · Model access scan")
print("  Fetching model list …")
try:
    all_models = rpc(
        "ir.model", "search_read",
        [[["transient", "=", False]]],
        {"fields": ["model", "name"], "order": "model asc"},
    )
except RuntimeError as e:
    print(f"  ✗  Could not fetch model list: {e}")
    all_models = []

readable, denied, errors = [], [], []
for m in all_models:
    model_name = m["model"]
    try:
        count = rpc(model_name, "search_count", [[]])
        readable.append((model_name, count))
    except RuntimeError as e:
        msg = str(e)
        if "access" in msg.lower() or "denied" in msg.lower() or "not allowed" in msg.lower():
            denied.append(model_name)
        else:
            errors.append((model_name, msg))

print(f"\n  ✓  Readable models : {len(readable)}")
print(f"  ✗  Access denied   : {len(denied)}")
print(f"  ?  Other errors    : {len(errors)}")

if denied:
    print("\n  Denied models (sample, up to 20):")
    for m in denied[:20]:
        print(f"    - {m}")

if errors:
    print("\n  Other errors (sample, up to 10):")
    for m, msg in errors[:10]:
        print(f"    - {m}: {msg[:80]}")


# ── Step 3: Record counts for key models ─────────────────────────────────────
section("3 · Record counts for models of interest")
max_len = max(len(m) for m in MODELS_OF_INTEREST)
for model_name in MODELS_OF_INTEREST:
    try:
        count = rpc(model_name, "search_count", [[]])
        print(f"  {model_name:<{max_len}}  {count:>8} records  ✓")
    except RuntimeError as e:
        msg = str(e)
        label = "access denied" if "access" in msg.lower() or "denied" in msg.lower() else msg[:60]
        print(f"  {model_name:<{max_len}}  {'':>8}          ✗  {label}")


# ── Step 4: Write-access check ────────────────────────────────────────────────
section("4 · Write-access check (should be REJECTED for read-only user)")
test_record_id = None
try:
    test_record_id = rpc(
        "res.partner", "create",
        [{"name": "__api_key_test_DO_NOT_USE__"}],
    )
    print(f"  ⚠  WARNING: Create succeeded (record id={test_record_id}).")
    print("     Your API key user has WRITE access — it is NOT read-only.")
    print("     Deleting the test record …")
    rpc("res.partner", "unlink", [[test_record_id]])
    print(f"  ✓  Test record deleted.")
except RuntimeError as e:
    msg = str(e)
    if "access" in msg.lower() or "denied" in msg.lower() or "not allowed" in msg.lower():
        print("  ✓  Create correctly rejected — user is read-only.")
    else:
        print(f"  ?  Unexpected error during create test: {msg}")


# ── Summary ───────────────────────────────────────────────────────────────────
section("Summary")
print("  Authentication  : ✓")
print(f"  Readable models : {len(readable)}")
print(f"  Denied models   : {len(denied)}")
write_status = "⚠  user has write access" if test_record_id else "✓  user is read-only"
print(f"  Write access    : {write_status}")
print()
