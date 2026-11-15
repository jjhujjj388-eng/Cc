# admin/addcr.py
"""
Admin Command: /addcr
Add credits to a specific user.
Usage: /addcr <user_id> <amount>
Example: /addcr 7742548417 500
"""

import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

from config import OWNER_ID, ADMIN_IDS
from db import get_user, update_user
from utils.credits import add_credits  # ✅ Existing function

logger = logging.getLogger(__name__)

async def addcr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin-only command to add credits to a user.
    Format: /addcr <user_id> <credits>
    """
    user = update.effective_user
    user_id = user.id

    # ===== 1. PERMISSION CHECK =====
    if user_id != OWNER_ID and user_id not in ADMIN_IDS:
        await update.message.reply_text(
            "🚫 <b>𝘼𝙘𝙘𝙚𝙨𝙨 𝘿𝙚𝙣𝙞𝙚𝙙!</b>\n𝙊𝙣𝙡𝙮 𝙊𝙬𝙣𝙚𝙧 𝙤𝙧 𝘼𝙙𝙢𝙞𝙣𝙨 𝙘𝙖𝙣 𝙪𝙨𝙚 𝙩𝙝𝙞𝙨 𝙘𝙤𝙢𝙢𝙖𝙣𝙙.",
            parse_mode=ParseMode.HTML
        )
        return

    # ===== 2. ARGUMENT PARSING =====
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/addcr &lt;user_id&gt; &lt;credits&gt;</code>\n"
            "Example: <code>/addcr 7742548417 500</code>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        target_user_id = int(context.args[0])
        credits_to_add = int(context.args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ <b>Invalid arguments!</b> User ID and credits must be numbers.",
            parse_mode=ParseMode.HTML
        )
        return

    if credits_to_add <= 0:
        await update.message.reply_text(
            "❌ Credit amount must be positive!",
            parse_mode=ParseMode.HTML
        )
        return

    # ===== 3. FETCH TARGET USER =====
    target_user = await get_user(target_user_id)
    if not target_user:
        await update.message.reply_text(
            f"❌ User <code>{target_user_id}</code> not found in database.\n"
            "They need to /start the bot first.",
            parse_mode=ParseMode.HTML
        )
        return

    old_credits = target_user.get("credits", 0)

    # ===== 4. ADD CREDITS =====
    success = await add_credits(target_user_id, credits_to_add)

    if not success:
        await update.message.reply_text(
            "❌ Failed to update credits. Database error.",
            parse_mode=ParseMode.HTML
        )
        return

    new_credits = old_credits + credits_to_add

    # ===== 5. SUCCESS RESPONSE =====
    response = (
        f"✅ <b>Credits Added Successfully!</b>\n\n"
        f"👤 <b>User:</b> <code>{target_user_id}</code>\n"
        f"💰 <b>Previous Credits:</b> <code>{old_credits}</code>\n"
        f"➕ <b>Added:</b> <code>+{credits_to_add}</code>\n"
        f"📊 <b>New Balance:</b> <code>{new_credits}</code>"
    )

    await update.message.reply_text(response, parse_mode=ParseMode.HTML)

    # Optional: Log the action
    logger.info(f"Admin {user_id} added {credits_to_add} credits to user {target_user_id}")

    # Optional: Notify the target user (uncomment if needed)
    # try:
    #     await context.bot.send_message(
    #         chat_id=target_user_id,
    #         text=f"🎉 <b>You received {credits_to_add} credits!</b>\n"
    #              f"Your new balance is <code>{new_credits}</code>.",
    #         parse_mode=ParseMode.HTML
    #     )
    # except Exception as e:
    #     logger.warning(f"Could not notify user {target_user_id}: {e}")


# ===== REGISTRATION FUNCTION =====
def register_addcr_handler(application):
    """Register the /addcr command with the bot application."""
    application.add_handler(CommandHandler("addcr", addcr_command))
    logger.info("✅ /addcr command registered")