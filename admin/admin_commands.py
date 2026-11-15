# admin/admin_commands.py
import re
from datetime import datetime, timedelta
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import update_user, get_all_users
from config import OWNER_ID, ADMIN_IDS, DEFAULT_FREE_CREDITS, AUTHORIZED_PRIVATE_USERS, AUTHORIZED_CHATS
import logging

logger = logging.getLogger(__name__)

def escape_markdown_v2(text: str) -> str:
    """Escape for MarkdownV2"""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', str(text))

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
        
        await update_user(
            user_id,
            plan='Free',
            status='Free',
            plan_expiry='N/A',
            credits=DEFAULT_FREE_CREDITS
        )

        AUTHORIZED_PRIVATE_USERS.discard(user_id)

        await update.effective_message.reply_text(
            f"✅ Plan and private access have been removed for user `{user_id}`\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

    except ValueError:
        return await update.effective_message.reply_text(
            "❌ Invalid user ID format\\. Please provide a valid integer user ID\\.",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows all admin commands, authorized groups, and private plan users."""

    # Updated admin commands list with NEW plans only
    admin_commands_list = (
        "• `/give_silver <user_id>`: Give 7\\-day Silver Plan \\(500cr\\)\n"
        "• `/give_gold <user_id>`: Give 15\\-day Gold Plan \\(1500cr\\)\n"
        "• `/give_platinum <user_id>`: Give 30\\-day Platinum Plan \\(3000cr\\)\n"
        "• `/give_diamond <user_id>`: Give 60\\-day Diamond Plan \\(5000cr\\)\n"
        "• `/take_plan <user_id>`: Remove plan & private access\n"
        "• `/gen_silver [count]`: Generate Silver redeem codes\n"
        "• `/gen_gold [count]`: Generate Gold redeem codes\n"
        "• `/gen_platinum [count]`: Generate Platinum redeem codes\n"
        "• `/gen_diamond [count]`: Generate Diamond redeem codes\n"
        "• `/au <chat_id>`: Authorize a group\n"
        "• `/rauth <user_id>`: Remove private user auth\n"
        "• `/addcr <user_id> <credits>`: Add credits to user\n"
    )

    # Authorized Groups
    authorized_groups_list = []
    for chat_id in AUTHORIZED_CHATS:
        try:
            chat = await context.bot.get_chat(chat_id)
            name = escape_markdown_v2(chat.title or "N/A")
        except Exception:
            name = "Unknown or Left Group"
        escaped_id = escape_markdown_v2(str(chat_id))
        authorized_groups_list.append(f"• `{escaped_id}` → *{name}*")
    authorized_groups_str = (
        "\n".join(authorized_groups_list) if authorized_groups_list else "_No groups authorized\\._"
    )

    # Private plan users
    users = await get_all_users()
    plan_users = []
    for user in users:
        plan = user.get("plan", "Free")
        if plan.lower() not in ["free", "n/a"]:
            uid = escape_markdown_v2(str(user["id"]))
            plan_escaped = escape_markdown_v2(plan)
            plan_users.append(f"• ID: `{uid}` \\| Plan: `{plan_escaped}`")
    authorized_users_str = (
        "\n".join(plan_users) if plan_users else "_No private users with plans\\._"
    )

    admin_dashboard_message = (
        "╭━━━━━『 𝘼𝙙𝙢𝙞𝙣 𝘾𝙢𝙙 』━━━━━╮\n"
        "┣ 🤖 *Admin Commands:*\n"
        f"{admin_commands_list}\n"
        "╭━━━『 𝘈𝘶𝘵𝘩𝘰𝘳𝘪𝘴𝘦𝘥 𝘎𝘳𝘰𝘶𝘱𝘴 』━━━╮\n"
        f"{authorized_groups_str}\n"
        "╭━━━『 𝘈𝘶𝘵𝘩𝘰𝘳𝘪𝘴𝘦𝘥 𝘜𝘴𝘦𝘳𝘴 \\(Private Plans\\) 』━━━╮\n"
        f"{authorized_users_str}"
    )

    await update.effective_message.reply_text(
        admin_dashboard_message,
        parse_mode=ParseMode.MARKDOWN_V2
    )