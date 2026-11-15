# utils/decorators.py
import time
import asyncio
from functools import wraps
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config import OWNER_ID, ADMIN_IDS, AUTHORIZED_CHATS
from force_join import force_join

# ✅ OPTIMIZED: Thread-safe cooldown dict + asyncio Lock
# Concurrent updates ON hone ke baad race condition aa sakti thi — ye fix karta hai
user_last_command = {}
_cooldown_lock = asyncio.Lock()

async def enforce_cooldown(user_id: int, update: Update, cooldown_seconds: int = 5) -> bool:
    """Enforce command cooldown — thread-safe for concurrent updates.

    The bot owner and any admin are exempt and never see the wait prompt.
    """
    if user_id == OWNER_ID or user_id in ADMIN_IDS:
        return True

    current_time = time.time()

    async with _cooldown_lock:
        last_time = user_last_command.get(user_id, 0)

        if current_time - last_time < cooldown_seconds:
            remaining = cooldown_seconds - (current_time - last_time)
            await update.effective_message.reply_text(
                f"⏳ 𝙋𝙡𝙚𝙖𝙨𝙚 𝙬𝙖𝙞𝙩 {remaining:.0f} 𝙨𝙚𝙘𝙤𝙣𝙙𝙨",
                parse_mode=ParseMode.HTML
            )
            return False

        user_last_command[user_id] = current_time
        return True

def restricted(func):
    """Restrict to authorized users/groups"""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type
        
        # Check banned users
        from admin.system_commands import BANNED_USERS
        if user_id in BANNED_USERS:
            await update.message.reply_text("🚫 You are banned.")
            return
        
        # Allow owner or private chats
        if chat_type != "private" and chat_id not in AUTHORIZED_CHATS and user_id != OWNER_ID:
            await update.message.reply_text(
                f"🚫 Group not authorized.\n📩 Contact {AUTHORIZATION_CONTACT}",
                parse_mode=ParseMode.HTML
            )
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapped

def owner_only(func):
    """Owner only commands"""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id != OWNER_ID:
            await update.message.reply_text("🚫 Owner only.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def admin_only(func):
    """Admin only commands"""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != OWNER_ID and user_id not in ADMIN_IDS:
            await update.message.reply_text("🚫 Admins only!")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped


# =====================================================================
# === Premium / chat-type gating ======================================
# =====================================================================
async def _user_is_premium(user_id: int) -> bool:
    """Owner and admins are always premium. Otherwise consult plan label."""
    if user_id == OWNER_ID or user_id in ADMIN_IDS:
        return True
    try:
        from utils.credits import is_premium as _ip
        return await _ip(user_id)
    except Exception:
        return False


def premium_only(func):
    """Mass gates: only owner / admins / premium plan users may use.
    Free users get a polite refusal in any chat type."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not await _user_is_premium(user_id):
            try:
                await update.effective_message.reply_text(
                    "🚫 <i>This command is for <b>Premium</b> users only.</i>\n"
                    "<i>Upgrade your plan to unlock mass gates.</i>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return
        return await func(update, context, *args, **kwargs)
    return wrapped


def private_premium_only(func):
    """Single gates: in private chat, premium only. In groups, anyone allowed."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_type = update.effective_chat.type if update.effective_chat else "private"
        user_id = update.effective_user.id
        if chat_type == "private" and not await _user_is_premium(user_id):
            try:
                await update.effective_message.reply_text(
                    "🚫 <i>Free users can only check cards in the <b>group</b>.</i>\n"
                    "<i>Upgrade to <b>Premium</b> to use the bot in DM.</i>",
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                pass
            return
        return await func(update, context, *args, **kwargs)
    return wrapped
