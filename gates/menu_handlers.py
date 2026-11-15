# gates/menu_handlers.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user, update_user
from config import OWNER_ID, ADMIN_IDS, BULLET_GROUP_LINK, DEVELOPER_NAME, DEVELOPER_LINK
from utils.credits import format_credits

logger = logging.getLogger(__name__)

# ============================================================
# === STYLED BUTTONS (Bot API 9.4) ============================
# Every button in every menu is built through the ``_btn``
# helper below. That helper produces an InlineKeyboardButton
# whose JSON (via the to_dict() patch in utils.styled_buttons)
# carries the official Bot API 9.4 ``style`` field
# ("success" = green / "primary" = blue) and a premium
# ``icon_custom_emoji_id`` so the Telegram client renders the
# coloured pill + premium emoji icon natively. Effectively the
# same outcome as POSTing to api.telegram.org/bot<TOKEN>/...
# by hand, but every existing handler keeps working unchanged.
# ============================================================
from utils.styled_buttons import styled_button


def _btn(text: str, *, callback_data: str = None, url: str = None,
         color: str = "blue", icon: str = None) -> InlineKeyboardButton:
    return styled_button(
        text,
        callback_data=callback_data,
        url=url,
        color=color,
        icon=icon,
    )


line1 = "𝙎𝙩𝙖𝙩𝙪𝙨 ↭ 𝘖𝘯𝘭𝘪𝘯𝘦 <tg-emoji emoji-id='5852557780262592341'>✅</tg-emoji>"


async def _send_list_view(q, text: str, keyboard) -> None:
    """Render a long Tools-style command-list view from a callback query.

    Tries to edit the existing photo's caption first. If that fails (e.g.
    because the new text exceeds Telegram's 1024-char caption limit), it
    deletes the photo message and sends a fresh text reply in its place so
    the new view never appears stacked below the old one.
    """
    try:
        await q.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
        return
    except Exception as e:
        logger.info(f"caption edit failed ({e}); swapping to text message")

    try:
        await q.message.delete()
    except Exception:
        pass

    try:
        await q.message.chat.send_message(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"_send_list_view failed to send new message: {e}")

# ===== BACK TO START HANDLER =====
async def back_to_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler to go back to the main menu (exactly like /start)."""
    q = update.callback_query
    await q.answer()
    
    user = q.from_user
    user_id = user.id
    
    try:
        from datetime import datetime
        from telegram import InputMediaPhoto
        
        # Get user data
        user_data = await get_user(user_id)
        
        # Prepare user info
        user_full_name = user.first_name or "User"
        if user.last_name:
            user_full_name += f" {user.last_name}"
        
        clickable_name = f'<a href="tg://user?id={user_id}">{user_full_name}</a>'
        
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
        credits = format_credits(user_id, user_data.get('credits', 200))

        if user_id == OWNER_ID:
            status = "Owner"
        elif user_id in ADMIN_IDS:
            status = "Admin"
        elif "Trial" in plan:
            status = "Trial"
        elif "Premium" in plan:
            status = "Premium"
        elif "Plus" in plan:
            status = "Plus"
        elif "Prime" in plan:
            status = "Prime"
        else:
            status = "Free"
        
        # Build the final 𝘞𝘦𝘭𝘤𝘰𝘮𝘦 𝘮𝘦𝘴𝘴𝘢𝘨𝘦 (exactly like /start)
        final_text = (
            f"<tg-emoji emoji-id='5017122105011995219'>🌟</tg-emoji> 𝘞𝘦𝘭𝘤𝘰𝘮𝘦 𝘛𝘰 𝘚𝘱𝘢𝘤𝘦 𝘊𝘩𝘬 𝘉𝘰𝘵\n\n"
            f"𝑰 𝒂𝒎 𝒚𝒐𝒖𝒓 𝒈𝒐-𝒕𝒐 𝒃𝒐𝒕, 𝒑𝒂𝒄𝒌𝒆𝒅 𝒘𝒊𝒕𝒉 𝒂 𝒗𝒂𝒓𝒊𝒆𝒕𝒚 𝒐𝒇 𝒈𝒂𝒕𝒆𝒔, 𝒕𝒐𝒐𝒍𝒔, 𝒂𝒏𝒅 𝒄𝒐𝒎𝒎𝒂𝒏𝒅𝒔 𝒕𝒐 𝒆𝒏𝒉𝒂𝒏𝒄𝒆 𝒚𝒐𝒖𝒓 𝒆𝒙𝒑𝒆𝒓𝒊𝒆𝒏𝒄𝒆. 𝑬𝒙𝒄𝒊𝒕𝒆𝒅 𝒕𝒐 𝒔𝒆𝒆 𝒘𝒉𝒂𝒕 𝑰 𝒄𝒂𝒏 𝒅𝒐?\n\n"
            f"<tg-spoiler>𝘜𝘴𝘦 𝘉𝘦𝘭𝘰𝘸 𝘉𝘶𝘵𝘵𝘰𝘯 𝘛𝘰 𝘚𝘦𝘦 𝘔𝘺 𝘊𝘰𝘮𝘮𝘢𝘯𝘥..</tg-spoiler>\n\n"
            f"<tg-emoji emoji-id='5852557780262592341'>✈️</tg-emoji> 𝙔𝙤𝙪𝙧 𝙄𝙣𝙛𝙤\n\n"
            f"𝘜𝘴𝘦𝘳 : {clickable_name}\n"
            f"𝘐𝘋 : <code>{user_id}</code>\n"
            f"𝘚𝘵𝘢𝘵𝘶𝘴 : {status}\n"
            f"𝘊𝘳𝘦𝘥𝘪𝘵𝘴 : {credits}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"𝘉𝘰𝘵 𝘝𝘦𝘳𝘴𝘪𝘰𝘯 : 2.0"
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
        
        photo_url = "https://previews.jumpshare.com/thumb/815bc01b796dd6f1733c957c5af194937d658d6ab09dd9f56f787ff6979c1aa2d6716b3fa0e87c4060354f0cd313fcf5ece880f33436bfcaf540e5c01aaefb66371ee2644e74495cef864c07892ef1ce"
        
        # Try to edit the existing photo message
        try:
            await q.edit_message_media(
                media=InputMediaPhoto(media=photo_url, caption=final_text, parse_mode=ParseMode.HTML),
                reply_markup=keyboard
            )
        except Exception:
            # If edit fails, delete old message and send new photo
            try:
                await q.message.delete()
            except:
                pass
            await q.message.reply_photo(
                photo=photo_url,
                caption=final_text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard
            )
            
    except Exception as e:
        logger.error(f"Error in back_to_start_handler: {e}")
        # Fallback with same emoji buttons
        await q.message.reply_text(
            "<tg-emoji emoji-id='5017122105011995219'>🌟</tg-emoji> Welcome back! Use buttons below.",
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

# ===== TOOLS MENU HANDLER =====
async def tools_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for the 'Tools' button with pagination."""
    q = update.callback_query
    await q.answer()
    
    page1_text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "                         𝙏𝙤𝙤𝙡𝙨 <tg-emoji emoji-id='5861909758017018732'>🛠️</tg-emoji>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘚𝘤𝘳𝘦𝘱𝘦𝘳 \n"
        "𝙐𝙨𝙚 ⇾ /scr (channel_link) (amt)\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘚𝘤𝘳𝘢𝘱𝘦 𝘧𝘳𝘰𝘮 𝘮𝘶𝘭𝘵𝘪𝘱𝘭𝘦 𝘤𝘩𝘢𝘯𝘯𝘦𝘭𝘴 \n"
        "𝙐𝙨𝙚 ⇾ /mc (link) (link) (amt)\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘗𝘢𝘺𝘮𝘦𝘯𝘵 𝘎𝘢𝘵𝘦𝘸𝘢𝘺 𝘊𝘩𝘦𝘤𝘬𝘦𝘳\n"
        "𝙐𝙨𝙚 ⇾ /gate {Site_url}\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘔𝘢𝘴𝘴 𝘗𝘢𝘺𝘮𝘦𝘯𝘵 𝘎𝘢𝘵𝘦𝘸𝘢𝘺 𝘊𝘩𝘦𝘤𝘬𝘦𝘳 \n"
        "𝙐𝙨𝙚 ⇾ /mgate {site_url} {site_url}\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"  
        "𝙉𝙖𝙢𝙚 ↣ 𝘍𝘪𝘭𝘭 𝘚𝘱𝘭𝘪𝘵𝘦𝘳\n"
        "𝙐𝙨𝙚 ⇾ /split {amount}\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"  
        "𝙉𝙖𝙢𝙚 ↣ 𝘊𝘭𝘦𝘢𝘯 𝘊𝘢𝘳𝘥𝘴 𝘍𝘳𝘰𝘮 𝘋𝘶𝘮𝘱𝘴\n"
        "𝙐𝙨𝙚 ⇾ /clean\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"        
    )

    keyboard = [
        [_btn("➡️ Next", callback_data="tools_page_2", color="blue", icon="")],
        [_btn("◀️ Back to Menu", callback_data="back_to_start", color="red", icon="")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await q.edit_message_caption(
            caption=page1_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    except Exception:
        try:
            await q.edit_message_text(
                text=page1_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"Failed to edit message, sending a new one: {e}")
            try:
                await q.message.delete()
            except Exception:
                pass
            await q.message.reply_text(
                text=page1_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )

async def tools_page_2_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for Tools page 2."""
    q = update.callback_query
    await q.answer()
    
    page2_text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "                         𝙏𝙤𝙤𝙡𝙨 <tg-emoji emoji-id='5861909758017018732'>🛠️</tg-emoji>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘙𝘢𝘯𝘥𝘰𝘮 𝘊𝘢𝘳𝘥 𝘗𝘪𝘤𝘬 \n"
        "𝙐𝙨𝙚 ⇾ /pick\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘈𝘥𝘥 𝘗𝘳𝘰𝘹𝘺 \n"
        "𝙐𝙨𝙚 ⇾ /addpxy\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘙𝘦𝘮𝘰𝘷𝘦 𝘗𝘳𝘰𝘹𝘺\n"
        "𝙐𝙨𝙚 ⇾ /rmpxy\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘊𝘩𝘦𝘤𝘬 𝘠𝘰𝘶𝘳 𝘈𝘥𝘥𝘦𝘥 𝘗𝘳𝘰𝘹𝘺\n"
        "𝙐𝙨𝙚 ⇾ /mypxy\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"  
        "𝙉𝙖𝙢𝙚 ↣ 𝘍𝘢𝘬𝘦 𝘈𝘥𝘥𝘳𝘦𝘴𝘴 𝘎𝘦𝘯𝘦𝘳𝘢𝘵𝘰𝘳\n"
        "𝙐𝙨𝙚 ⇾ /fk\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"        
        "𝙉𝙖𝙢𝙚 ↣ 𝘉𝘐𝘕 𝘭𝘰𝘰𝘬𝘶𝘱\n"
        "𝙐𝙨𝙚 ⇾ /bin {bin}\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"        
    )

    keyboard = [
        [_btn("⬅️ Back", callback_data="tools_page_1", color="blue", icon="")],
        [_btn("◀️ Back to Menu", callback_data="back_to_start", color="red", icon="")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await q.edit_message_caption(
            caption=page2_text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    except Exception:
        try:
            await q.edit_message_text(
                text=page2_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.warning(f"Failed to edit message, sending a new one: {e}")
            try:
                await q.message.delete()
            except Exception:
                pass
            await q.message.reply_text(
                text=page2_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )

# ===== GATES MENU HANDLER =====
async def gates_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for the 'Gates' button."""
    q = update.callback_query
    await q.answer()
    
    photo_url = "https://previews.jumpshare.com/thumb/815bc01b796dd6f1733c957c5af194937d658d6ab09dd9f56f787ff6979c1aa2d6716b3fa0e87c4060354f0cd313fcf5ece880f33436bfcaf540e5c01aaefb66371ee2644e74495cef864c07892ef1ce"
    
    text = (
    '━━━━<tg-emoji emoji-id="5852456612307934613">📦</tg-emoji> 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 𝙈𝙚𝙣𝙪 ━━━━\n\n'
    '<tg-emoji emoji-id="5323307196807653127">⚡</tg-emoji> 𝑨𝒖𝒕𝒉 𝑮𝒂𝒕𝒆𝒘𝒂𝒚  - 𝘼𝙘𝙘𝙚𝙨𝙨 𝙖𝙪𝙩𝙝𝙚𝙣𝙩𝙞𝙘𝙖𝙩𝙞𝙤𝙣 𝙛𝙚𝙖𝙩𝙪𝙧𝙚𝙨\n'
    '<tg-emoji emoji-id="5323535839391653590">💰</tg-emoji> 𝑪𝒉𝒂𝒓𝒈𝒆 𝑮𝒂𝒕𝒆𝒘𝒂𝒚 - 𝘼𝙘𝙘𝙚𝙨𝙨 𝙥𝙖𝙮𝙢𝙚𝙣𝙩/𝙘𝙝𝙖𝙧𝙜𝙚 𝙛𝙚𝙖𝙩𝙪𝙧𝙚𝙨\n'
    '<tg-emoji emoji-id="5323307196807653127">📦</tg-emoji> 𝑴𝒂𝒔𝒔 𝑮𝒂𝒕𝒆𝒘𝒂𝒚 - 𝘽𝙪𝙡𝙠 𝙘𝙖𝙧𝙙 𝙘𝙝𝙚𝙘𝙠𝙞𝙣𝙜 𝙛𝙚𝙖𝙩𝙪𝙧𝙚𝙨\n\n'
    "<tg-emoji emoji-id='5854875172816821430'>👀</tg-emoji> 𝑰𝒇 𝒀𝒐𝒖 𝑭𝒂𝒄𝒆 𝑨𝒏𝒚 𝑻𝒊𝒑𝒆 𝑶𝒇 𝑰𝒔𝒔𝒖𝒆 𝑻𝒉𝒂𝒏 𝑫𝑴 𝑨𝒅𝒎𝒊𝒏"
)

    keyboard = InlineKeyboardMarkup([
        [
            _btn("𝘼𝙪𝙩𝙝", callback_data="auth_sub_menu", color="blue", icon="5852881749645728848"),
            _btn("𝘾𝙝𝙖𝙧𝙜𝙚", callback_data="charge_gateway_menu", color="green", icon="5260294334619042015")
        ],
        [
            _btn("𝙈𝙖𝙨𝙨 𝙂𝙖𝙩𝙚𝙬𝙖𝙮", callback_data="mass_gateway_menu", color="blue", icon="")
        ],
        [_btn("◀️ Back to Menu", callback_data="back_to_start", color="red", icon="")]
    ])

    from telegram import InputMediaPhoto
    try:
        # Try to edit the existing photo message
        await q.edit_message_media(
            media=InputMediaPhoto(media=photo_url, caption=text, parse_mode=ParseMode.HTML),
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Failed to edit message to Gates menu, sending new one: {e}")
        # If edit fails, delete old message and send new photo (fallback)
        try:
            await q.message.delete()
        except:
            pass
        await q.message.reply_photo(
            photo=photo_url,
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

# ===== AUTH SUB MENU =====
async def auth_sub_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flat list of every Auth-gate command (Tools-style layout)."""
    q = update.callback_query
    await q.answer()

    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "                 𝘼𝙪𝙩𝙝 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 <tg-emoji emoji-id='5323307196807653127'>⚡</tg-emoji>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘚𝘵𝘳𝘪𝘱𝘦 𝘈𝘶𝘵𝘩 𝘝1\n"
        "𝙐𝙨𝙚 ⇾ /chk cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘚𝘵𝘳𝘪𝘱𝘦 𝘈𝘶𝘵𝘩 𝘝2\n"
        "𝙐𝙨𝙚 ⇾ /sr cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘔𝘢𝘴𝘴 𝘚𝘵𝘳𝘪𝘱𝘦 𝘈𝘶𝘵𝘩\n"
        "𝙐𝙨𝙚 ⇾ /mass (cards / reply .txt)\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘉𝘳𝘢𝘪𝘯𝘵𝘳𝘦𝘦 𝘈𝘶𝘵𝘩\n"
        "𝙐𝙨𝙚 ⇾ /b3 cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘉𝘳𝘢𝘪𝘯𝘵𝘳𝘦𝘦 𝘊𝘩𝘢𝘳𝘨𝘦\n"
        "𝙐𝙨𝙚 ⇾ /bc cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Gate Menu", callback_data="gates_menu", color="red", icon="")]
    ])

    await _send_list_view(q, text, keyboard)

# ===== STRIPE AUTH MENU =====
async def stripe_auth_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for the 'Stripe' auth button."""
    q = update.callback_query
    await q.answer()
    
    text = (
        "𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↬ 𝙎𝙩𝙧𝙞𝙥𝙚 𝙋𝙧𝙚𝙢𝙞𝙪𝙢 𝘼𝙪𝙩𝙝 ➜\n"
        "⤷ 𝘾𝙤𝙢𝙢𝙖𝙣𝙙 <code>/chk</code> [𝙎𝙞𝙣𝙜𝙡𝙚]\n"
        " 𝐒𝐭𝐚𝐭𝐮𝐬     ➜  𝐷𝑒𝑎𝑑 ❌\n"
        "──────────────────────\n"
        "𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↭ 𝙎𝙩𝙧𝙞𝙥𝙚 𝘼𝙪𝙩𝙝 ➜\n"
        "⤷ 𝘾𝙤𝙢𝙢𝙖𝙣𝙙 <code>/sr</code> [𝙎𝙞𝙣𝙜𝙡𝙚]\n"
        " 𝐒𝐭𝐚𝐭𝐮𝐬     ➜  𝐷𝑒𝑎𝑑 ❌\n"
        "──────────────────────\n"
        "𝙎𝙩𝙧𝙞𝙥𝙚 𝙈𝙖𝙨𝙨 𝘾𝙝𝙚𝙘𝙠 ➜\n"
        "⤷ 𝘾𝙤𝙢𝙢𝙖𝙣𝙙 ⇾ <code>/mass</code> [𝙈𝙖𝙨𝙨 𝘾𝙝𝙚𝙘𝙠𝙞𝙣𝙜]\n"
        " 𝐒𝐭𝐚𝐭𝐮𝐬    ➜ 𝐷𝑒𝑎𝑑 ❌"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Auth Menu", callback_data="auth_sub_menu", color="red", icon="")]
    ])
    
    try:
        await q.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Failed to edit message, sending a new one: {e}")
        await q.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

# ===== BRAINTREE AUTH MENU =====
async def braintree_auth_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for the 'Braintree' auth button."""
    q = update.callback_query
    await q.answer()
    
    text = (
        "𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↬ 𝘽𝙧𝙖𝙞𝙣𝙩𝙧𝙚𝙚 𝙋𝙧𝙚𝙢𝙞𝙪𝙢 𝘼𝙪𝙩𝙝 ➜\n"
        "⤷ 𝘾𝙤𝙢𝙢𝙖𝙣𝙙 <code>/b3</code> [𝙎𝙞𝙣𝙜𝙡𝙚]\n"
        "──────────────────────\n"
        "𝙈𝙖𝙨𝙨 𝘾𝙝𝙠 𝘾𝙤𝙢𝙞𝙣𝙜 𝙎𝙤𝙤𝙣 🧠"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Auth Menu", callback_data="auth_sub_menu", color="red", icon="")]
    ])
    
    try:
        await q.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Failed to edit message, sending a new one: {e}")
        await q.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

# ===== CHARGE GATEWAY MENU =====
async def charge_gateway_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flat list of every Charge-gate command (Tools-style layout)."""
    q = update.callback_query
    await q.answer()

    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "               𝘾𝙝𝙖𝙧𝙜𝙚 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 <tg-emoji emoji-id='5323535839391653590'>💰</tg-emoji>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘈𝘶𝘵𝘰 𝘚𝘩𝘰𝘱𝘪𝘧𝘺\n"
        "𝙐𝙨𝙚 ⇾ /sh cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘙𝘢𝘻𝘰𝘳𝘱𝘢𝘺 ₹1\n"
        "𝙐𝙨𝙚 ⇾ /rz cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘚𝘵𝘳𝘪𝘱𝘦 $1\n"
        "𝙐𝙨𝙚 ⇾ /st cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘚𝘵𝘳𝘪𝘱𝘦 $5\n"
        "𝙐𝙨𝙚 ⇾ /st1 cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘚𝘒-𝘉𝘢𝘴𝘦𝘥 $1\n"
        "𝙐𝙨𝙚 ⇾ /cc cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘚𝘒-𝘉𝘢𝘴𝘦𝘥 $5\n"
        "𝙐𝙨𝙚 ⇾ /su cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘚𝘒 𝘒𝘦𝘺 𝘊𝘩𝘦𝘤𝘬\n"
        "𝙐𝙨𝙚 ⇾ /sk sk_xxx\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘗𝘢𝘺𝘗𝘢𝘭 $1\n"
        "𝙐𝙨𝙚 ⇾ /pp cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘗𝘢𝘺𝘗𝘢𝘭 $9\n"
        "𝙐𝙨𝙚 ⇾ /py cc|mm|yy|cvv\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Gate Menu", callback_data="gates_menu", color="red", icon="")]
    ])

    await _send_list_view(q, text, keyboard)

# ===== AUTO SHOPIFY MENU =====
async def auto_shopify_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    bullet = "<a href='https://t.me/DarkCarder05'>「❃」</a>"
    
    text = (
        "━━━━━━ 𝘼𝙪𝙩𝙤 𝙎𝙝𝙤𝙥𝙞𝙛𝙮 ━━━━━━\n\n"
        f"{bullet} 𝘾𝙤𝙢𝙢𝙖𝙣𝙙   <code>/sh</code>  [𝙎𝙞𝙣𝙜𝙡𝙚 𝘾𝙝𝙚𝙘𝙠𝙞𝙣𝙜]\n"
        f"{bullet} 𝙈𝙖𝙨𝙨     <code>/msh</code> [𝙘𝙖𝙧𝙙𝙨 𝙤𝙧 .𝙩𝙭𝙩]\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{bullet} 𝘼𝙙𝙙 𝙎𝙞𝙩𝙚   <code>/add &lt;site&gt;</code>\n"
        f"{bullet} <code>/show</code> 𝘾𝙝𝙚𝙘𝙠 𝙔𝙤𝙪𝙧 𝘼𝙙𝙙𝙚𝙙 𝙎𝙝𝙤𝙥𝙞𝙛𝙮 𝙎𝙞𝙩𝙚𝙨\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{bullet} 𝙐𝙨𝙚 <code>/removeall</code> 𝙏𝙤 𝙍𝙚𝙢𝙤𝙫𝙚 𝘼𝙡𝙡 𝘼𝙙𝙙𝙚𝙙 𝙎𝙞𝙩𝙚𝙨\n"
        f"{bullet} 𝙐𝙨𝙚 <code>/rm</code> 𝙏𝙤 𝙍𝙚𝙢𝙤𝙫𝙚 𝙎𝙞𝙣𝙜𝙡𝙚 𝙎𝙞𝙩𝙚"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Charge Menu", callback_data="charge_gateway_menu", color="red", icon="")]
    ])
    
    await q.edit_message_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ===== SK BASED MENU =====
async def sk_based_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    bullet = "<a href='https://t.me/DarkCarder05'>「❃」</a>"
    
    text = (
        "💸━━ 𝐒𝐊-𝐁𝐚𝐬𝐞𝐝 𝐋𝐨𝐨𝐤𝐔𝐏 ━━🧠\n\n"
        f"{bullet} SK-Based $1 Charge\n"
        f"⤷ 𝐂𝐌𝐃: <code>/cc card|mm|yy|cvv</code>\n"
        f"⤷ 𝐏𝐫𝐢𝐜𝐞: $1.00\n\n"
        f"{bullet} SK-Based $5 Charge\n"
        f"⤷ 𝐂𝐌𝐃: <code>/su card|mm|yy|cvv</code>\n"
        f"⤷ 𝐏𝐫𝐢𝐜𝐞: $5.00\n\n"
        f"{bullet} 𝐒𝐭𝐚𝐭𝐮𝐬  : 𝐷𝑒𝑎𝑑 ❌\n"
        f"{bullet} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 : SK-Based Stripe\n"
        "━━━━━━━━━━━━━━━━━━"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Charge Menu", callback_data="charge_gateway_menu", color="red", icon="")]
    ])
    
    await q.edit_message_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ===== STRIPE CHARGE MENU =====
async def stripe_charge_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    bullet = "<a href='https://t.me/DarkCarder05'>「❃」</a>"
    
    text = (
        "━━━━━━━━ 𝐒𝐭𝐫𝐢𝐩𝐞 1$ ━━━━━━━━\n\n"
        f"{bullet} 𝐂𝐌𝐃   : <code>/st</code>\n"
        f"{bullet} 𝐒𝐭𝐚𝐭𝐮𝐬  : 𝐷𝑒𝑎𝑑 ❌\n"
        f"{bullet} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 : Stripe\n"
        f"{bullet} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 𝐂𝐡𝐚𝐫𝐠𝐞   : $1\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "━━━━━━━━ 𝐒𝐭𝐫𝐢𝐩𝐞 5$ ━━━━━━━━\n\n"
        f"{bullet} 𝐂𝐌𝐃   : <code>/st1</code>\n"
        f"{bullet} 𝐒𝐭𝐚𝐭𝐮𝐬  : 𝐷𝑒𝑎𝑑 ❌\n"
        f"{bullet} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 : Stripe\n"
        f"{bullet} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 𝐂𝐡𝐚𝐫𝐠𝐞   : $5\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Charge Menu", callback_data="charge_gateway_menu", color="red", icon="")]
    ])
    
    await q.edit_message_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ===== PAYPAL 1$ MENU =====
async def paypal1_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    bullet = "<a href='https://t.me/DarkCarder05'>「❃」</a>"
    
    text = (
        "━━━━━━━ 𝙋𝙖𝙮𝙋𝙖𝙡 1$ ━━━━━━━\n\n"
        f"{bullet} 𝘾𝙤𝙢𝙢𝙖𝙣𝙙 ↭ <code>/pp</code>\n"
        f"{bullet} 𝙎𝙩𝙖𝙩𝙪𝙨 ↭ 𝘿𝙚𝙖𝙙 🔥\n"
        f"{bullet} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↭ PayPal\n"
        f"{bullet} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 𝘾𝙝𝙖𝙧𝙜𝙚 ↭ $1\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Charge Menu", callback_data="charge_gateway_menu", color="red", icon="")]
    ])
    
    await q.edit_message_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ===== PAYPAL 9$ MENU =====
async def paypal9_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    bullet = "<a href='https://t.me/DarkCarder05'>「❃」</a>"
    
    text = (
        "━━━━━━━ 𝙋𝙖𝙮𝙋𝙖𝙡 9$ ━━━━━━━\n\n"
        f"{bullet} 𝘾𝙤𝙢𝙢𝙖𝙣𝙙 ↭ <code>/py</code>\n"
        f"{bullet} 𝙎𝙩𝙖𝙩𝙪𝙨 ↭ 𝑨𝒄𝒕𝒊𝒗𝒆 🧠💎\n"
        f"{bullet} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↭ PayPal\n"
        f"{bullet} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 𝘾𝙝𝙖𝙧𝙜𝙚 ↭ $9\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Charge Menu", callback_data="charge_gateway_menu", color="red", icon="")]
    ])
    
    await q.edit_message_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ===== RAZORPAY MENU =====
async def razorpay_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    bullet = "<a href='https://t.me/DarkCarder05'>「❃」</a>"
    
    text = (
        "━━━━━━━ 𝙍𝙖𝙯𝙤𝙧 𝙋𝙖𝙮 ━━━━━━━\n\n"
        f"{bullet} 𝙎𝙞𝙣𝙜𝙡𝙚    <code>/rz</code>    [1 𝙘𝙖𝙧𝙙]\n"
        f"{bullet} 𝙈𝙖𝙨𝙨      <code>/mrz</code>   [𝙘𝙖𝙧𝙙𝙨 𝙤𝙧 .𝙩𝙭𝙩]\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{bullet} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 𝘾𝙝𝙖𝙧𝙜𝙚 ↭ 1₹\n"
        f"{bullet} 𝙎𝙩𝙖𝙩𝙪𝙨 ↭ 𝑨𝒄𝒕𝒊𝒗𝒆 ✅\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Charge Menu", callback_data="charge_gateway_menu", color="red", icon="")]
    ])
    
    try:
        await q.edit_message_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception as e:
        logger.warning(f"Failed to edit message, sending a new one: {e}")
        await q.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

# ===== MASS GATEWAY MENU =====
async def mass_gateway_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Flat list of every Mass-gateway command (Tools-style layout)."""
    q = update.callback_query
    await q.answer()

    text = (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "                𝙈𝙖𝙨𝙨 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 <tg-emoji emoji-id='5852456612307934613'>📦</tg-emoji>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘔𝘢𝘴𝘴 𝘚𝘵𝘳𝘪𝘱𝘦 𝘈𝘶𝘵𝘩\n"
        "𝙐𝙨𝙚 ⇾ /mass (cards / reply .txt)\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘔𝘢𝘴𝘴 𝘚𝘵𝘳𝘪𝘱𝘦 𝘚𝘒-𝘉𝘢𝘴𝘦𝘥\n"
        "𝙐𝙨𝙚 ⇾ /sktxt (reply .txt)\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘔𝘢𝘴𝘴 𝘚𝘵𝘳𝘪𝘱𝘦 (txt)\n"
        "𝙐𝙨𝙚 ⇾ /chktxt (reply .txt)\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘔𝘢𝘴𝘴 𝘉𝘳𝘢𝘪𝘯𝘵𝘳𝘦𝘦\n"
        "𝙐𝙨𝙚 ⇾ /mb3 (reply .txt)\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘔𝘢𝘴𝘴 𝘚𝘩𝘰𝘱𝘪𝘧𝘺\n"
        "𝙐𝙨𝙚 ⇾ /msh (cards / reply .txt)\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘔𝘢𝘴𝘴 𝘗𝘢𝘺𝘗𝘢𝘭\n"
        "𝙐𝙨𝙚 ⇾ /masspp (reply .txt)\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "𝙉𝙖𝙢𝙚 ↣ 𝘙𝘢𝘻𝘰𝘳𝘱𝘢𝘺 𝘔𝘢𝘴𝘴\n"
        "𝙐𝙨𝙚 ⇾ /mrz (cards / reply .txt)\n"
        f"{line1}\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Gate Menu", callback_data="gates_menu", color="red", icon="")]
    ])

    await _send_list_view(q, text, keyboard)

# ===== MASS STRIPE MENU =====
async def mass_stripe_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for the 'Stripe' mass gateway button."""
    q = update.callback_query
    await q.answer()
    
    text = (
        "𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↬ 𝙈𝙖𝙨𝙨 𝙎𝙩𝙧𝙞𝙥𝙚 𝘼𝙪𝙩𝙝\n\n"
        "⤷ 𝘾𝙤𝙢𝙢𝙖𝙣𝙙 ⇾ <code>/chktxt</code>\n"
        "𝙎𝙩𝙖𝙩𝙪𝙨 ⇾ 𝙊𝙣 🔥"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Mass Gateway", callback_data="mass_gateway_menu", color="red", icon="")]
    ])
    
    try:
        await q.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Failed to edit message, sending a new one: {e}")
        await q.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

# ===== MASS BRAINTREE MENU =====
async def mass_braintree_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for the 'Mass Braintree' button."""
    q = update.callback_query
    await q.answer()
    
    owner_link = f"<a href='tg://user?id={OWNER_ID}'>𝑶𝒘𝒏𝒆𝒓</a>"

    text = (
        "𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↬ 𝙈𝙖𝙨𝙨 𝘽𝙧𝙖𝙞𝙣𝙩𝙧𝙚𝙚 𝘼𝙪𝙩𝙝\n\n"
        "⤷ 𝘾𝙤𝙢𝙢𝙖𝙣𝙙 ⇾ <code>/mb3</code>\n"
        "𝙎𝙩𝙖𝙩𝙪𝙨 ⇾ 𝙊𝙣 🔥\n\n"
        "𝙏𝙮𝙥𝙚 ⇾ 𝙋𝙖𝙞𝙙 𝙋𝙡𝙖𝙣𝙨 𝙊𝙣𝙡𝙮 🦂\n\n"
        f"🌿 𝘿𝙢 𝙁𝙤𝙧 𝙋𝙖𝙞𝙙 𝙋𝙡𝙖𝙣 ➞ {owner_link}"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Mass Gateway", callback_data="mass_gateway_menu", color="red", icon="")]
    ])
    
    try:
        await q.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Failed to edit message, sending a new one: {e}")
        await q.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

# ===== MASS SHOPIFY MENU =====
async def mass_shopify_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for the 'Auto Shopify' mass gateway button."""
    q = update.callback_query
    await q.answer()
    
    text = (
        "𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↬ 𝘼𝙪𝙩𝙤 𝙎𝙝𝙤𝙥𝙞𝙛𝙮 💎\n\n"
        "⤷ <code>/msh</code> 𝙎𝙚𝙦𝙪𝙚𝙣𝙩𝙞𝙖𝙡 𝙢𝙖𝙨𝙨 𝙘𝙝𝙚𝙘𝙠\n"
        "⤷ <code>/mtxt</code> 20-𝙘𝙤𝙣𝙘𝙪𝙧𝙧𝙚𝙣𝙩 .𝙩𝙭𝙩 𝙘𝙝𝙚𝙘𝙠\n"
        "⤷ 𝙐𝙨𝙚 ⇾ 𝙎𝙚𝙣𝙙 .𝙩𝙭𝙩 𝙛𝙞𝙡𝙚 𝙤𝙧 𝙧𝙚𝙥𝙡𝙮 𝙬𝙞𝙩𝙝 𝙞𝙩\n"
        "⤷ 𝙎𝙩𝙖𝙩𝙪𝙨 ⇾ 𝙊𝙣 🔥"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Mass Gateway", callback_data="mass_gateway_menu", color="red", icon="")]
    ])
    
    try:
        await q.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Failed to edit message, sending a new one: {e}")
        await q.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

# ===== MASS PAYPAL MENU =====
async def mass_paypal_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for the 'PayPal' mass gateway button."""
    q = update.callback_query
    await q.answer()
    
    text = (
        "𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↬ 𝙈𝙖𝙨𝙨 𝙋𝙖𝙮𝙋𝙖𝙡\n\n"
        "⤷ 𝘾𝙤𝙢𝙢𝙖𝙣𝙙 ⇾ <code>/masspp</code>\n"
        "𝙎𝙩𝙖𝙩𝙪𝙨 ⇾ 𝙊𝙣 🔥\n\n"
        "𝙏𝙮𝙥𝙚 ⇾ 𝙁𝙧𝙚𝙚 𝘼𝙣𝙙 𝙋𝙧𝙚𝙢𝙞𝙪𝙢 𝘽𝙤𝙩𝙝\n\n"
        "𝙐𝙨𝙖𝙜𝙚 ⇾ 𝙍𝙚𝙥𝙡𝙮 𝙒𝙞𝙩𝙝 .𝙩𝙭𝙩 𝙁𝙞𝙡𝙡 𝘼𝙣𝙙 𝘾𝙘𝙨 🦂"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Mass Gateway", callback_data="mass_gateway_menu", color="red", icon="")]
    ])
    
    try:
        await q.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Failed to edit message, sending a new one: {e}")
        await q.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

# ===== MASS SK STRIPE MENU =====
async def mass_sk_stripe_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for the 'Stripe SK Based' mass gateway button."""
    q = update.callback_query
    await q.answer()
    
    owner_link = f"<a href='tg://user?id={OWNER_ID}'>𝑶𝒘𝒏𝒆𝒓</a>"

    text = (
        "𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↬ 𝙎𝙩𝙧𝙞𝙥𝙚 1 𝘿𝙤𝙡𝙡𝙚𝙧 𝘾𝙝𝙖𝙧𝙜𝙚 𝙎𝙠 𝘽𝙖𝙨𝙚𝙙\n\n"
        "⤷ 𝘾𝙤𝙢𝙢𝙖𝙣𝙙 ⇾ <code>/sktxt</code>\n"
        "𝙎𝙩𝙖𝙩𝙪𝙨 ⇾ 𝙊𝙣 🔥\n\n"
        "𝙏𝙮𝙥𝙚 ⇾ 𝙋𝙧𝙚𝙢𝙞𝙪𝙢 𝙊𝙣𝙡𝙮 🦂\n\n"
        "𝙐𝙨𝙖𝙜𝙚 ⇾ 𝙍𝙚𝙖𝙙 𝘾𝙖𝙧𝙙 𝙁𝙧𝙤𝙢 .𝙩𝙭𝙩 𝙁𝙞𝙡𝙡 🦂\n\n"
        f"🌿 𝘿𝙢 𝙁𝙤𝙧 𝙋𝙖𝙞𝙙 𝙋𝙡𝙖𝙣 ➞ {owner_link}"
    )

    keyboard = InlineKeyboardMarkup([
        [_btn("◀️ Back to Mass Gateway", callback_data="mass_gateway_menu", color="red", icon="")]
    ])
    
    try:
        await q.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    except Exception as e:
        logger.warning(f"Failed to edit message, sending a new one: {e}")
        await q.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True
        )

async def admin_panel_ui_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ultra premium admin panel with colored buttons."""
    q = update.callback_query
    user = update.effective_user
    if user.id != OWNER_ID and user.id not in ADMIN_IDS:
        await q.answer("Owner / Admin only.", show_alert=True)
        return
    await q.answer()
    text = (
        "<tg-emoji emoji-id='5260294334619042015'>⚡</tg-emoji> <b>𝘿𝘼𝙍𝙆 𝙓 · 𝘼𝘿𝙈𝙄𝙉 𝙋𝘼𝙉𝙀𝙇</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Plans</b> · give / gen / take\n"
        "<b>Users</b> · credits · broadcast\n"
        "<b>System</b> · groups · auth\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Use buttons or classic /admin commands.</i>"
    )
    keyboard = InlineKeyboardMarkup([
        [
            _btn("𝙎𝙞𝙡𝙫𝙚𝙧", callback_data="admin_help_silver", color="blue", icon="5852881749645728848"),
            _btn("𝙂𝙤𝙡𝙙", callback_data="admin_help_gold", color="green", icon="5852881749645728848"),
        ],
        [
            _btn("𝙋𝙡𝙖𝙩𝙞𝙣𝙪𝙢", callback_data="admin_help_plat", color="blue", icon="5854872574361608556"),
            _btn("𝘿𝙞𝙖𝙢𝙤𝙣𝙙", callback_data="admin_help_dia", color="green", icon="5854872574361608556"),
        ],
        [
            _btn("𝘼𝙙𝙙 𝘾𝙧𝙚𝙙𝙞𝙩𝙨", callback_data="admin_help_addcr", color="green", icon="5260294334619042015"),
            _btn("𝘽𝙧𝙤𝙖𝙙𝙘𝙖𝙨𝙩", callback_data="admin_help_bc", color="red", icon="5260294334619042015"),
        ],
        [
            _btn("𝙐𝙨𝙚𝙧𝙨", callback_data="admin_help_users", color="blue", icon="5854899611180736052"),
            _btn("𝘾𝙢𝙙𝙨 𝙇𝙞𝙨𝙩", callback_data="admin_help_cmds", color="blue", icon="5854899611180736052"),
        ],
        [
            _btn("🔙 𝘽𝙖𝙘𝙠", callback_data="menu_back_start", color="red", icon="5017122105011995219"),
        ],
    ])
    try:
        await q.edit_message_caption(caption=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception:
        try:
            await q.edit_message_text(text=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        except Exception:
            await context.bot.send_message(chat_id=user.id, text=text, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def admin_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = update.effective_user
    if user.id != OWNER_ID and user.id not in ADMIN_IDS:
        await q.answer("Owner / Admin only.", show_alert=True)
        return
    data = q.data or ""
    tips = {
        "admin_help_silver": "/give_silver <user_id>\n/gen_silver [count]",
        "admin_help_gold": "/give_gold <user_id>\n/gen_gold [count]",
        "admin_help_plat": "/give_platinum <user_id>\n/gen_platinum [count]",
        "admin_help_dia": "/give_diamond <user_id>\n/gen_diamond [count]",
        "admin_help_addcr": "/addcr <user_id> <credits>",
        "admin_help_bc": "/broadcast <message>",
        "admin_help_users": "/get_user or users list cmds",
        "admin_help_cmds": "Open /admin for full command dashboard",
    }
    msg = tips.get(data, "Unknown")
    await q.answer(msg, show_alert=True)
