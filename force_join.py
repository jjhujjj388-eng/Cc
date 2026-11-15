# force_join.py
from functools import wraps
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application
from telegram.error import BadRequest, Forbidden

# --- Configuration (pulled from config.py so there's only one source of truth) ---
from config import (
    ADMIN_IDS,
    OWNER_ID,
    FORCE_JOIN_GROUP_ID as GROUP_ID,
    FORCE_JOIN_GROUP_USERNAME as GROUP_USERNAME,
    FORCE_JOIN_CHANNEL_ID as CHANNEL_ID,
    FORCE_JOIN_CHANNEL_USERNAME as CHANNEL_USERNAME,
)
from utils.styled_buttons import styled_button


def _force_join_keyboard() -> InlineKeyboardMarkup:
    """Coloured + premium-emoji buttons for the join gate.

    Layout matches the rest of the bot: top action row is green,
    the lone final-action row (Done!) is blue.
    """
    return InlineKeyboardMarkup([
        [
            styled_button(
                "𝙂𝙧𝙤𝙪𝙥",
                url=str(GROUP_USERNAME),
                color="green",
            ),
            styled_button(
                "𝘾𝙝𝙖𝙣𝙣𝙚𝙡",
                url=f"https://t.me/{CHANNEL_USERNAME}",
                color="green",
            ),
        ],
        [
            styled_button(
                "𝘿𝙤𝙣𝙚!",
                callback_data="check_joined",
                color="blue",
            ),
        ],
    ])


_FORCE_JOIN_TEXT = (
    '<tg-emoji emoji-id="5122980872626112634">💎</tg-emoji> 𝗔𝗰𝗰𝗲𝘀𝘀 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱\n\n'
    '𝙁𝙞𝙧𝙨𝙩 𝙔𝙤𝙪 𝙉𝙚𝙚𝙙 𝙏𝙤 𝙅𝙤𝙞𝙣 𝙊𝙪𝙧 𝙂𝙧𝙤𝙪𝙥 𝘼𝙣𝙙 𝘾𝙝𝙖𝙣𝙣𝙚𝙡 '
    '<tg-emoji emoji-id="5125485783452485568">💎</tg-emoji>\n\n'
    '𝘼𝙛𝙩𝙚𝙧 𝙅𝙤𝙞𝙣𝙞𝙣𝙜 𝘾𝙡𝙞𝙘𝙠 𝘿𝙤𝙣𝙚 ! 𝘽𝙪𝙩𝙩𝙤𝙣 '
    '<tg-emoji emoji-id="5125285625091589713">💎</tg-emoji>'
)

logger = logging.getLogger("force_join")
logger.setLevel(logging.INFO)

# Commands that bypass the join gate. ``/start`` is intentionally NOT here so
# brand-new users always see the join prompt the first time they DM the bot.
EXEMPT_COMMANDS = ["broad", "cancel"]


def _is_privileged(user_id: int) -> bool:
    """Owner / admins skip force-join entirely."""
    return user_id == OWNER_ID or user_id in ADMIN_IDS

async def safe_get_member(bot, chat_id, user_id: int):
    """Safely check if a user is in a group/channel"""
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        logger.info(f"[DEBUG] User {user_id} in {chat_id}: {member.status}")
        return member.status
    except BadRequest as e:
        if "user not found" in str(e).lower() or "user not participant" in str(e).lower():
            logger.info(f"[DEBUG] User {user_id} NOT in {chat_id}")
            return "not_member"
        else:
            logger.warning(f"[SAFE CHECK] Failed to get member {user_id} in {chat_id}: {e}")
            return None
    except Forbidden:
        logger.warning(f"[SAFE CHECK] Bot not admin in chat {chat_id} or chat inaccessible")
        return None
    except Exception as e:
        logger.warning(f"[SAFE CHECK] Error getting member {user_id} in {chat_id}: {e}")
        return None

async def is_user_joined(bot, user_id: int) -> bool:
    """Check if user has joined BOTH group and channel"""
    valid_statuses = ["member", "administrator", "creator", "restricted"]

    group_status = await safe_get_member(bot, GROUP_ID, user_id)
    if group_status not in valid_statuses:
        logger.warning(f"User {user_id} NOT in group ({group_status})")
        return False

    channel_status = await safe_get_member(bot, CHANNEL_ID, user_id)
    if channel_status not in valid_statuses:
        logger.warning(f"User {user_id} NOT in channel ({channel_status})")
        return False

    logger.info(f"User {user_id} is in group & channel ✅")
    return True

def force_join(func):
    """Decorator to enforce group + channel join before using a command"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if _is_privileged(user_id):
            return await func(update, context)

        # ---- Ban gate: banned users can't run ANY command ----
        try:
            from admin.system_commands import BANNED_USERS, closed_commands
        except Exception:
            BANNED_USERS, closed_commands = set(), set()
        if user_id in BANNED_USERS:
            try:
                if update.message:
                    await update.message.reply_text("🚫 You are banned from using this bot.")
            except Exception:
                pass
            return

        command_name = ""
        if update.message and update.message.text:
            cmd_text = update.message.text.split()[0]
            if cmd_text.startswith(('/', '.')):
                command_name = cmd_text[1:].split('@')[0].lower()

        if command_name in EXEMPT_COMMANDS:
            return await func(update, context)

        # ---- /close gate: respect closed commands for non-privileged users ----
        if command_name and command_name in closed_commands:
            try:
                if update.message:
                    await update.message.reply_text(
                        f"🚫 The /{command_name} command is temporarily closed."
                    )
            except Exception:
                pass
            return

        joined = await is_user_joined(context.bot, user_id)
        if not joined:
            reply_markup = _force_join_keyboard()

            if update.message:
                await update.message.reply_text(
                    text=_FORCE_JOIN_TEXT,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            elif update.callback_query:
                await update.callback_query.message.reply_text(
                    text=_FORCE_JOIN_TEXT,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )

            try:
                if update.message:
                    await update.message.delete()
            except Exception:
                pass

            return

        return await func(update, context)

    return wrapper

async def check_joined_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Re-check membership when user clicks 'Done!'"""
    query = update.callback_query
    user_id = query.from_user.id

    logger.info(f"Callback triggered by user {user_id}")

    joined = await is_user_joined(context.bot, user_id)

    if joined:
        await query.answer(
            "𝙏𝙝𝙖𝙣𝙠 𝙮𝙤𝙪 𝙁𝙤𝙧 𝙅𝙤𝙞𝙣𝙞𝙣𝙜 𝙉𝙤𝙬 𝙔𝙤𝙪 𝘾𝙖𝙣 𝙐𝙨𝙚 𝙊𝙪𝙧 𝘽𝙤𝙩!!✅",
            show_alert=True,
        )
        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Failed to delete force-join prompt: {e}")

        # Drop the welcome / start menu so the user lands somewhere useful
        # instead of an empty chat.
        try:
            from tools.start import start_command
            await start_command(update, context)
        except Exception as e:
            logger.warning(f"Post-verify start_command failed: {e}")
    else:
        await query.answer(
            "𝙔𝙤𝙪 𝙃𝙖𝙫𝙚𝙣'𝙩 𝙅𝙤𝙞𝙣 𝙁𝙞𝙧𝙨𝙩 𝙅𝙤𝙞𝙣 !!",
            show_alert=True,
        )
        logger.info(f"User {user_id} clicked 'Done!' but is still missing membership.")

def wrap_all_commands(application: Application):
    """Automatically wrap all command handlers with force_join decorator"""
    for handler in application.handlers.get(0, []):
        if hasattr(handler, 'commands'):
            for command in handler.commands:
                if command.lower() not in EXEMPT_COMMANDS:
                    original_callback = handler.callback
                    handler.callback = force_join(original_callback)
                    logger.info(f"✅ Auto-wrapped command /{command} with force_join")
    
    logger.info("✅ All commands automatically wrapped with force_join!")

def register_force_join_handlers(application: Application):
    """Register force join callback handlers and wrap all commands"""
    from telegram.ext import CallbackQueryHandler
    
    application.add_handler(
        CallbackQueryHandler(
            check_joined_callback,
            pattern="^check_joined$"
        )
    )
    
    wrap_all_commands(application)
    
    logger.info("✅ Force join system fully activated!")

async def global_force_join_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global filter that checks ALL messages for force join"""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id

    if _is_privileged(user_id):
        return

    # Ban gate at the global filter level too
    try:
        from admin.system_commands import BANNED_USERS
    except Exception:
        BANNED_USERS = set()
    if user_id in BANNED_USERS:
        try:
            await update.message.reply_text("🚫 You are banned from using this bot.")
        except Exception:
            pass
        try:
            await update.message.delete()
        except Exception:
            pass
        from telegram.ext import ApplicationHandlerStop
        raise ApplicationHandlerStop

    text = update.message.text.strip()

    if text.startswith(('/', '.')):
        cmd_text = text.split()[0]
        command_name = cmd_text[1:].split('@')[0].lower()

        if command_name in EXEMPT_COMMANDS:
            return
        
        joined = await is_user_joined(context.bot, user_id)
        if not joined:
            await update.message.reply_text(
                text=_FORCE_JOIN_TEXT,
                reply_markup=_force_join_keyboard(),
                parse_mode="HTML"
            )

            try:
                await update.message.delete()
            except Exception:
                pass

            from telegram.ext import ApplicationHandlerStop
            raise ApplicationHandlerStop