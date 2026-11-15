"""
tools/plan.py

The ``/plan`` command — shows all subscription plan details and the user's
current plan/credits.
"""

from __future__ import annotations

import logging
from typing import Tuple

from telegram import Update, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

from config import OWNER_ID, PLAN_DETAILS
from db import get_user
from force_join import force_join
from utils.credits import format_credits, is_unlimited
from utils.styled_buttons import styled_button


logger = logging.getLogger(__name__)


PLAN_PRICES = {
    "Silver": "5 USD",
    "Gold": "12 USD",
    "Platinum": "25 USD",
    "Diamond": "45 USD",
}

# Premium emoji on the "Buy Plan (DM Owner)" button.
BUY_PLAN_ICON_ID = "6129705083501293112"


async def build_plan_message(user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Build the text + inline keyboard for /plan and the Plans inline button."""
    user_data = await get_user(user_id) or {}
    current_plan = "Owner" if is_unlimited(user_id) else user_data.get("plan", "Free")
    credits = format_credits(user_id, user_data.get("credits", 0))
    expiry = "∞" if is_unlimited(user_id) else user_data.get("plan_expiry", "N/A")

    plan_emoji = {
        "Silver": "🧃",
        "Gold": "🧋",
        "Platinum": "🍰",
        "Diamond": "🍭",
    }

    lines = [
        "<b>💎 𝗕𝗼𝘁 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻 𝗣𝗹𝗮𝗻𝘀</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    for name, details in PLAN_DETAILS.items():
        emoji = plan_emoji.get(name, "✨")
        price = PLAN_PRICES.get(name, "DM owner")
        lines.append(f"{emoji} <b>{name}</b>")
        lines.append(f"   • Credits: <b>{details['credits']}</b>")
        lines.append(f"   • Validity: <b>{details['days']} days</b>")
        lines.append(f"   • Price: <b>{price}</b>")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("<b>👤 Your Plan</b>")
    lines.append(f"   • Plan: <b>{current_plan}</b>")
    lines.append(f"   • Credits: <b>{credits}</b>")
    lines.append(f"   • Expiry: <b>{expiry}</b>")
    lines.append("")
    lines.append("📩 To purchase / extend a plan, contact the owner.")

    text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup([
        [
            styled_button(
                "Buy Plan",
                url=f"tg://user?id={OWNER_ID}",
                color="blue",
                icon=BUY_PLAN_ICON_ID,
            )
        ]
    ])
    return text, keyboard


@force_join
async def plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text, keyboard = await build_plan_message(user_id)

    await update.effective_message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


def register_plan_command(application):
    application.add_handler(CommandHandler("plan", plan_command))
    logger.info("✅ /plan command registered")
