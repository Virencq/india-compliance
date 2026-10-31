"""Unauthenticated Tally GSTIN lookup used for party/address autofill.

This is an unofficial public website endpoint, not a GSTN/GSP API. Keep the
request server-side, cache successful responses, and let callers fall back to
the configured India Compliance GST provider when it is unavailable.
"""

import requests
import frappe

from india_compliance.gst_india.utils import get_state

TALLY_GSTIN_LOOKUP_URL = (
    "https://tallysolutions.com/wp-content/themes/tally/api/gstin-serach-api.php"
)
CACHE_TTL_SECONDS = 60 * 60 * 24 * 180
REQUEST_TIMEOUT_SECONDS = 4


def get_tally_gstin_info(gstin):
    """Return GSTN-shaped taxpayer data, or None when Tally cannot serve it."""
    cache_key = f"tally_gstin_info:{gstin}"
    cached = frappe.cache.get_value(cache_key)
    if cached:
        return frappe._dict(cached)

    try:
        response = requests.post(
            TALLY_GSTIN_LOOKUP_URL,
            data={"gstin": gstin},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        frappe.logger("india_compliance").warning("Tally GSTIN lookup unavailable: %s", exc)
        return None

    if not isinstance(data, dict):
        return None

    status = data.get("status")
    is_success = status is True or status == 1 or status == "1"
    if not is_success or str(data.get("validation_status", "")).upper() != "VALID":
        return None

    legal_name = (data.get("legal_name") or "").strip()
    trade_name = (data.get("trade_name") or "").strip()
    if not (legal_name or trade_name):
        return None

    state = (data.get("state") or data.get("state_name") or "").strip()
    if not state:
        state = get_state(gstin[:2]) or ""

    address = (data.get("address") or "").strip()
    pincode = str(data.get("pincode") or "").strip()
    district = (data.get("district") or data.get("city") or "").strip()

    # Preserve the GSTN response shape expected by gstin_info._get_address().
    taxpayer = frappe._dict(
        gstin=gstin,
        lgnm=legal_name,
        tradeNam=trade_name,
        ctb=(data.get("business_constitution") or "").strip(),
        dty=(data.get("registration_type") or "").strip(),
        sts=(data.get("gstin_status") or "").strip(),
        rgdt=(data.get("registration_date") or "").strip(),
        pradr=frappe._dict(
            addr=frappe._dict(
                bno=address,
                dst=district,
                stcd=state,
                pncd=pincode,
            )
        ),
    )

    frappe.cache.set_value(
        cache_key,
        dict(taxpayer),
        expires_in_sec=CACHE_TTL_SECONDS,
    )
    return taxpayer
