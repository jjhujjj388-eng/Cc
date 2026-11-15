"""utils/mass_progress.py

Shared progress-UI builder for every mass-check command (``/msh``, ``/mrz``,
``/masspp`` …). Every gate renders the same Tools-style progress card with
premium custom-emoji icons.

The premium emoji ids below were supplied by the bot owner — they map to the
green/blue/red/yellow Telegram Premium emojis that should sit before each
label on the progress card:

    Mass Check Progress  → ⚡  emoji 5348235470461483629
    Progress             → 🕯  emoji 5980995951160987855
    Charged              → 🔥  emoji 5116414868357907335
    Approved             → 💎  emoji 5316827280863934685
    Declined             → ❌  emoji 5316660455744223443
    Gate Name            → ⭐  emoji 5267500801240092311
    Card                 → 💎  emoji 5348296214183950233
    Response (label)     → ⚡  emoji 5348235470461483629
    Response (spinner)   → ⏳  emoji 5215327832040811010
    Took                 → ⏰  emoji 5776213190387961618
"""

from __future__ import annotations

import html
import time
from typing import Optional

from telegram import InlineKeyboardMarkup

from utils.styled_buttons import styled_button


HEADER_EMOJI = "5348235470461483629"   # ⚡
PROGRESS_EMOJI = "5980995951160987855"  # 🕯
CHARGED_EMOJI = "5116414868357907335"   # 🔥
APPROVED_EMOJI = "5316827280863934685"  # 💎
DECLINED_EMOJI = "5316660455744223443"  # ❌
GATE_EMOJI = "5267500801240092311"      # ⭐
CARD_EMOJI = "5348296214183950233"      # 💎
RESPONSE_EMOJI = "5348235470461483629"  # ⚡
SPINNER_EMOJI = "5215327832040811010"   # ⏳
TOOK_EMOJI = "5776213190387961618"      # ⏰


def _emoji(emoji_id: str, fallback: str) -> str:
    return f"<tg-emoji emoji-id='{emoji_id}'>{fallback}</tg-emoji>"


def _fmt_elapsed(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s}s"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"


def _short(text: str, limit: int = 80) -> str:
    if not text:
        return "-"
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def render_mass_progress(
    *,
    gate_name: str,
    total: int,
    checked: int,
    charged: int = 0,
    approved: int = 0,
    declined: int = 0,
    card: str = "-",
    response: str = "-",
    start_time: Optional[float] = None,
    elapsed: Optional[float] = None,
    in_progress: bool = True,
) -> str:
    """Build the HTML body of the mass-check progress card."""
    pct = (checked / total * 100.0) if total else 0.0
    if elapsed is None:
        elapsed = (time.time() - start_time) if start_time else 0.0

    spinner = f" {_emoji(SPINNER_EMOJI, '⏳')}" if in_progress else ""

    return (
        f"{_emoji(HEADER_EMOJI, '⚡')} <b>𝗠𝗮𝘀𝘀 𝗖𝗵𝗲𝗰𝗸 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀</b>\n"
        f"\n"
        f"{_emoji(PROGRESS_EMOJI, '🕯')} <b>𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀</b> : {checked}/{total} ({pct:.0f}%)\n"
        f"{_emoji(CHARGED_EMOJI, '🔥')} <b>𝗖𝗵𝗮𝗿𝗴𝗲𝗱</b> : {charged}\n"
        f"{_emoji(APPROVED_EMOJI, '💎')} <b>𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱</b> : {approved}\n"
        f"{_emoji(DECLINED_EMOJI, '❌')} <b>𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱</b> : {declined}\n"
        f"\n"
        f"{_emoji(GATE_EMOJI, '⭐')} <b>𝗚𝗮𝘁𝗲 𝗡𝗮𝗺𝗲</b> : <code>{html.escape(gate_name)}</code>\n"
        f"\n"
        f"{_emoji(CARD_EMOJI, '💎')} <b>𝗖𝗮𝗿𝗱</b> : <code>{html.escape(_short(card, 50))}</code>\n"
        f"{_emoji(RESPONSE_EMOJI, '⚡')} <b>𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲</b> : <code>{html.escape(_short(response, 80))}</code>{spinner}\n"
        f"\n"
        f"{_emoji(TOOK_EMOJI, '⏰')} <b>𝗧𝗼𝗼𝗸</b> : <code>{_fmt_elapsed(elapsed)}</code>"
    )


def stop_keyboard(callback_data: str = "mass_stop") -> InlineKeyboardMarkup:
    """Single blue STOP button below the progress card."""
    return InlineKeyboardMarkup([
        [
            styled_button(
                "𝗦𝘁𝗼𝗽",
                callback_data=callback_data,
                color="blue",
            )
        ]
    ])
