"""admin/get_user_cmd.py — /get_user command (owner only).

Lists every premium user with a clickable Telegram name link, ID, plan,
credits and plan-expiry. Paginated with blue Next / Back buttons.
"""

from __future__ import annotations

import html
import logging
from typing import Any, Dict, List

from telegram import Update, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from config import OWNER_ID, ADMIN_IDS
from db import get_all_users, get_user
from utils.styled_buttons import styled_button


logger = logging.getLogger(__name__)

PAGE_SIZE = 8
FREE_PLAN_NAMES = {"free", "n/a", "none", ""}


def _is_premium_doc(doc: Dict[str, Any]) -> bool:
    plan = str(doc.get("plan", "Free") or "Free").strip().lower()
    return plan not in FREE_PLAN_NAMES


async def _collect_premium_users() -> List[Dict[str, Any]]:
    users = await get_all_users()
    out: List[Dict[str, Any]] = []
    for u in users:
        uid = u.get("id")
        if uid is None:
            continue
        try:
            uid_int = int(uid)
        except Exception:
            continue
        if uid_int == OWNER_ID or uid_int in ADMIN_IDS:
            continue
        if not _is_premium_doc(u):
            continue
        full = await get_user(uid_int) or u
        out.append({
            "id": uid_int,
            "plan": full.get("plan", "Free"),
            "credits": full.get("credits", 0),
            "plan_expiry": full.get("plan_expiry", "N/A"),
        })
    out.sort(key=lambda x: x["id"], reverse=True)
    return out


async def _resolve_name(bot, uid: int) -> str:
    """Fetch the user's Telegram display name. Falls back to 'User <id>'."""
    try:
        chat = await bot.get_chat(uid)
        first = (getattr(chat, "first_name", "") or "").strip()
        last = (getattr(chat, "last_name", "") or "").strip()
        uname = (getattr(chat, "username", "") or "").strip()
        full = (f"{first} {last}").strip()
        if full:
            return full
        if uname:
            return f"@{uname}"
    except Exception as e:
        logger.debug(f"get_chat({uid}) failed: {e}")
    return f"User {uid}"


async def _build_text(bot, users: List[Dict[str, Any]], page: int, total_pages: int) -> str:
    if not users:
        return (
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "💎 <b><i>Premium Users</i></b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>No premium users found.</i>"
        )
    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"💎 <b><i>Premium Users</i></b> [{page + 1}/{max(total_pages, 1)}]",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    start = page * PAGE_SIZE
    chunk = users[start:start + PAGE_SIZE]
    for idx, u in enumerate(chunk, start=start + 1):
        uid = u["id"]
        plan = html.escape(str(u.get("plan", "Free")))
        credits = u.get("credits", 0)
        expiry = html.escape(str(u.get("plan_expiry", "N/A")))
        name = html.escape(await _resolve_name(bot, uid))
        mention = f'<a href="tg://user?id={uid}">{name}</a>'
        lines.append(f"<b>{idx}.</b> {mention}")
        lines.append(f"   <i>ID:</i> <code>{uid}</code>")
        lines.append(f"   <i>Plan:</i> <b>{plan}</b>")
        lines.append(f"   <i>Credits:</i> <b>{credits}</b>")
        lines.append(f"   <i>Expires:</i> <i>{expiry}</i>")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


def _build_buttons(page: int, total_pages: int) -> InlineKeyboardMarkup:
    row = []
    if page > 0:
        row.append(styled_button("⬅️ Back", callback_data=f"getuser_page_{page - 1}", color="blue"))
    row.append(styled_button(f"[{page + 1}/{max(total_pages, 1)}]", callback_data="noop", color="blue"))
    if page < total_pages - 1:
        row.append(styled_button("➡️ Next", callback_data=f"getuser_page_{page + 1}", color="blue"))
    return InlineKeyboardMarkup([row])


async def get_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.effective_message.reply_text("🚫 Owner only.")
        return
    users = await _collect_premium_users()
    total_pages = max(1, (len(users) + PAGE_SIZE - 1) // PAGE_SIZE)
    text = await _build_text(context.bot, users, 0, total_pages)
    buttons = _build_buttons(0, total_pages) if users else None
    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=buttons,
    )


async def get_user_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != OWNER_ID:
        return
    data = query.data or ""
    try:
        page = int(data.rsplit("_", 1)[1])
    except Exception:
        return
    users = await _collect_premium_users()
    total_pages = max(1, (len(users) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    text = await _build_text(context.bot, users, page, total_pages)
    buttons = _build_buttons(page, total_pages) if users else None
    try:
        await query.message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            reply_markup=buttons,
        )
    except Exception as e:
        logger.warning(f"get_user pagination edit failed: {e}")


def register_get_user_handler(application) -> None:
    application.add_handler(
        CallbackQueryHandler(get_user_pagination, pattern=r"^getuser_page_\d+$")
    )
