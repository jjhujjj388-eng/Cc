"""
db.py — Upstash Redis backend.

Replaces the previous MongoDB layer. The async function signatures used by the
rest of the bot are kept identical, so callers do not need to change.

Schema
------
* ``user:{user_id}``                 → JSON-serialised user document (HASH not
                                       used so we can store arbitrary nested
                                       lists/strings cheaply)
* ``users``                          → SET of every user_id seen so far
* ``redeem:{CODE}``                  → JSON-serialised redeem-code document
* ``redeem_codes``                   → SET of all redeem codes
* ``razorpay_sites``                 → SET of every saved Razorpay site URL
"""

from __future__ import annotations

import asyncio
import json

# Local redeem fallback when Upstash SET fails / offline
import os as _os
LOCAL_REDEEM_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "local_redeem_codes.json")

def _local_redeem_load() -> dict:
    try:
        if _os.path.isfile(LOCAL_REDEEM_FILE):
            with open(LOCAL_REDEEM_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _local_redeem_save(data: dict) -> None:
    try:
        with open(LOCAL_REDEEM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=0)
    except Exception as e:
        logger.error(f"local redeem save: {e}")

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from config import (
    DEFAULT_FREE_CREDITS,
    UPSTASH_REDIS_REST_TOKEN,
    UPSTASH_REDIS_REST_URL,
)


logger = logging.getLogger(__name__)


# =====================================================================
# === Default user values (kept compatible with the old Mongo layer) ==
# =====================================================================
DEFAULT_PLAN = "Free"
DEFAULT_STATUS = "Free"
DEFAULT_PLAN_EXPIRY = "N/A"
DEFAULT_KEYS_REDEEMED = 0


# =====================================================================
# === Tiny async REST client for Upstash ==============================
# =====================================================================
class UpstashClient:
    """A minimal async client for the Upstash Redis REST API.

    The REST API accepts commands as a JSON array, e.g. ``["GET", "key"]``,
    and returns ``{"result": ..., "error": ...}``.
    """

    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {token}"}
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            async with self._lock:
                if self._session is None or self._session.closed:
                    self._session = aiohttp.ClientSession(
                        headers=self._headers,
                        timeout=aiohttp.ClientTimeout(total=15),
                    )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def call(self, *args: Any) -> Any:
        """Send a single Upstash command and return the ``result`` field."""
        session = await self._ensure_session()
        payload = [str(a) for a in args]
        try:
            async with session.post(self._base_url, json=payload) as resp:
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"Upstash call {args[:1]} failed: {e}")
            return None
        if isinstance(data, dict) and data.get("error"):
            logger.warning(f"Upstash error for {args[:1]}: {data['error']}")
            return None
        if isinstance(data, dict):
            return data.get("result")
        return data

    async def pipeline(self, commands: List[List[Any]]) -> List[Any]:
        """Execute several commands in a single round-trip via the REST pipeline."""
        if not commands:
            return []
        session = await self._ensure_session()
        url = f"{self._base_url}/pipeline"
        payload = [[str(a) for a in cmd] for cmd in commands]
        try:
            async with session.post(url, json=payload) as resp:
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"Upstash pipeline failed: {e}")
            return [None] * len(commands)
        if not isinstance(data, list):
            return [None] * len(commands)
        out: List[Any] = []
        for entry in data:
            if isinstance(entry, dict):
                if entry.get("error"):
                    logger.warning(f"Upstash pipeline error: {entry['error']}")
                    out.append(None)
                else:
                    out.append(entry.get("result"))
            else:
                out.append(entry)
        return out


_client: Optional[UpstashClient] = None


def _get_client() -> UpstashClient:
    global _client
    if _client is None:
        _client = UpstashClient(UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN)
    return _client


# =====================================================================
# === Internal helpers ================================================
# =====================================================================
def _user_key(user_id: int) -> str:
    return f"user:{int(user_id)}"


def _code_key(code: str) -> str:
    return f"redeem:{str(code).upper()}"


def _default_user_doc(user_id: int) -> Dict[str, Any]:
    return {
        "id": int(user_id),
        "credits": DEFAULT_FREE_CREDITS,
        "plan": DEFAULT_PLAN,
        "status": DEFAULT_STATUS,
        "plan_expiry": DEFAULT_PLAN_EXPIRY,
        "keys_redeemed": DEFAULT_KEYS_REDEEMED,
        "registered_at": datetime.now().strftime("%d-%m-%Y"),
        "custom_urls": [],
        "proxies": [],
        "serp_key": None,
    }


def _decode_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", "ignore")
        except Exception:
            return None
    return str(value)


def _parse_doc(value: Any) -> Optional[Dict[str, Any]]:
    text = _decode_str(value)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# =====================================================================
# === Init ============================================================
# =====================================================================
async def init_db() -> bool:
    """Ping Upstash and confirm credentials work."""
    client = _get_client()
    try:
        result = await client.call("PING")
        if result and str(result).upper() == "PONG":
            logger.info("✅ Upstash Redis connected successfully!")
            return True
        logger.error(f"❌ Upstash Redis PING returned: {result!r}")
        return False
    except Exception as e:
        logger.error(f"❌ Upstash connection failed: {e}")
        return False


# =====================================================================
# === Users ===========================================================
# =====================================================================
async def get_user(user_id: int) -> Dict[str, Any]:
    """Return the user document, creating one with defaults if missing."""
    client = _get_client()
    try:
        raw = await client.call("GET", _user_key(user_id))
        doc = _parse_doc(raw)
        if doc is None:
            new_doc = _default_user_doc(user_id)
            await client.pipeline(
                [
                    ["SET", _user_key(user_id), json.dumps(new_doc)],
                    ["SADD", "users", str(int(user_id))],
                ]
            )
            return new_doc

        # Backfill any missing default keys (for older docs).
        defaults = _default_user_doc(user_id)
        changed = False
        for key, value in defaults.items():
            if key not in doc:
                doc[key] = value
                changed = True
        doc["id"] = int(user_id)
        if changed:
            await client.call("SET", _user_key(user_id), json.dumps(doc))
        return doc
    except Exception as e:
        logger.error(f"❌ get_user({user_id}) failed: {e}")
        return _default_user_doc(user_id)


async def update_user(user_id: int, **kwargs: Any) -> bool:
    """Patch the user document with the supplied fields.

    Defensive against transient Upstash hiccups: if the GET returns no doc
    we double-check with EXISTS before falling back to a fresh default
    document. This prevents an empty-but-existing key (or a momentarily
    failed read) from silently wiping a user's plan/credits.
    """
    if not kwargs:
        return False
    client = _get_client()
    try:
        raw = None
        last_err = None
        for _ in range(3):
            try:
                raw = await client.call("GET", _user_key(user_id))
                break
            except Exception as e:
                last_err = e
                await asyncio.sleep(0.4)
        else:
            logger.error(f"❌ update_user({user_id}) GET failed: {last_err}")
            return False

        doc = _parse_doc(raw)
        if doc is None:
            # Confirm the key really is missing before resetting to defaults.
            exists = 0
            try:
                exists = int(await client.call("EXISTS", _user_key(user_id)) or 0)
            except Exception as e:
                logger.error(
                    f"❌ update_user({user_id}) EXISTS check failed, aborting "
                    f"to avoid wiping user data: {e}"
                )
                return False
            if exists:
                logger.error(
                    f"❌ update_user({user_id}): key exists but doc unparseable, "
                    f"refusing to overwrite."
                )
                return False
            doc = _default_user_doc(user_id)

        for key, value in kwargs.items():
            if value is None:
                continue
            doc[key] = value
        doc["id"] = int(user_id)
        await client.pipeline(
            [
                ["SET", _user_key(user_id), json.dumps(doc)],
                ["SADD", "users", str(int(user_id))],
            ]
        )
        return True
    except Exception as e:
        logger.error(f"❌ update_user({user_id}) failed: {e}")
        return False


async def add_custom_url(user_id: int, url: str) -> bool:
    if not url:
        return False
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    user = await get_user(user_id)
    urls = user.get("custom_urls", []) or []
    if url in urls:
        return False
    urls.append(url)
    return await update_user(user_id, custom_urls=urls)


async def remove_custom_url(user_id: int, url: str) -> bool:
    user = await get_user(user_id)
    urls = user.get("custom_urls", []) or []
    if url not in urls:
        return False
    urls.remove(url)
    return await update_user(user_id, custom_urls=urls)


async def clear_all_custom_urls(user_id: int) -> bool:
    return await update_user(user_id, custom_urls=[])


async def get_all_users() -> List[Dict[str, Any]]:
    client = _get_client()
    try:
        ids = await client.call("SMEMBERS", "users") or []
        if not ids:
            return []
        ids = [_decode_str(i) for i in ids if i is not None]
        keys = [_user_key(int(i)) for i in ids if str(i).lstrip("-").isdigit()]
        if not keys:
            return []
        raw_docs = await client.call("MGET", *keys) or []
        users: List[Dict[str, Any]] = []
        for raw in raw_docs:
            doc = _parse_doc(raw)
            if not doc:
                continue
            users.append(
                {
                    "id": doc.get("id"),
                    "credits": doc.get("credits", DEFAULT_FREE_CREDITS),
                    "plan": doc.get("plan", DEFAULT_PLAN),
                    "status": doc.get("status", DEFAULT_STATUS),
                    "custom_urls": doc.get("custom_urls", []),
                    "serp_key": doc.get("serp_key"),
                    "registered_at": doc.get("registered_at", "Unknown"),
                }
            )
        return users
    except Exception as e:
        logger.error(f"❌ get_all_users failed: {e}")
        return []


async def get_user_count() -> int:
    client = _get_client()
    try:
        result = await client.call("SCARD", "users")
        return int(result or 0)
    except Exception as e:
        logger.error(f"❌ get_user_count failed: {e}")
        return 0


# =====================================================================
# === Redeem codes ====================================================
# =====================================================================
async def add_redeem_code(code: str, plan_name: str, credits: int, days: int) -> bool:
    upper = str(code).strip().upper()
    doc = {
        "code": upper,
        "plan": plan_name,
        "credits": int(credits),
        "days": int(days),
        "used": False,
        "used_by": None,
        "used_at": None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    ok = False
    try:
        client = _get_client()
        r1 = await client.call("SET", _code_key(upper), json.dumps(doc))
        await client.call("SADD", "redeem_codes", upper)
        if r1 is not None:
            ok = True
            logger.info(f"Redeem code saved Upstash: {upper}")
    except Exception as e:
        logger.error(f"❌ add_redeem_code Upstash failed: {e}")
    try:
        data = _local_redeem_load()
        data[upper] = doc
        _local_redeem_save(data)
        ok = True
        logger.info(f"Redeem code saved local: {upper}")
    except Exception as e:
        logger.error(f"❌ local redeem save failed: {e}")
    return ok


async def get_redeem_code(code: str) -> Optional[Dict[str, Any]]:
    """Return the code document only if it exists AND is unused."""
    upper = str(code).strip().upper()
    try:
        client = _get_client()
        raw = await client.call("GET", _code_key(upper))
        doc = _parse_doc(raw)
        if doc and not doc.get("used"):
            return doc
        if doc and doc.get("used"):
            return None
    except Exception as e:
        logger.error(f"❌ get_redeem_code Upstash failed: {e}")
    try:
        data = _local_redeem_load()
        doc = data.get(upper)
        if doc and not doc.get("used"):
            return doc
    except Exception as e:
        logger.error(f"❌ get_redeem_code local failed: {e}")
    return None


async def mark_code_used(code: str, user_id: int) -> bool:
    upper = str(code).strip().upper()
    doc = None
    try:
        client = _get_client()
        raw = await client.call("GET", _code_key(upper))
        doc = _parse_doc(raw)
    except Exception as e:
        logger.error(f"mark_code_used GET: {e}")
    if not doc:
        try:
            data = _local_redeem_load()
            doc = data.get(upper)
        except Exception:
            doc = None
    if not doc:
        return False
    doc["used"] = True
    doc["used_by"] = int(user_id)
    doc["used_at"] = datetime.now().isoformat(timespec="seconds")
    try:
        client = _get_client()
        await client.call("SET", _code_key(upper), json.dumps(doc))
    except Exception as e:
        logger.error(f"mark_code_used Upstash SET: {e}")
    try:
        data = _local_redeem_load()
        data[upper] = doc
        _local_redeem_save(data)
    except Exception as e:
        logger.error(f"mark_code_used local: {e}")
    return True


# =====================================================================
# === Razorpay site pool ==============================================
# =====================================================================
async def add_razorpay_site(url: str) -> bool:
    """Returns True if newly added, False if already present (or on error)."""
    client = _get_client()
    try:
        url = url.strip()
        if not url:
            return False
        result = await client.call("SADD", "razorpay_sites", url)
        try:
            return int(result) > 0
        except (TypeError, ValueError):
            return False
    except Exception as e:
        logger.error(f"❌ add_razorpay_site('{url}') failed: {e}")
        return False


async def remove_razorpay_site(url: str) -> bool:
    client = _get_client()
    try:
        result = await client.call("SREM", "razorpay_sites", url.strip())
        try:
            return int(result) > 0
        except (TypeError, ValueError):
            return False
    except Exception as e:
        logger.error(f"❌ remove_razorpay_site('{url}') failed: {e}")
        return False


async def remove_all_razorpay_sites() -> int:
    client = _get_client()
    try:
        members = await client.call("SMEMBERS", "razorpay_sites") or []
        members = [_decode_str(m) for m in members if m is not None]
        if not members:
            return 0
        await client.call("DEL", "razorpay_sites")
        return len(members)
    except Exception as e:
        logger.error(f"❌ remove_all_razorpay_sites failed: {e}")
        return 0


async def get_all_razorpay_sites() -> List[str]:
    client = _get_client()
    try:
        members = await client.call("SMEMBERS", "razorpay_sites") or []
        return [_decode_str(m) for m in members if m is not None]
    except Exception as e:
        logger.error(f"❌ get_all_razorpay_sites failed: {e}")
        return []


# =====================================================================
# === Backwards-compat shims =========================================
# Some callers reference ``users_collection`` / ``redeem_codes_collection``
# directly (e.g. for indexing). Provide harmless stand-ins so imports do not
# blow up; they are no-ops for the REST backend.
# =====================================================================
class _NoopCollection:  # pragma: no cover - tiny shim
    async def create_index(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def find_one(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def insert_one(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def update_one(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def delete_one(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def delete_many(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def count_documents(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def find(self, *args: Any, **kwargs: Any):  # pragma: no cover
        async def _empty():
            if False:
                yield None  # noqa: PLR0917
        return _empty()


users_collection = _NoopCollection()
redeem_codes_collection = _NoopCollection()
razorpay_sites_collection = _NoopCollection()


async def create_redeem_codes_indexes() -> None:
    """Old Mongo-era helper kept for compatibility — Redis needs no indexes."""
    return None
