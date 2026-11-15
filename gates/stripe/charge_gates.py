# gates/stripe/charge_gates.py
import re
import asyncio
import aiohttp
import json
import time
import logging
from html import escape
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user, update_user
from bin import get_bin_info
from utils.decorators import enforce_cooldown
from utils.credits import consume_credit
from utils.helpers import escape_html
from utils.bullet import get_bullet_link, get_developer_mention, get_user_mention
from force_join import force_join

logger = logging.getLogger(__name__)

# ===== CONFIG =====
STRIPE_1_API = "ge&cc="

# === GROUP IDs ===
PUBLIC_GROUP_ID = -1003814496328

# ===== CARD PATTERN =====
CARD_PATTERN = re.compile(
    r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b"
)

# ===== HIT DETECTOR =====
async def send_hit(update: Update, context: ContextTypes.DEFAULT_TYPE, card: str, status: str, response: str, gateway: str):
    """Send Hit notification to public group and full card to private group."""
    user = update.effective_user
    user_mention = f'<a href="tg://user?id={user.id}">{escape_html(user.first_name or "User")}</a>'
    
    # ----- PUBLIC GROUP: Hit Detected -----
    bot_link = '<a href="https://t.me/chncexbot">DarkXChk</a>'
    hit_message = (
        f'<tg-emoji emoji-id="5219804923130038865">💎</tg-emoji> 𝑯𝑰𝑻 𝑫𝒆𝒕𝒆𝒄𝒕𝒆𝒅 <tg-emoji emoji-id="4916036072560919511">💎</tg-emoji>\n'
        f'━━━━━━━━\n'
        f'𝘜𝘴𝘦𝘳 <tg-emoji emoji-id="5125545114130712471">💎</tg-emoji> {user_mention}\n'
        f'𝘚𝘵𝘢𝘵𝘶𝘴 <tg-emoji emoji-id="5125583403764156460">💎</tg-emoji> {status}\n'
        f'𝘙𝘦𝘴𝘱𝘰𝘯𝘴𝘦 <tg-emoji emoji-id="5125545114130712471">💎</tg-emoji> {escape_html(response)}\n'
        f'𝘎𝘢𝘵𝘦𝘸𝘢𝙮 <tg-emoji emoji-id="5861552326543678329">💎</tg-emoji> {gateway}\n'
        f'━━━━━━━━\n'
        f'𝑯𝑰𝑻 𝑭𝒓𝒐𝒎 <tg-emoji emoji-id="5125546965261618614">💎</tg-emoji> {bot_link}'
    )
    try:
        await context.bot.send_message(chat_id=PUBLIC_GROUP_ID, text=hit_message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Failed to send Hit to public group: {e}")

# ===== STRIPE 1$ (/st) =====
async def process_st(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str):
    """Process Stripe 1$ charge"""
    start_time = time.time()

    try:
        user = update.effective_user

        if not await consume_credit(user.id):
            await update.message.reply_text("❌ You don't have enough credits left.")
            return

        parts = payload.split("|")
        if len(parts) != 4:
            await update.message.reply_text("❌ Invalid format.\nUse: /st 1234567812345678|12|2028|123")
            return

        cc, mm, yy, cvv = [p.strip() for p in parts]
        full_card = f"{cc}|{mm}|{yy}|{cvv}"
        escaped_card = escape_html(full_card)

        msg = await update.message.reply_text("💸")

        api_url = f"{STRIPE_1_API}{full_card}"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=50) as resp:
                api_response = await resp.text()

        try:
            data = json.loads(api_response)
        except json.JSONDecodeError:
            await msg.edit_text(f"❌ Invalid API response:\n<code>{escape_html(api_response[:500])}</code>")
            return

        response_data = data.get("response", "{}")
        
        try:
            nested_response = json.loads(response_data)
            error_message = nested_response.get("errors", "Unknown error")
        except:
            error_message = str(response_data)

        error_lower = str(error_message).lower()
        
        if "declined" in error_lower:
            header_status = "❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙"
            display_response = "Card was declined"
            is_approved = False
        elif "incorrect" in error_lower or "invalid" in error_lower:
            header_status = "❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙"
            display_response = "Invalid card details"
            is_approved = False
        elif "success" in error_lower or "approved" in error_lower:
            header_status = "✅ 𝘼𝙋𝙋𝙍𝙊𝙑𝙀𝘿"
            display_response = "Payment approved"
            is_approved = True
        else:
            header_status = "❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙"
            display_response = str(error_message)
            is_approved = False

        # ✅ Hit if approved
        if is_approved:
            await send_hit(update, context, full_card, "Approved", display_response, "Stripe 1$")

        try:
            bin_details = await get_bin_info(cc[:6])
            brand = (bin_details.get("scheme") or "N/A").upper()
            type_ = (bin_details.get("type") or "N/A").upper()
            level = (bin_details.get("brand") or "N/A").upper()
            issuer = bin_details.get("bank") or "N/A"
            country_name = bin_details.get("country") or "Unknown"
            country_flag = bin_details.get("country_emoji", "")
        except:
            brand = type_ = level = issuer = "N/A"
            country_name = "Unknown"
            country_flag = ""

        dev_mention = get_developer_mention()
        elapsed_time = round(time.time() - start_time, 2)

        final_text = (
            f"<b>{header_status}</b>\n\n"
            f"𝘾𝙖𝙧𝙙\n"
            f"⤷ <code>{escaped_card}</code>\n"
            f"𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↣ 𝙎𝙩𝙧𝙞𝙥𝙚 𝟭$\n"
            f"𝙍𝙚𝙨𝙥𝙤𝙣𝙨𝙚 ↣ <i><code>{escape_html(display_response)}</code></i>\n\n"
            f"<pre>"
            f"𝐈𝐧𝐟𝐨 ↣ {escape_html(brand)} - {escape_html(type_)} - {escape_html(level)}\n"
            f"𝐁𝐚𝐧𝐤 ↣ {escape_html(issuer)}\n"
            f"𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ↣ {escape_html(country_name)} {country_flag}"
            f"</pre>\n\n"
            f"𝘿𝙀𝙑 ↣ {dev_mention}\n"
            f"𝙏𝙞𝙢𝙚 ↣ {elapsed_time}s"
        )

        await msg.edit_text(final_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.exception("Error in /st")
        try:
            await update.message.reply_text(f"❌ Error: <code>{escape_html(str(e))}</code>")
        except:
            pass

@force_join
async def st_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await enforce_cooldown(user.id, update):
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
            "⚠️ Usage: <code>/st card|mm|yy|cvv</code>\nOr reply to a message containing a card.",
            parse_mode=ParseMode.HTML
        )
        return

    card, mm, yy, cvv = card_input
    mm = mm.zfill(2)
    yy = yy[-2:] if len(yy) == 4 else yy
    payload = f"{card}|{mm}|{yy}|{cvv}"

    asyncio.create_task(process_st(update, context, payload))

# ===== STRIPE 5$ (/st1) =====
async def process_st1(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str):
    """Process Stripe 5$ charge"""
    start_time = time.time()

    try:
        user = update.effective_user

        if not await consume_credit(user.id):
            await update.message.reply_text("❌ You don't have enough credits left.")
            return

        parts = payload.split("|")
        if len(parts) != 4:
            await update.message.reply_text("❌ Invalid format.\nUse: /st1 1234567812345678|12|2028|123")
            return

        cc, mm, yy, cvv = [p.strip() for p in parts]
        full_card = f"{cc}|{mm}|{yy}|{cvv}"
        escaped_card = escape_html(full_card)

        bullet_link = get_bullet_link()

        processing_text = (
            f"<pre><code>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴⏳</code></pre>\n"
            f"<pre><code>{escaped_card}</code></pre>\n\n"
            f"<b>Gateway ↣ 𝙎𝙩𝙧𝙞𝙥𝙚 𝟱$ 𝘾𝙝𝙖𝙧𝙜𝙚</b>\n"
        )

        processing_msg = await update.message.reply_text(processing_text, parse_mode=ParseMode.HTML)

        api_url = f"{STRIPE_1_API}{full_card}"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=50) as resp:
                api_response = await resp.text()

        try:
            data = json.loads(api_response)
        except json.JSONDecodeError:
            await processing_msg.edit_text(f"❌ Invalid API response:\n<code>{escape_html(api_response[:500])}</code>")
            return

        response_data = data.get("response", "{}")
        
        try:
            nested_response = json.loads(response_data)
            error_message = nested_response.get("errors", "Unknown error")
        except:
            error_message = str(response_data)

        error_lower = str(error_message).lower()
        
        if "declined" in error_lower:
            header_status = "❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙"
            display_response = "Card was declined"
            is_approved = False
        elif "incorrect" in error_lower or "invalid" in error_lower:
            header_status = "❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙"
            display_response = "Invalid card details"
            is_approved = False
        elif "success" in error_lower or "approved" in error_lower:
            header_status = "✅ 𝘼𝙋𝙋𝙍𝙊𝙑𝙀𝘿"
            display_response = "Payment approved"
            is_approved = True
        else:
            header_status = "❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙"
            display_response = str(error_message)
            is_approved = False

        # ✅ Hit if approved
        if is_approved:
            await send_hit(update, context, full_card, "Approved", display_response, "Stripe 5$")

        try:
            bin_details = await get_bin_info(cc[:6])
            brand = (bin_details.get("scheme") or "N/A").upper()
            type_ = (bin_details.get("type") or "N/A").upper()
            level = (bin_details.get("brand") or "N/A").upper()
            issuer = bin_details.get("bank") or "N/A"
            country_name = bin_details.get("country") or "Unknown"
            country_flag = bin_details.get("country_emoji", "")
        except:
            brand = type_ = level = issuer = "N/A"
            country_name = "Unknown"
            country_flag = ""

        dev_mention = get_developer_mention()
        elapsed_time = round(time.time() - start_time, 2)

        final_text = (
            f"<b>{header_status}</b>\n\n"
            f"𝘾𝙖𝙧𝙙\n"
            f"⤷ <code>{escaped_card}</code>\n"
            f"𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↣ 𝙎𝙩𝙧𝙞𝙥𝙚 𝟱$\n"
            f"𝙍𝙚𝙨𝙥𝙤𝙣𝙨𝙚 ↣ <i><code>{escape_html(display_response)}</code></i>\n\n"
            f"<pre>"
            f"𝐈𝐧𝐟𝐨 ↣ {escape_html(brand)} - {escape_html(type_)} - {escape_html(level)}\n"
            f"𝐁𝐚𝐧𝐤 ↣ {escape_html(issuer)}\n"
            f"𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ↣ {escape_html(country_name)} {country_flag}"
            f"</pre>\n\n"
            f"𝘿𝙀𝙑 ↣ {dev_mention}\n"
            f"𝙏𝙞𝙢𝙚 ↣ {elapsed_time}s"
        )

        await processing_msg.edit_text(final_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.exception("Error in /st1")
        try:
            await update.message.reply_text(f"❌ Error: <code>{escape_html(str(e))}</code>")
        except:
            pass

@force_join
async def st1_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not await enforce_cooldown(user.id, update):
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
            "⚠️ Usage: <code>/st1 card|mm|yy|cvv</code>\nOr reply to a message containing a card.",
            parse_mode=ParseMode.HTML
        )
        return

    card, mm, yy, cvv = card_input
    mm = mm.zfill(2)
    yy = yy[-2:] if len(yy) == 4 else yy
    payload = f"{card}|{mm}|{yy}|{cvv}"

    asyncio.create_task(process_st1(update, context, payload))
