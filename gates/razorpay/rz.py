"""
gates/razorpay/rz.py

Charging commands for the Razorpay gate.

* ``/rz <card>``        — Single check. Picks one random site from the global pool.
* ``/mrz <cards...>``   — Mass check, concurrent, with a Stop button.
* ``/rztxt <file/text>``— Mass check from a .txt file (or replied text). Runs up
  to RZTXT_CONCURRENCY cards concurrently, each card uses a different site + proxy combo.

The per-card result uses the dedicated Razorpay UI template (Chncxbot style)
with Support / Plans inline buttons.
"""

from __future__ import annotations

import asyncio
import html
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, ContextTypes

from bin import get_bin_info
from config import (
    ADMIN_IDS,
    AUTHORIZATION_CONTACT,
    BOT_USERNAME,
    DEVELOPER_LINK,
    DEVELOPER_NAME,
    OFFICIAL_CHANNEL_LINK,
    OFFICIAL_CHANNEL_USERNAME,
    OWNER_ID,
    PLAN_DETAILS,
    PUBLIC_GROUP_ID,
)
from db import get_all_razorpay_sites, get_user, update_user
from force_join import force_join
from utils.credits import consume_credit, is_unlimited, add_credits
from utils.decorators import enforce_cooldown
from utils.helpers import escape_html

from utils.styled_buttons import styled_button
from utils.mass_progress import render_mass_progress, stop_keyboard

from .common import (
    MAX_ORDER_RETRIES,
    STATUS_APPROVED,
    STATUS_CHARGED,
    STATUS_DECLINED,
    STATUS_ERROR,
    auto_remove_site_if_dead,
    call_razorpay_api,
    classify_response,
    extract_cards_from_text,
    get_proxies_for_user,
    is_order_id_not_found,
    is_retryable_error,
    is_site_killed_by,
    normalize_card,
    pair_sites_with_proxies,
    pick_random,
)


# Premium emoji ids requested by the owner for the per-card result buttons.
SUPPORT_ICON_ID = "6129705083501293112"
CHANNEL_ICON_ID = "6154386220441933028"


def _channel_url() -> str:
    """Prefer the public username link; fall back to the invite link."""
    if OFFICIAL_CHANNEL_USERNAME:
        return f"https://t.me/{OFFICIAL_CHANNEL_USERNAME}"
    return OFFICIAL_CHANNEL_LINK or "https://t.me/"

# Premium custom-emoji ids used for the per-card Status line.
STATUS_EMOJI_IDS = {
    STATUS_CHARGED: "5041796412954641308",
    STATUS_APPROVED: "5039844895779455925",
    STATUS_DECLINED: "5855085385696156087",
    STATUS_ERROR: "5210952531676504517",
}
STATUS_FALLBACK_EMOJI = {
    STATUS_CHARGED: "💎",
    STATUS_APPROVED: "✅",
    STATUS_DECLINED: "❌",
    STATUS_ERROR: "⚠️",
}
STATUS_LABEL = {
    STATUS_CHARGED: "Charged",
    STATUS_APPROVED: "Approved",
    STATUS_DECLINED: "Declined",
    STATUS_ERROR: "Error",
}


logger = logging.getLogger(__name__)


# ===== CONFIG =====
RZTXT_CONCURRENCY = 30
RZTXT_TIMEOUT = 35  # per-card upstream API timeout (seconds)
ACTIVE_MASS: Dict[int, bool] = {}
ACTIVE_MASS_STOP: Dict[int, asyncio.Event] = {}


# =====================================================================
# === HELPERS — status flag, plan badge, BIN block ====================
# =====================================================================
def _status_flag(category: str) -> str:
    """HTML-safe status badge that uses premium custom emojis."""
    label = STATUS_LABEL.get(category, "Error")
    fallback = STATUS_FALLBACK_EMOJI.get(category, "⚠️")
    emoji_id = STATUS_EMOJI_IDS.get(category)
    if emoji_id:
        return f"{label} <tg-emoji emoji-id='{emoji_id}'>{fallback}</tg-emoji>"
    return f"{label} {fallback}"


def _plan_badge(plan: str) -> str:
    p = (plan or "").lower()
    if "owner" in p:
        return "👑"
    if "admin" in p:
        return "🛡️"
    if "diamond" in p:
        return "🔷"
    if "platinum" in p:
        return "💎"
    if "gold" in p:
        return "🥇"
    if "silver" in p:
        return "🥈"
    if "trial" in p:
        return "🧪"
    if "prime" in p:
        return "🏆"
    if "premium" in p:
        return "✨"
    if "plus" in p:
        return "➕"
    return "🎟️"


async def _user_plan_label(user_id: int) -> Tuple[str, str]:
    """Return (plan_name, plan_badge) for the given user id."""
    if user_id == OWNER_ID:
        return "Owner", _plan_badge("owner")
    if user_id in ADMIN_IDS:
        return "Admin", _plan_badge("admin")
    try:
        data = await get_user(user_id) or {}
        plan = str(data.get("plan", "Free")) or "Free"
        return plan, _plan_badge(plan)
    except Exception:
        return "Free", "🎟️"


def _bin_block_sync(card: str, info: Dict[str, Any]) -> Dict[str, str]:
    return {
        "bin": card[:6],
        "vendor": info.get("scheme") or "Unknown",
        "type": info.get("type") or "Unknown",
        "level": info.get("brand") or "Unknown",
        "bank": info.get("bank") or "Unknown",
        "country": info.get("country") or "Unknown",
        "flag": info.get("country_emoji") or "🏳️",
    }


async def _bin_block(card: str) -> Dict[str, str]:
    try:
        info = await get_bin_info(card[:6]) or {}
    except Exception:
        info = {}
    return _bin_block_sync(card, info)


# =====================================================================
# === Main UI template ================================================
# =====================================================================
def _bot_handle() -> str:
    if BOT_USERNAME:
        cap = BOT_USERNAME[0].upper() + BOT_USERNAME[1:]
        return f"{cap}"
    return "Chncxbot"


from utils.cards_ui import (
    result_buttons as _result_buttons,
    processing_text as _ui_processing_text,
    format_card_result as _ui_format_card_result,
    CHARGED as UI_CHARGED,
    APPROVED as UI_APPROVED,
    DECLINED as UI_DECLINED,
    ERROR as UI_ERROR,
)


_RZ_UI_BUCKET = {
    STATUS_CHARGED: UI_CHARGED,
    STATUS_APPROVED: UI_APPROVED,
    STATUS_DECLINED: UI_DECLINED,
    STATUS_ERROR: UI_ERROR,
}


async def _render_razorpay_card(
    *,
    card: str,
    user_id: int,
    profile_html: str,
    api_response: Dict[str, Any],
    elapsed: float,
    user=None,
) -> Tuple[str, str]:
    """Build the per-card final message in the shared PayPal-style template.

    Returns ``(status_category, final_text)``.
    """
    category = classify_response(api_response)
    raw_response = api_response.get("Response") or "N/A"
    amount = api_response.get("Amount") or "1₹"
    gateway = api_response.get("Gate") or "Razorpay"
    gateway_label = f"{gateway} {amount}".strip()

    plan, badge = await _user_plan_label(user_id)
    plan_label = f"{plan} {badge}".strip()

    final = await _ui_format_card_result(
        card=card,
        gateway=gateway_label,
        response=raw_response,
        status=_RZ_UI_BUCKET.get(category, UI_ERROR),
        elapsed=elapsed,
        user=user,
        user_mention_html=profile_html,
        plan_label=plan_label,
    )
    return category, final


def _processing_text(card: str, gateway: str = "Razorpay 1₹") -> str:
    return _ui_processing_text(card, gateway)


def _processed_text(card: str, gateway: str = "Razorpay 1₹") -> str:
    # Same as processing — kept for callers that edit between phases.
    return _ui_processing_text(card, gateway)


def _profile_html(user) -> str:
    name = getattr(user, "first_name", None) or "User"
    if getattr(user, "last_name", None):
        name += f" {user.last_name}"
    return f'<a href="tg://user?id={user.id}">{escape_html(name)}</a>'


_HIT_STATUS_EMOJI = {
    "charged": ("5041796412954641308", "💎"),
    "approved": ("5125343104638912114", "✅"),
    "declined": ("5855085385696156087", "❌"),
}


def _hit_status_html(status_label: str) -> str:
    eid, fb = _HIT_STATUS_EMOJI.get((status_label or "").strip().lower(), ("", ""))
    safe = escape_html(status_label)
    if eid:
        return f'{safe} <tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'
    return safe


async def _send_hit(
    context: ContextTypes.DEFAULT_TYPE,
    user,
    card: str,
    status_label: str,
    response: str,
    gateway: str = "Razorpay 1₹",
) -> None:
    """Broadcast a successful Razorpay hit to the public group (with bot link preview as bottom box)."""
    bot_link = f'<a href="https://t.me/{BOT_USERNAME}">𝘚𝘱𝘢𝘤𝘦 𝘊𝘩𝘬</a>'
    profile = _profile_html(user)
    hit_message = (
        '<tg-emoji emoji-id="5219804923130038865">💎</tg-emoji> '
        '<b>𝑯𝑰𝑻 𝑫𝒆𝒕𝒆𝒄𝒕𝒆𝒅</b> '
        '<tg-emoji emoji-id="4916036072560919511">💎</tg-emoji>\n'
        '━━━━━━━━\n'
        f'𝘜𝘴𝘦𝘳 ➞ {profile}\n'
        f'𝘚𝘵𝘢𝘵𝘶𝘴 ➞ {_hit_status_html(status_label)}\n'
        f'𝘙𝘦𝘴𝘱𝘰𝘯𝘴𝘦 ➞ <code>{escape_html(response)}</code>\n'
        f'𝘎𝘢𝘵𝘦𝘸𝘢𝘺 ➞ {escape_html(gateway)}\n'
        '━━━━━━━━\n'
        f'𝑯𝑰𝑻 𝑭𝒓𝒐𝒎 ➞ {bot_link}'
    )
    try:
        await context.bot.send_message(
            chat_id=PUBLIC_GROUP_ID,
            text=hit_message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
    except Exception as e:
        logger.warning(f"send_hit (razorpay) failed: {e}")


# =====================================================================
# === Plans callback (used by Support/Plans button) ===================
# =====================================================================
async def plans_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Drop a full plan-details message when the inline 'Plans' button is tapped."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    chat_id = query.message.chat.id if query.message else query.from_user.id

    try:
        from tools.plan import build_plan_message
        text, keyboard = await build_plan_message(query.from_user.id)
    except Exception as e:
        logger.warning(f"plans_info: build_plan_message failed: {e}")
        text, keyboard = (
            "💎 Use <code>/plan</code> to see all subscription plans.",
            None,
        )

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"plans_info: send_message failed: {e}")


# =====================================================================
# === Site / proxy guard ==============================================
# =====================================================================
async def _ensure_sites_and_proxies(
    update: Update, user_id: int
) -> Optional[Tuple[List[str], List[str]]]:
    sites = await get_all_razorpay_sites()
    if not sites:
        await update.message.reply_text(
            "📭 <b>No Razorpay sites configured.</b>\n"
            "Owner must add some via <code>/addrz</code> first.",
            parse_mode=ParseMode.HTML,
        )
        return None

    proxies = await get_proxies_for_user(user_id)
    if not proxies:
        await update.message.reply_text(
            "❌ <b>No proxies found.</b>\n"
            "Add proxies via <code>/addpxy</code> before using Razorpay gates.",
            parse_mode=ParseMode.HTML,
        )
        return None
    return sites, proxies


# =====================================================================
# /rz – SINGLE
# =====================================================================
@force_join
async def rz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await enforce_cooldown(user.id, update):
        return

    raw = ""
    if context.args:
        raw = " ".join(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        raw = update.message.reply_to_message.text

    card = normalize_card(raw)
    if not card:
        await update.message.reply_text(
            "<b>Usage:</b> <code>/rz cc|mm|yy|cvv</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    pair = await _ensure_sites_and_proxies(update, user.id)
    if pair is None:
        return
    sites, proxies = pair

    if not await consume_credit(user.id):
        await update.message.reply_text(
            "❌ Not enough credits.", parse_mode=ParseMode.HTML
        )
        return

    site = pick_random(sites)
    proxy = pick_random(proxies) or ""

    loading_msg = await update.message.reply_text(
        _processing_text(card), parse_mode=ParseMode.HTML
    )

    start = time.time()
    api_response = await call_razorpay_api(card, site, proxy)
    # Silent retry on "order_id not found" with different site/proxy
    for _retry in range(MAX_ORDER_RETRIES):
        if not is_retryable_error(api_response):
            break
        site = pick_random(sites)
        proxy = pick_random(proxies) or ""
        api_response = await call_razorpay_api(card, site, proxy)
    elapsed = time.time() - start

    if is_site_killed_by(api_response):
        await auto_remove_site_if_dead(api_response)

    try:
        await loading_msg.edit_text(
            _processed_text(card), parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

    category, final = await _render_razorpay_card(
        card=card,
        user_id=user.id,
        profile_html=_profile_html(user),
        api_response=api_response,
        elapsed=elapsed,
    )

    try:
        await loading_msg.edit_text(
            final,
            parse_mode=ParseMode.HTML,
            reply_markup=_result_buttons(),
            disable_web_page_preview=True,
        )
    except Exception:
        await update.message.reply_text(
            final,
            parse_mode=ParseMode.HTML,
            reply_markup=_result_buttons(),
            disable_web_page_preview=True,
        )

    if category in (STATUS_CHARGED, STATUS_APPROVED):
        await _send_hit(
            context,
            user,
            card,
            STATUS_LABEL.get(category, category),
            api_response.get("Response") or "",
        )


# =====================================================================
# /mrz – MASS, ONE BY ONE
# =====================================================================
@force_join
async def mrz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if not await enforce_cooldown(user_id, update):
        return

    raw = ""
    if context.args:
        raw = " ".join(context.args)
    elif update.message.reply_to_message:
        rep = update.message.reply_to_message
        if rep.text:
            raw = rep.text
        elif rep.document:
            try:
                file = await context.bot.get_file(rep.document.file_id)
                raw = (await file.download_as_bytearray()).decode("utf-8", "ignore")
            except Exception as e:
                logger.warning(f"mrz: failed to read replied document: {e}")

    cards = extract_cards_from_text(raw)
    if not cards:
        await update.message.reply_text(
            "<b>Usage:</b> <code>/mrz cc|mm|yy|cvv</code> (one per line) "
            "or reply to a message/file with cards.",
            parse_mode=ParseMode.HTML,
        )
        return

    if ACTIVE_MASS.get(user_id):
        await update.message.reply_text(
            "⚠️ You already have a mass Razorpay check running.",
            parse_mode=ParseMode.HTML,
        )
        return

    pair = await _ensure_sites_and_proxies(update, user_id)
    if pair is None:
        return
    sites, proxies = pair

    ACTIVE_MASS[user_id] = True
    stop_event = asyncio.Event()
    ACTIVE_MASS_STOP[user_id] = stop_event
    start_time = time.time()
    try:
        totals = {
            STATUS_CHARGED: 0,
            STATUS_APPROVED: 0,
            STATUS_DECLINED: 0,
            STATUS_ERROR: 0,
        }
        progress = {"checked": 0, "card": "-", "response": "-"}
        progress_lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(RZTXT_CONCURRENCY)
        profile_html = _profile_html(user)

        status_msg = await update.message.reply_text(
            render_mass_progress(
                gate_name="Razorpay",
                total=len(cards),
                checked=0,
                card="-",
                response="-",
                start_time=start_time,
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=stop_keyboard(callback_data=f"stop_mrz:{user_id}"),
        )

        user_data = await get_user(user_id)
        available_credits = int((user_data or {}).get("credits", 0) or 0)
        is_free = is_unlimited(user_id)
        cards_to_check = cards if is_free else cards[:available_credits]
        if not cards_to_check:
            await update.message.reply_text("❌ Out of credits.", parse_mode=ParseMode.HTML)
            return
        if not is_free:
            await consume_credit(user_id, len(cards_to_check))

        pairs = pair_sites_with_proxies(cards_to_check, sites, proxies)

        connector = aiohttp.TCPConnector(limit=RZTXT_CONCURRENCY, limit_per_host=RZTXT_CONCURRENCY)
        timeout = aiohttp.ClientTimeout(total=RZTXT_TIMEOUT)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async def worker(card: str, site: str, proxy: str):
                if stop_event.is_set():
                    return
                async with semaphore:
                    if stop_event.is_set():
                        return
                    start = time.time()
                    api_response = await call_razorpay_api(
                        card, site, proxy, timeout=RZTXT_TIMEOUT, session=session
                    )
                    # Silent retry on "order_id not found" with different site/proxy
                    for _retry in range(MAX_ORDER_RETRIES):
                        if not is_retryable_error(api_response):
                            break
                        site = pick_random(sites)
                        proxy = pick_random(proxies) or ""
                        api_response = await call_razorpay_api(
                            card, site, proxy, timeout=RZTXT_TIMEOUT, session=session
                        )
                    elapsed = time.time() - start

                if is_site_killed_by(api_response):
                    asyncio.create_task(auto_remove_site_if_dead(api_response))

                category, final = await _render_razorpay_card(
                    card=card,
                    user_id=user_id,
                    profile_html=profile_html,
                    api_response=api_response,
                    elapsed=elapsed,
                )
                response_text = api_response.get("Response") or "-"

                async with progress_lock:
                    totals[category] = totals.get(category, 0) + 1
                    progress["checked"] += 1
                    progress["card"] = card
                    progress["response"] = response_text

                if category in (STATUS_CHARGED, STATUS_APPROVED):
                    try:
                        await update.message.reply_text(
                            final,
                            parse_mode=ParseMode.HTML,
                            reply_markup=_result_buttons(),
                            disable_web_page_preview=True,
                        )
                    except Exception as e:
                        logger.warning(f"mrz: failed to send card result: {e}")
                    await _send_hit(
                        context,
                        user,
                        card,
                        STATUS_LABEL.get(category, category),
                        response_text,
                    )

            async def progress_updater():
                last = -1
                while progress["checked"] < len(cards_to_check) and not stop_event.is_set():
                    await asyncio.sleep(2)
                    if progress["checked"] == last:
                        continue
                    last = progress["checked"]
                    try:
                        await status_msg.edit_text(
                            render_mass_progress(
                                gate_name="Razorpay",
                                total=len(cards_to_check),
                                checked=progress["checked"],
                                charged=totals[STATUS_CHARGED],
                                approved=totals[STATUS_APPROVED],
                                declined=totals[STATUS_DECLINED],
                                card=progress["card"],
                                response=progress["response"],
                                start_time=start_time,
                            ),
                            parse_mode=ParseMode.HTML,
                            reply_markup=stop_keyboard(callback_data=f"stop_mrz:{user_id}"),
                        )
                    except Exception:
                        pass

            tasks = [asyncio.create_task(worker(c, s, p)) for c, s, p in pairs]
            updater_task = asyncio.create_task(progress_updater())

            async def stop_watcher():
                await stop_event.wait()
                for t in tasks:
                    if not t.done():
                        t.cancel()

            watcher_task = asyncio.create_task(stop_watcher())
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                updater_task.cancel()
                watcher_task.cancel()

        # Refund credits for any cards that didn't actually run (e.g. user pressed STOP)
        if not is_free:
            unused = max(0, len(cards_to_check) - int(progress.get("checked", 0)))
            if unused > 0:
                try:
                    await add_credits(user_id, unused)
                except Exception:
                    pass

        elapsed_total = time.time() - start_time
        try:
            await status_msg.edit_text(
                render_mass_progress(
                    gate_name="Razorpay",
                    total=len(cards_to_check),
                    checked=progress["checked"],
                    charged=totals[STATUS_CHARGED],
                    approved=totals[STATUS_APPROVED],
                    declined=totals[STATUS_DECLINED],
                    card="-",
                    response="Complete",
                    elapsed=elapsed_total,
                    in_progress=False,
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    finally:
        ACTIVE_MASS.pop(user_id, None)
        ACTIVE_MASS_STOP.pop(user_id, None)


async def stop_mrz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    try:
        target_user_id = int(query.data.split(":", 1)[1])
    except Exception:
        return
    if query.from_user.id != target_user_id and query.from_user.id != OWNER_ID:
        try:
            await query.answer("Only the original user can stop this check.", show_alert=True)
        except Exception:
            pass
        return
    ev = ACTIVE_MASS_STOP.get(target_user_id)
    if ev is not None:
        ev.set()
        try:
            await query.answer("Stopping…", show_alert=False)
        except Exception:
            pass


# =====================================================================
# /rztxt – MASS, CONCURRENT
# =====================================================================
@force_join
async def rztxt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if not await enforce_cooldown(user_id, update):
        return

    raw = ""
    msg = update.message
    if msg.document:
        try:
            file = await context.bot.get_file(msg.document.file_id)
            raw = (await file.download_as_bytearray()).decode("utf-8", "ignore")
        except Exception as e:
            logger.warning(f"rztxt: failed to read document: {e}")
    elif msg.reply_to_message and msg.reply_to_message.document:
        try:
            file = await context.bot.get_file(msg.reply_to_message.document.file_id)
            raw = (await file.download_as_bytearray()).decode("utf-8", "ignore")
        except Exception as e:
            logger.warning(f"rztxt: failed to read replied document: {e}")
    elif msg.reply_to_message and msg.reply_to_message.text:
        raw = msg.reply_to_message.text
    elif context.args:
        raw = " ".join(context.args)

    cards = extract_cards_from_text(raw)
    if not cards:
        await update.message.reply_text(
            "<b>Usage:</b> Reply to a .txt file with /rztxt or paste cards in arguments.",
            parse_mode=ParseMode.HTML,
        )
        return

    if ACTIVE_MASS.get(user_id):
        await update.message.reply_text(
            "⚠️ You already have a mass Razorpay check running.",
            parse_mode=ParseMode.HTML,
        )
        return

    pair = await _ensure_sites_and_proxies(update, user_id)
    if pair is None:
        return
    sites, proxies = pair

    ACTIVE_MASS[user_id] = True
    stop_event = asyncio.Event()
    ACTIVE_MASS_STOP[user_id] = stop_event
    try:
        status_msg = await update.message.reply_text(
            f"🚀 Starting concurrent Razorpay check for <b>{len(cards)}</b> "
            f"card(s) (up to <b>{RZTXT_CONCURRENCY}</b> in parallel)…",
            parse_mode=ParseMode.HTML,
            reply_markup=stop_keyboard(callback_data=f"stop_mrz:{user_id}"),
        )

        totals = {
            STATUS_CHARGED: 0,
            STATUS_APPROVED: 0,
            STATUS_DECLINED: 0,
            STATUS_ERROR: 0,
        }
        progress = {"checked": 0}
        progress_lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(RZTXT_CONCURRENCY)
        profile_html = _profile_html(user)

        user_data = await get_user(user_id)
        available_credits = int((user_data or {}).get("credits", 0) or 0)
        is_free = is_unlimited(user_id)
        cards_to_check = cards if is_free else cards[:available_credits]
        if not cards_to_check:
            await update.message.reply_text("❌ Out of credits.", parse_mode=ParseMode.HTML)
            return
        if not is_free:
            await consume_credit(user_id, len(cards_to_check))

        pairs = pair_sites_with_proxies(cards_to_check, sites, proxies)

        connector = aiohttp.TCPConnector(limit=RZTXT_CONCURRENCY, limit_per_host=RZTXT_CONCURRENCY)
        timeout = aiohttp.ClientTimeout(total=RZTXT_TIMEOUT)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async def worker(card: str, site: str, proxy: str):
                async with semaphore:
                    start = time.time()
                    api_response = await call_razorpay_api(
                        card, site, proxy, timeout=RZTXT_TIMEOUT, session=session
                    )
                    # Silent retry on "order_id not found" with different site/proxy
                    for _retry in range(MAX_ORDER_RETRIES):
                        if not is_retryable_error(api_response):
                            break
                        site = pick_random(sites)
                        proxy = pick_random(proxies) or ""
                        api_response = await call_razorpay_api(
                            card, site, proxy, timeout=RZTXT_TIMEOUT, session=session
                        )
                    elapsed = time.time() - start

                if is_site_killed_by(api_response):
                    asyncio.create_task(auto_remove_site_if_dead(api_response))

                category, final = await _render_razorpay_card(
                    card=card,
                    user_id=user_id,
                    profile_html=profile_html,
                    api_response=api_response,
                    elapsed=elapsed,
                )

                async with progress_lock:
                    totals[category] = totals.get(category, 0) + 1
                    progress["checked"] += 1

                if category in (STATUS_CHARGED, STATUS_APPROVED):
                    try:
                        await update.message.reply_text(
                            final,
                            parse_mode=ParseMode.HTML,
                            reply_markup=_result_buttons(),
                            disable_web_page_preview=True,
                        )
                    except Exception as e:
                        logger.warning(f"rztxt: failed to send hit: {e}")

            async def progress_updater():
                last = -1
                while progress["checked"] < len(cards_to_check):
                    await asyncio.sleep(4)
                    if progress["checked"] == last:
                        continue
                    last = progress["checked"]
                    try:
                        await status_msg.edit_text(
                            f"🚀 <b>Razorpay Mass Check</b>\n"
                            f"Progress: <b>{progress['checked']}/{len(cards_to_check)}</b>\n"
                            f"💎 Charged: {totals[STATUS_CHARGED]}\n"
                            f"✅ Approved: {totals[STATUS_APPROVED]}\n"
                            f"❌ Declined: {totals[STATUS_DECLINED]}\n"
                            f"⚠️ Errors: {totals[STATUS_ERROR]}",
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        pass

            tasks = [asyncio.create_task(worker(c, s, p)) for c, s, p in pairs]
            updater_task = asyncio.create_task(progress_updater())

            async def stop_watcher():
                await stop_event.wait()
                for t in tasks:
                    if not t.done():
                        t.cancel()

            watcher_task = asyncio.create_task(stop_watcher())
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                updater_task.cancel()
                watcher_task.cancel()

        # Refund credits for cards that didn't actually run
        if not is_free:
            unused = max(0, len(cards_to_check) - int(progress.get("checked", 0)))
            if unused > 0:
                try:
                    await add_credits(user_id, unused)
                except Exception:
                    pass

        try:
            await status_msg.edit_text(
                f"✅ <b>Razorpay Mass Check Complete</b>\n"
                f"Total: <b>{len(cards_to_check)}</b>\n"
                f"💎 Charged: {totals[STATUS_CHARGED]}\n"
                f"✅ Approved: {totals[STATUS_APPROVED]}\n"
                f"❌ Declined: {totals[STATUS_DECLINED]}\n"
                f"⚠️ Errors: {totals[STATUS_ERROR]}",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    finally:
        ACTIVE_MASS.pop(user_id, None)
        ACTIVE_MASS_STOP.pop(user_id, None)


# =====================================================================
# REGISTER
# =====================================================================
def register_rz_handlers(application):
    """Register the plans_info + mrz-stop callbacks used by the Razorpay
    result keyboard.

    The /rz, /mrz and /rztxt commands themselves are wired up by main.py
    through ``add_dual_command``.
    """
    application.add_handler(
        CallbackQueryHandler(plans_info_callback, pattern=r"^plans_info$")
    )
    application.add_handler(
        CallbackQueryHandler(stop_mrz_callback, pattern=r"^stop_mrz:")
    )
    logger.info(
        "✅ Razorpay charge commands ready (plans_info + stop_mrz callbacks registered)"
    )
