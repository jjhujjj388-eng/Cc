# admin/system_commands.py
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import OWNER_ID, ADMIN_IDS
from db import get_all_users, update_user

logger = logging.getLogger(__name__)

# Banned users set
BANNED_USERS = set()

# Closed commands set
closed_commands = set()


def _is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMIN_IDS


async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban a user from using the bot."""
    if not _is_owner(update.effective_user.id):
        await update.message.reply_text("🚫 Only the bot owner can ban users.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return

    try:
        user_id = int(context.args[0])
        BANNED_USERS.add(user_id)
        await update.message.reply_text(f"✅ User {user_id} has been banned.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")


async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unban a user."""
    if not _is_owner(update.effective_user.id):
        await update.message.reply_text("🚫 Only the bot owner can unban users.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return

    try:
        user_id = int(context.args[0])
        BANNED_USERS.discard(user_id)
        await update.message.reply_text(f"✅ User {user_id} has been unbanned.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")


async def close_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close a command."""
    if not _is_owner(update.effective_user.id):
        await update.message.reply_text("🚫 Owner only command.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /close <command>")
        return

    closed_commands.add(context.args[0].lower())
    await update.message.reply_text(f"The /{context.args[0]} command is now closed.")


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Re-open a previously closed command."""
    if not _is_owner(update.effective_user.id):
        await update.message.reply_text("🚫 Owner only command.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Usage: /restart <command>")
        return

    closed_commands.discard(context.args[0].lower())
    await update.message.reply_text(f"The /{context.args[0]} command is now available.")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset every user's credits to a given amount."""
    if not _is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized.")
        return

    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("⚠️ Usage: /reset <amount_of_credits>")
        return

    new_credits = int(context.args[0])
    try:
        users = await get_all_users()
        modified = 0
        for u in users:
            uid = u.get("id")
            if uid is None:
                continue
            if await update_user(int(uid), credits=new_credits):
                modified += 1
        await update.message.reply_text(
            f"✅ Reset credits for {modified}/{len(users)} users to {new_credits}."
        )
    except Exception as e:
        logger.exception("reset_command failed")
        await update.message.reply_text(f"❌ Database error: {e}")
