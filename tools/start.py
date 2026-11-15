# Start command handler for Black X Card Bot
# Updated with premium emoji buttons

import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user, update_user
from config import OWNER_ID, ADMIN_IDS, DEVELOPER_LINK
from force_join import force_join
from gates.menu_handlers import _btn
from utils.credits import format_credits

logger = logging.getLogger(__name__)

@force_join
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command with premium emoji buttons.

    Works for both /start (Message update) and the force-join 'Done!'
    callback (CallbackQuery update) — uses ``update.effective_chat`` and
    ``context.bot.send_video`` instead of ``update.message.reply_video``
    so it doesn't crash when there's no ``update.message``.
    """
    user = update.effective_user
    chat = update.effective_chat
    user_id = user.id
    chat_id = chat.id if chat is not None else user_id

    try:
        # Get user data
        user_data_task = asyncio.create_task(get_user(user_id))
        
        # Prepare user info
        user_full_name = user.first_name or "User"
        if user.last_name:
            user_full_name += f" {user.last_name}"
        
        # Clickable name that opens user profile
        clickable_name = f'<a href="tg://user?id={user_id}">{user_full_name}</a>'
        
        # Wait for user data
        try:
            user_data = await user_data_task
        except Exception as e:
            logger.error(f"Error fetching user data: {e}")
            user_data = None
        
        # If no user data, create with defaults
        if not user_data:
            await update_user(
                user_id,
                credits=200,
                plan="Free",
                status="Free User",
                plan_expiry="N/A",
                registered_at=datetime.now().strftime('%d-%m-%Y'),
                keys_redeemed=0
            )
            user_data = await get_user(user_id)
        
        plan = user_data.get('plan', 'Free')
        stored_status = (user_data.get('status') or '').strip()
        credits = format_credits(user_id, user_data.get('credits', 200))

        # Determine user status — prefer stored DB status set by plan_manager
        if user_id == OWNER_ID:
            status = "Owner"
        elif user_id in ADMIN_IDS:
            status = "Admin"
        elif stored_status and stored_status.lower() not in ("free", "free user", ""):
            status = stored_status
        elif "Trial" in plan:
            status = "Trial"
        elif "Premium" in plan:
            status = "Premium"
        elif "Plus" in plan:
            status = "Plus"
        elif "Prime" in plan:
            status = "Prime"
        elif "Silver" in plan:
            status = "Silver"
        elif "Gold" in plan:
            status = "Gold"
        elif "Platinum" in plan:
            status = "Platinum"
        elif "Diamond" in plan:
            status = "Diamond"
        else:
            status = "Free"
        
        # Build the final welcome message with the requested spoiler line
        final_text = (
            f"<tg-emoji emoji-id='5017122105011995219'>🌟</tg-emoji> <b>𝙒𝙀𝙇𝘾𝙊𝙈𝙀 𝙏𝙊 𝘿𝘼𝙍𝙆 𝙓</b>\n"
            f"<tg-emoji emoji-id='5260294334619042015'>⚡</tg-emoji> <i>Ultra Premium Checker</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<tg-emoji emoji-id='5852557780262592341'>✈️</tg-emoji> <b>𝙔𝙤𝙪𝙧 𝙋𝙧𝙤𝙛𝙞𝙡𝙚</b>\n"
            f"• 𝑼𝒔𝒆𝒓 ➜ {clickable_name}\n"
            f"• 𝑰𝑫 ➜ <code>{user_id}</code>\n"
            f"• 𝑺𝒕𝒂𝒕𝒖𝒔 ➜ <b>{status}</b>\n"
            f"• 𝑪𝒓𝒆𝒅𝒊𝒕𝒔 ➜ <code>{credits}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<tg-spoiler>Tap Gates · Tools · Panel below</tg-spoiler>\n"
            f"<tg-emoji emoji-id='5260294334619042015'>⚡</tg-emoji> 𝑽𝒆𝒓𝒔𝒊𝒐𝒏 <b>2.0 𝑼𝒍𝒕𝒓𝒂</b>"
        )

        buttons = [
            [
                _btn(
                    "𝙂𝙖𝙩𝙚𝙨",
                    callback_data="gates_menu",
                    color="green",
                    icon="5852881749645728848",
                ),
                _btn(
                    "𝙏𝙤𝙤𝙡𝙨",
                    callback_data="tools_menu",
                    color="green",
                    icon="5854872574361608556",
                ),
            ],
            [
                _btn(
                    "𝑶𝒘𝒏𝒆𝒓",
                    url=DEVELOPER_LINK,
                    color="blue",
                    icon="5854899611180736052",
                )
            ],
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        
        video_url = "https://files.catbox.moe/fvmte9.mp4"
        # Build premium colored keyboard
        buttons = [
            [
                _btn("𝙂𝙖𝙩𝙚𝙨", callback_data="gates_menu", color="green", icon="5852881749645728848"),
                _btn("𝙏𝙤𝙤𝙡𝙨", callback_data="tools_menu", color="blue", icon="5854872574361608556"),
            ],
            [
                _btn("𝙋𝙧𝙤𝙛𝙞𝙡𝙚", callback_data="tools_menu", color="blue", icon="5854899611180736052"),
                _btn("𝘼𝙙𝙢𝙞𝙣", callback_data="admin_panel_ui", color="red", icon="5260294334619042015"),
            ],
            [
                _btn("𝑶𝒘𝒏𝒆𝒓", url=DEVELOPER_LINK, color="blue", icon="5854899611180736052"),
                _btn("𝙎𝙪𝙥𝙥𝙤𝙧𝙩", url=DEVELOPER_LINK, color="green", icon="5017122105011995219"),
            ],
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        try:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_url,
                caption=final_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                supports_streaming=True,
            )
        except Exception as ve:
            logger.warning(f"send_video failed, fallback photo: {ve}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=final_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )

    except Exception as e:
        logger.error(f"Start command error: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="<tg-emoji emoji-id='5017122105011995219'>🌟</tg-emoji> Welcome to DARK X CHECKER\n\nUse buttons below to get started!",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [
                    _btn(
                        "𝙂𝙖𝙩𝙚𝙨",
                        callback_data="gates_menu",
                        color="green",
                        icon="5852881749645728848",
                    ),
                    _btn(
                        "𝙏𝙤𝙤𝙡𝙨",
                        callback_data="tools_menu",
                        color="green",
                        icon="5854872574361608556",
                    ),
                ],
                [
                    _btn(
                        "𝑶𝒘𝒏𝒆𝒓",
                        url=DEVELOPER_LINK,
                        color="blue",
                        icon="5854899611180736052",
                    )
                ],
            ])
        )
