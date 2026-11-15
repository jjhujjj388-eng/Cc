# admin/auth_commands.py
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import update_user, get_user
from config import OWNER_ID, ADMIN_IDS, AUTHORIZED_CHATS, AUTHORIZED_PRIVATE_USERS, DEFAULT_FREE_CREDITS
import logging

logger = logging.getLogger(__name__)

def escape_markdown(text: str) -> str:
    """Escape special characters for MarkdownV2"""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def auth_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Authorize a group to use the bot"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 𝙔𝙤𝙪 𝙖𝙧𝙚 𝙣𝙤𝙩 𝙖𝙪𝙩𝙝𝙤𝙧𝙞𝙯𝙚𝙙 𝙩𝙤 𝙪𝙨𝙚 𝙩𝙝𝙞𝙨 𝙘𝙤𝙢𝙢𝙖𝙣𝙙.")

    if not context.args or not context.args[0].strip('-').isdigit():
        return await update.effective_message.reply_text(
            "❌ Invalid format\\. Usage: `/au [chat_id]`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    try:
        chat_id = int(context.args[0])
        if chat_id > 0:
            return await update.effective_message.reply_text(
                "❌ That is not a group chat ID\\. Make sure you provide a valid group chat ID that starts with `-`\\.", 
                parse_mode=ParseMode.MARKDOWN_V2
            )

        AUTHORIZED_CHATS.add(chat_id)
        await update.effective_message.reply_text(
            f"✅ Group with chat ID `{chat_id}` has been authorized\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

    except ValueError:
        return await update.effective_message.reply_text(
            "❌ Invalid chat ID format\\. Please provide a valid integer chat ID\\.", 
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def remove_authorize_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a user's private access and reset their plan"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 𝙔𝙤𝙪 𝙖𝙧𝙚 𝙣𝙤𝙩 𝙖𝙪𝙩𝙝𝙤𝙧𝙞𝙯𝙚𝙙 𝙩𝙤 𝙪𝙨𝙚 𝙩𝙝𝙞𝙨 𝙘𝙤𝙢𝙢𝙖𝙣𝙙.")

    if not context.args or not context.args[0].isdigit():
        return await update.effective_message.reply_text(
            "❌ Invalid format\\. Usage: `/rauth [user_id]`",
            parse_mode=ParseMode.MARKDOWN_V2
        )

    try:
        user_id = int(context.args[0])

        # Remove from authorized private users set
        if user_id in AUTHORIZED_PRIVATE_USERS:
            AUTHORIZED_PRIVATE_USERS.discard(user_id)

        # Reset user plan to Free in database
        await update_user(
            user_id,
            plan='Free',
            status='Free',
            credits=DEFAULT_FREE_CREDITS,
            plan_expiry='N/A'
        )

        # ✅ Fixed: Use HTML parse mode to avoid markdown escaping issues
        await update.effective_message.reply_text(
            f"✅ User <code>{user_id}</code> has been de-authorized and plan reset to Free.",
            parse_mode=ParseMode.HTML
        )

    except ValueError:
        return await update.effective_message.reply_text(
            "❌ Invalid user ID format. Please provide a valid integer user ID.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error in remove_authorize_user: {e}")
        await update.effective_message.reply_text(
            f"❌ Database error: {str(e)}",
            parse_mode=ParseMode.HTML
        )

async def take_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a user's current plan and revoke private access"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 𝙔𝙤𝙪 𝙖𝙧𝙚 𝙣𝙤𝙩 𝙖𝙪𝙩𝙝𝙤𝙧𝙞𝙯𝙚𝙙 𝙩𝙤 𝙪𝙨𝙚 𝙩𝙝𝙞𝙨 𝙘𝙤𝙢𝙢𝙖𝙣𝙙.")

    if not context.args or not context.args[0].isdigit():
        return await update.effective_message.reply_text(
            "❌ Invalid format\\. Usage: `/take_plan [user_id]`", 
            parse_mode=ParseMode.MARKDOWN_V2
        )
    
    try:
        user_id = int(context.args[0])
        
        # Reset plan and credits
        await update_user(
            user_id,
            plan='Free',
            status='Free',
            plan_expiry='N/A',
            credits=DEFAULT_FREE_CREDITS
        )

        AUTHORIZED_PRIVATE_USERS.discard(user_id)

        # ✅ Fixed: Use HTML parse mode
        await update.effective_message.reply_text(
            f"✅ Plan and private access have been removed for user <code>{user_id}</code>.",
            parse_mode=ParseMode.HTML
        )

    except ValueError:
        return await update.effective_message.reply_text(
            "❌ Invalid user ID format. Please provide a valid integer user ID.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error in take_plan: {e}")
        await update.effective_message.reply_text(
            f"❌ Database error: {str(e)}",
            parse_mode=ParseMode.HTML
        )