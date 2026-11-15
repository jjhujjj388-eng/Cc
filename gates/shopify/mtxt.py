"""
gates/shopify/mtxt.py

Concurrent Shopify TXT mass-checker (``/mtxt``).

Behaviour
---------
* Reads cards from a .txt file (uploaded or replied) or from message text.
* Runs up to 20 cards concurrently — every card uses a different random
  site + proxy combo so checks don't pile up on the same site.
* Posts a per-card hit message for charged/approved results.
* Maintains a single status message with running totals.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

from db import get_user, update_user
from force_join import force_join
from utils.cards_ui import (
    APPROVED as UI_APPROVED,
    CHARGED as UI_CHARGED,
    DECLINED as UI_DECLINED,
    ERROR as UI_ERROR,
    format_card_result,
    result_buttons as _ui_result_buttons,
)
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
    pair_sites_with_proxies,
    remove_user_site,
)


logger = logging.getLogger(__name__)


MTXT_CONCURRENCY = 20


_active_users: Dict[int, bool] = {}

_UI_BUCKET = {
    STATUS_CHARGED: UI_CHARGED,
    STATUS_APPROVED: UI_APPROVED,
    STATUS_DECLINED: UI_DECLINED,
    STATUS_ERROR: UI_ERROR,
}


@force_join
async def mtxt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    raw = ""
    msg = update.message
    if msg.document:
        try:
            file = await context.bot.get_file(msg.document.file_id)
            raw = (await file.download_as_bytearray()).decode("utf-8", "ignore")
        except Exception as e:
            logger.warning(f"mtxt: failed to read document: {e}")
    elif msg.reply_to_message and msg.reply_to_message.document:
        try:
            file = await context.bot.get_file(msg.reply_to_message.document.file_id)
            raw = (await file.download_as_bytearray()).decode("utf-8", "ignore")
        except Exception as e:
            logger.warning(f"mtxt: failed to read replied document: {e}")
    elif msg.reply_to_message and msg.reply_to_message.text:
        raw = msg.reply_to_message.text
    elif context.args:
        raw = " ".join(context.args)

    cards = extract_cards_from_text(raw)
    if not cards:
        await update.message.reply_text(
            "<b>Usage:</b> Reply to a .txt file with <code>/mtxt</code> or paste cards in arguments.",
            parse_mode=ParseMode.HTML,
        )
        return

    if _active_users.get(user_id):
        await update.message.reply_text(
            "⚠️ You already have an active /mtxt running.",
            parse_mode=ParseMode.HTML,
        )
        return

    sites = await get_user_sites(user_id)
    if not sites:
        await update.message.reply_text(
            "📭 <b>No Shopify sites added.</b>\nAdd sites with <code>/add</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    proxies = await get_proxies_for_user(user_id)
    if not proxies:
        await update.message.reply_text(
            "❌ <b>No proxies configured.</b>\nAdd some with <code>/addpxy</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    user_data = await get_user(user_id)
    if not user_data or user_data.get("credits", 0) <= 0:
        await update.message.reply_text(
            "❌ Out of credits.", parse_mode=ParseMode.HTML
        )
        return

    _active_users[user_id] = True
    try:
        stats = {
            "checked": 0,
            STATUS_CHARGED: 0,
            STATUS_APPROVED: 0,
            STATUS_DECLINED: 0,
            STATUS_ERROR: 0,
        }
        total = len(cards)
        start_time = time.time()

        status_msg = await update.message.reply_text(
            f"<b>🚀 Mass TXT check started</b>\nCards: <b>{total}</b> • "
            f"Concurrency: <b>{MTXT_CONCURRENCY}</b>",
            parse_mode=ParseMode.HTML,
        )

        semaphore = asyncio.Semaphore(MTXT_CONCURRENCY)
        progress_lock = asyncio.Lock()
        pairs = pair_sites_with_proxies(cards, sites, proxies)

        async def worker(card: str, site: str, proxy: str):
            async with semaphore:
                user_data = await get_user(user_id)
                if not user_data or user_data.get("credits", 0) <= 0:
                    return
                await update_user(user_id, credits=user_data["credits"] - 1)

                api_response = await call_shopify_api(card, site, proxy)
                if is_site_killed_by(api_response):
                    await remove_user_site(user_id, site)

                category = classify_response(api_response)

                async with progress_lock:
                    stats[category] = stats.get(category, 0) + 1
                    stats["checked"] += 1

                if category in (STATUS_CHARGED, STATUS_APPROVED):
                    plan, badge = await user_plan_label(user_id)
                    plan_label = f"{plan} {badge}".strip()
                    text = await format_card_result(
                        card=card,
                        gateway=format_gateway_with_price(api_response.get("Gateway", "Shopify Payments"), api_response.get("Price")),
                        response=api_response.get("Response", ""),
                        price=api_response.get("Price", "-"),
                        status=_UI_BUCKET.get(category, UI_ERROR),
                        user=update.effective_user,
                        plan_label=plan_label,
                    )
                    try:
                        await update.message.reply_text(
                            text,
                            parse_mode=ParseMode.HTML,
                            reply_markup=_ui_result_buttons(),
                            disable_web_page_preview=True,
                        )
                    except Exception as e:
                        logger.warning(f"mtxt: failed sending hit: {e}")

        async def progress_updater():
            last = -1
            while stats["checked"] < total:
                await asyncio.sleep(4)
                if stats["checked"] == last:
                    continue
                last = stats["checked"]
                try:
                    await status_msg.edit_text(
                        f"<b>🚀 Mass TXT check</b>\n"
                        f"Progress: <b>{stats['checked']}/{total}</b>\n"
                        f"🟢 Charged: {stats[STATUS_CHARGED]}\n"
                        f"🔵 Approved: {stats[STATUS_APPROVED]}\n"
                        f"🔴 Declined: {stats[STATUS_DECLINED]}\n"
                        f"⚪ Errors: {stats[STATUS_ERROR]}",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass

        updater_task = asyncio.create_task(progress_updater())
        try:
            await asyncio.gather(
                *[asyncio.create_task(worker(c, s, p)) for c, s, p in pairs],
                return_exceptions=True,
            )
        finally:
            updater_task.cancel()

        elapsed = time.time() - start_time
        try:
            await status_msg.edit_text(
                f"<b>✅ Mass TXT check complete</b>\n"
                f"Total: <b>{total}</b>\n"
                f"🟢 Charged: {stats[STATUS_CHARGED]}\n"
                f"🔵 Approved: {stats[STATUS_APPROVED]}\n"
                f"🔴 Declined: {stats[STATUS_DECLINED]}\n"
                f"⚪ Errors: {stats[STATUS_ERROR]}\n"
                f"⏱ Elapsed: {elapsed:.1f}s",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
    finally:
        _active_users.pop(user_id, None)


def register_mtxt_handlers(application):
    """No-op for compatibility — /mtxt is registered via main.py's add_dual_command."""
    logger.info("✅ Shopify /mtxt command ready (registered via main)")
