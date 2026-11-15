"""
gates/razorpay/sites.py

Owner-only Razorpay site pool management.

Commands
--------
* ``/addrz <url1> <url2> ...`` — Test each provided Razorpay link with the
  default test card and the owner's proxies. Sites that respond cleanly
  are saved. Sites whose response says "International cards are not
  supported …" are auto-removed (and never saved).
* ``/rzsite``                  — List all saved Razorpay sites.
* ``/rmrz <url>``              — Remove a single saved site.
* ``/rmrzall``                 — Wipe all saved sites.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from config import OWNER_ID, ADMIN_IDS
from db import (
    add_razorpay_site,
    get_all_razorpay_sites,
    remove_all_razorpay_sites,
    remove_razorpay_site,
)

from .common import (
    DEFAULT_TEST_CARD,
    auto_remove_site_if_dead,
    call_razorpay_api,
    classify_response,
    get_proxies_for_user,
    is_site_killed_by,
    pick_random,
    status_emoji,
    STATUS_ERROR,
)


logger = logging.getLogger(__name__)


# In-flight test results — keyed by chat id, used by the "Save" button below.
PENDING_ADDRZ: dict[int, dict] = {}


def _is_owner_or_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMIN_IDS


def _extract_urls(args: List[str]) -> List[str]:
    """Pull razorpay-style URLs out of the raw arguments."""
    urls: List[str] = []
    raw_text = " ".join(args)
    pattern = re.compile(r"https?://[^\s]+", re.IGNORECASE)

    for match in pattern.findall(raw_text):
        url = match.strip().rstrip(",;.")
        if url and url not in urls:
            urls.append(url)

    if not urls:
        for token in args:
            token = token.strip().rstrip(",;.")
            if not token:
                continue
            if token.startswith("razorpay.me") or "razorpay.com" in token or "rzp.io" in token:
                token = "https://" + token
            if token.startswith(("http://", "https://")):
                if token not in urls:
                    urls.append(token)
    return urls


def _short(text: str, n: int = 80) -> str:
    if not text:
        return ""
    return text if len(text) <= n else text[: n - 3] + "..."


# =====================================================================
# /addrz
# =====================================================================
async def addrz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _is_owner_or_admin(user.id):
        await update.message.reply_text(
            "🚫 <b>Owner only</b>", parse_mode=ParseMode.HTML
        )
        return

    urls: List[str] = []
    if context.args:
        urls = _extract_urls(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        urls = _extract_urls(update.message.reply_to_message.text.split())

    if not urls:
        await update.message.reply_text(
            "<b>Usage:</b> <code>/addrz https://razorpay.me/@a https://razorpay.me/@b ...</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    proxies = await get_proxies_for_user(user.id)
    proxy = pick_random(proxies) or ""

    chat_id = update.effective_chat.id
    PENDING_ADDRZ.pop(chat_id, None)
    PENDING_ADDRZ[chat_id] = {
        "user_id": user.id,
        "results": [],
        "alive": [],
    }

    status_msg = await update.message.reply_text(
        f"🔍 Testing <b>{len(urls)}</b> Razorpay site(s) with the default card...",
        parse_mode=ParseMode.HTML,
    )

    asyncio.create_task(
        _process_addrz(update, context, status_msg, urls, proxy, chat_id)
    )


async def _process_addrz(update, context, status_msg, urls, proxy, chat_id):
    lines: List[str] = []
    alive_sites: List[str] = []

    for idx, site in enumerate(urls, 1):
        api_response = await call_razorpay_api(
            DEFAULT_TEST_CARD, site=site, proxy=proxy, amount="1", timeout=60
        )
        category = classify_response(api_response)
        response_text = api_response.get("Response") or ""
        code = api_response.get("Code") or "N/A"

        if is_site_killed_by(api_response):
            await auto_remove_site_if_dead(api_response)
            lines.append(
                f"⛔️ <b>{html.escape(site)}</b> — auto-removed "
                f"(<i>{html.escape(_short(response_text))}</i>)"
            )
        else:
            emoji = status_emoji(category) if category != STATUS_ERROR else "⚠️"
            lines.append(
                f"{emoji} <b>{html.escape(site)}</b> — "
                f"<code>{html.escape(_short(response_text))}</code> "
                f"[{html.escape(str(code))}]"
            )
            if category != STATUS_ERROR:
                alive_sites.append(site)

        if idx % 4 == 0 or idx == len(urls):
            try:
                await status_msg.edit_text(
                    "🔍 <b>Razorpay site test</b>\n\n" + "\n".join(lines),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            except Exception:
                pass

    state = PENDING_ADDRZ.get(chat_id)
    if state is not None:
        state["results"] = lines
        state["alive"] = alive_sites

    buttons = []
    if alive_sites:
        buttons.append(
            [
                InlineKeyboardButton(
                    f"✅ Save {len(alive_sites)} live site(s)",
                    callback_data=f"addrz_save:{chat_id}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton("❌ Discard", callback_data=f"addrz_cancel:{chat_id}")]
    )

    try:
        await status_msg.edit_text(
            "🔍 <b>Razorpay site test complete</b>\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception as e:
        logger.warning(f"addrz: failed final edit: {e}")


async def addrz_save_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    try:
        chat_id = int(query.data.split(":", 1)[1])
    except Exception as e:
        logger.warning(f"addrz_save: bad callback_data {query.data!r}: {e}")
        return

    state = PENDING_ADDRZ.get(chat_id)
    if not state:
        try:
            await query.edit_message_text("❌ Test results expired. Run /addrz again.")
        except Exception:
            pass
        return

    if query.from_user.id != state["user_id"]:
        try:
            await query.answer(
                "Only the owner who started this test can save.",
                show_alert=True,
            )
        except Exception:
            pass
        return

    alive_sites = list(state.get("alive") or [])
    logger.info(f"addrz_save: attempting to save {len(alive_sites)} site(s): {alive_sites}")

    saved = 0
    duplicates = 0
    errors = 0
    error_details: List[str] = []
    saved_sites: List[str] = []

    for site in alive_sites:
        try:
            added = await add_razorpay_site(site)
        except Exception as e:
            errors += 1
            error_details.append(f"{site} -> {e}")
            logger.exception(f"addrz_save: add_razorpay_site({site!r}) raised")
            continue
        if added is True:
            saved += 1
            saved_sites.append(site)
        elif added is False:
            duplicates += 1
        else:
            errors += 1
            error_details.append(f"{site} -> add_razorpay_site returned {added!r}")
            logger.warning(f"addrz_save: unexpected return {added!r} for {site!r}")

    PENDING_ADDRZ.pop(chat_id, None)

    # Build the result panel so the owner can see exactly what happened.
    parts = [
        f"<b>📥 Razorpay site save</b>",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"✅ Newly saved : <b>{saved}</b>",
        f"⚠️ Duplicates : <b>{duplicates}</b>",
    ]
    if errors:
        parts.append(f"❌ Errors : <b>{errors}</b>")
    if saved_sites:
        parts.append("")
        parts.append("<b>Saved:</b>")
        for s in saved_sites[:10]:
            parts.append(f"• <code>{html.escape(s)}</code>")
        if len(saved_sites) > 10:
            parts.append(f"… +{len(saved_sites) - 10} more")
    if error_details:
        parts.append("")
        parts.append("<b>Errors:</b>")
        for e in error_details[:5]:
            parts.append(f"• <code>{html.escape(_short(e, 100))}</code>")
    parts.append("")
    parts.append("Use <code>/rzsite</code> to view the full list.")

    try:
        await query.edit_message_text(
            "\n".join(parts),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"addrz_save: failed final edit: {e}")


async def addrz_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        chat_id = int(query.data.split(":", 1)[1])
    except Exception:
        return

    state = PENDING_ADDRZ.get(chat_id)
    if state and query.from_user.id != state["user_id"]:
        await query.answer("Only the owner who started this test can cancel.", show_alert=True)
        return

    PENDING_ADDRZ.pop(chat_id, None)
    try:
        await query.edit_message_text("🗑️ Discarded test results.")
    except Exception:
        pass


# =====================================================================
# /rzsite
# =====================================================================
async def rzsite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _is_owner_or_admin(user.id):
        await update.message.reply_text(
            "🚫 <b>Owner only</b>", parse_mode=ParseMode.HTML
        )
        return
    sites = await get_all_razorpay_sites()
    if not sites:
        await update.message.reply_text(
            "📭 <b>No Razorpay sites saved.</b>\nOwner can add some with <code>/addrz</code>.",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = [f"<b>📋 Razorpay Sites ({len(sites)})</b>", ""]
    for idx, site in enumerate(sites, 1):
        lines.append(f"{idx}. <code>{html.escape(site)}</code>")

    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3800] + "\n\n…(truncated)"

    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


# =====================================================================
# /rmrz
# =====================================================================
async def rmrz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _is_owner_or_admin(user.id):
        await update.message.reply_text(
            "🚫 <b>Owner only</b>", parse_mode=ParseMode.HTML
        )
        return

    if not context.args:
        await update.message.reply_text(
            "<b>Usage:</b> <code>/rmrz https://razorpay.me/@example</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    urls = _extract_urls(context.args)
    if not urls:
        await update.message.reply_text(
            "❌ No valid URL detected.", parse_mode=ParseMode.HTML
        )
        return

    removed = 0
    not_found = 0
    for url in urls:
        if await remove_razorpay_site(url):
            removed += 1
        else:
            not_found += 1

    await update.message.reply_text(
        f"🗑️ Removed: <b>{removed}</b>\nNot found: <b>{not_found}</b>",
        parse_mode=ParseMode.HTML,
    )


# =====================================================================
# /rmrzall
# =====================================================================
async def rmrzall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _is_owner_or_admin(user.id):
        await update.message.reply_text(
            "🚫 <b>Owner only</b>", parse_mode=ParseMode.HTML
        )
        return

    count = await remove_all_razorpay_sites()
    await update.message.reply_text(
        f"🧹 Removed <b>{count}</b> Razorpay site(s).",
        parse_mode=ParseMode.HTML,
    )


# =====================================================================
# REGISTER
# =====================================================================
def register_razorpay_site_handlers(application):
    """Register only the inline-button callbacks for the site flow.

    The slash/dot commands are wired up by ``main.py`` via ``add_dual_command``
    to avoid double-handler registration.
    """
    application.add_handler(
        CallbackQueryHandler(addrz_save_callback, pattern=r"^addrz_save:")
    )
    application.add_handler(
        CallbackQueryHandler(addrz_cancel_callback, pattern=r"^addrz_cancel:")
    )
    logger.info(
        "✅ Razorpay site callbacks registered (commands wired separately)"
    )
