"""
utils/cards_ui.py

Shared per-card UI in the **PayPal-style** layout used across all gates
(Razorpay, Shopify, etc).

Result block:

    [💎] Card ➜ <code>4031...|07|30|259</code>
    ━━━━━━━━━━━
    [ﾒ] Status   ➜ Declined ❌
    [ﾒ] Response ➜ ORDER_NOT_APPROVED
    [ﾒ] Gateway  ➜ Razorpay 1₹
    ━━━━━━━━━━━
    [ﾒ] Info    ➜ VISA - PREPAID - CLASSIC
    [ﾒ] Bank    ➜ SUTTON BANK
    [ﾒ] Country ➜ UNITED STATES 🇺🇸
    ━━━━━━━━━━━
    [💎] Checked By ➜ {user} [{plan}]
    [💎] Dev        ➜ {dev}
    ━━━━━━━━━━━
    [ﾒ] Tᴏᴏᴋ : 3.42s

Plus a coloured ``Support`` / ``Channel`` inline keyboard.
"""

from __future__ import annotations

import html
from typing import Any, Dict, Optional

from telegram import InlineKeyboardMarkup

from bin import get_bin_info
from config import (
    DEVELOPER_LINK,
    DEVELOPER_NAME,
    OFFICIAL_CHANNEL_LINK,
    OFFICIAL_CHANNEL_USERNAME,
)
from utils.styled_buttons import styled_button


# Status buckets (kept for backward compatibility with existing callers)
CHARGED = "CHARGED"
APPROVED = "APPROVED"
DECLINED = "DECLINED"
ERROR = "ERROR"


# Premium emoji ids for the Support / Channel buttons.
SUPPORT_ICON_ID = "6129705083501293112"
CHANNEL_ICON_ID = "6154386220441933028"

# Premium emoji ids used in the result block markers.
EMOJI_DIAMOND_BLUE = "5125437164422694571"
EMOJI_DIAMOND_PINK = "5134452506935427991"
EMOJI_DIAMOND_GREEN = "5852557780262592341"


def escape(text: Any) -> str:
    if text is None:
        return ""
    return html.escape(str(text), quote=False)


def short(text: Any, n: int = 120) -> str:
    if text is None:
        return ""
    text = str(text)
    return text if len(text) <= n else text[: n - 3] + "..."


EMOJI_CHARGED_ID = "5041796412954641308"
EMOJI_APPROVED_ID = "5125343104638912114"
EMOJI_DECLINED_ID = "5855085385696156087"


def status_text(status: str) -> str:
    s = (status or "").upper()
    if s == CHARGED:
        return f'𝑪𝒉𝒂𝒓𝒈𝒆𝒅 <tg-emoji emoji-id="{EMOJI_CHARGED_ID}">💎</tg-emoji>'
    if s == APPROVED:
        return f'𝑨𝒑𝒑𝒓𝒐𝒗𝒆𝒅 <tg-emoji emoji-id="{EMOJI_APPROVED_ID}">✅</tg-emoji>'
    if s == DECLINED:
        return f'𝑫𝒆𝒄𝒍𝒊𝒏𝒆𝒅 <tg-emoji emoji-id="{EMOJI_DECLINED_ID}">❌</tg-emoji>'
    return '𝙀𝙧𝙧𝙤𝙧 ⚠️'


# Backward compat alias used by some legacy callers.
def status_header(status: str) -> str:
    return status_text(status)


def format_price(price: Any) -> str:
    if price in (None, "", "-"):
        return "-"
    s = str(price).strip()
    if s.startswith("$") or s.endswith("₹") or s.endswith("$") or s.endswith("£"):
        return s
    try:
        return f"${float(s):.2f}"
    except (TypeError, ValueError):
        return s


def _channel_url() -> str:
    if OFFICIAL_CHANNEL_USERNAME:
        return f"https://t.me/{OFFICIAL_CHANNEL_USERNAME}"
    return OFFICIAL_CHANNEL_LINK or "https://t.me/"


def result_buttons() -> InlineKeyboardMarkup:
    """Coloured Support / Channel inline keyboard shown under every card."""
    return InlineKeyboardMarkup(
        [
            [
                styled_button(
                    "Support",
                    url=DEVELOPER_LINK,
                    color="blue",
                    icon=SUPPORT_ICON_ID,
                ),
                styled_button(
                    "Channel",
                    url=_channel_url(),
                    color="blue",
                    icon=CHANNEL_ICON_ID,
                ),
            ]
        ]
    )


def processing_text(card: str, gateway: str) -> str:
    """The PayPal-style 'Processing ...' loading message."""
    return (
        f'<tg-emoji emoji-id="5195033767969839232">⏳</tg-emoji> '
        f'𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜 {escape(gateway)}...\n'
        f'<code>{escape(card)}</code>'
    )


async def _bin_block(card: str) -> Dict[str, str]:
    bin6 = card.split("|", 1)[0][:6]
    try:
        info = await get_bin_info(bin6) or {}
    except Exception:
        info = {}
    return {
        "brand": (info.get("scheme") or "N/A").upper(),
        "type": (info.get("type") or "N/A").upper(),
        "level": (info.get("brand") or "N/A").upper(),
        "bank": info.get("bank") or "N/A",
        "country": info.get("country") or "Unknown",
        "flag": info.get("country_emoji") or "",
    }


def _user_mention_html(user) -> str:
    if user is None:
        return "Fr"
    name = getattr(user, "first_name", None) or "User"
    if getattr(user, "last_name", None):
        name += f" {user.last_name}"
    return f'<a href="tg://user?id={user.id}">{escape(name)}</a>'


def _developer_html() -> str:
    return f'<a href="{DEVELOPER_LINK}">{DEVELOPER_NAME}</a>'


async def format_card_result(
    *,
    card: str,
    gateway: str,
    response: str,
    status: str,
    price: Any = "-",                # kept for backward compat (not displayed)
    elapsed: Optional[float] = None,
    user=None,
    user_mention_html: Optional[str] = None,
    plan_label: str = "",
    extra_top_lines: Optional[Dict[str, str]] = None,
    progress_footer: Optional[str] = None,
) -> str:
    """Build the PayPal-style per-card result message."""
    bin_info = await _bin_block(card)

    if user_mention_html is None:
        user_mention_html = _user_mention_html(user)

    plan_str = ""
    if plan_label:
        plan_str = f" [<code>{escape(plan_label)}</code>]"

    extras = ""
    if extra_top_lines:
        for label, value in extra_top_lines.items():
            extras += f"[ﾒ] <b><i>{escape(label)}</i></b> ➜ <b><i>{escape(value)}</i></b>\n"

    elapsed_line = ""
    if elapsed is not None:
        elapsed_line = (
            f"\n━━━━━━━━━━━\n"
            f"[ﾒ] <b><i>Tᴏᴏᴋ</i></b> : <code>{elapsed:.2f}s</code>"
        )

    progress_line = ""
    if progress_footer:
        progress_line = f"\n{progress_footer}"

    return (
        f'[<tg-emoji emoji-id="{EMOJI_DIAMOND_BLUE}">💎</tg-emoji>] '
        f'<b><i>Card</i></b> ➜ <code>{escape(card)}</code>\n'
        f'━━━━━━━━━━━\n'
        f'[ﾒ] <b><i>Status</i></b> ➜ {status_text(status)}\n'
        f'[ﾒ] <b><i>Response</i></b> ➜ <b><i>{escape(short(response))}</i></b>\n'
        f'[ﾒ] <b><i>Gateway</i></b> ➜ <b><i>{escape(gateway)}</i></b>\n'
        f'━━━━━━━━━━━\n'
        f'{extras}'
        f'[ﾒ] <b><i>Info</i></b> ➜ <b><i>'
        f'{escape(bin_info["brand"])} - {escape(bin_info["type"])} - {escape(bin_info["level"])}</i></b>\n'
        f'[ﾒ] <b><i>Bank</i></b> ➜ <b><i>{escape(bin_info["bank"])}</i></b>\n'
        f'[ﾒ] <b><i>Country</i></b> ➜ <b><i>{escape(bin_info["country"])} {bin_info["flag"]}</i></b>\n'
        f'━━━━━━━━━━━\n'
        f'[<tg-emoji emoji-id="{EMOJI_DIAMOND_PINK}">💎</tg-emoji>] '
        f'<b><i>Checked By</i></b> ➜ {user_mention_html}{plan_str}\n'
        f'[<tg-emoji emoji-id="{EMOJI_DIAMOND_GREEN}">💎</tg-emoji>] '
        f'<b><i>Dev</i></b> ➜ {_developer_html()}'
        f'{elapsed_line}'
        f'{progress_line}'
    )


# Backward compat alias for old code that imported build_bin_block.
async def build_bin_block(card: str) -> str:
    info = await _bin_block(card)
    return (
        f"𝗕𝗜𝗡 𝗜𝗻𝗳𝗼: {escape(info['brand'])} - {escape(info['type'])} - {escape(info['level'])}\n"
        f"𝗕𝗮𝗻𝗸: {escape(info['bank'])}\n"
        f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {escape(info['country'])} {info['flag']}"
    )
