# gates/sk_based_gates.py
# SK-Based commands
# /cc, /su, /sk

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
from utils.bullet import get_bullet_link, get_bullet2_link, get_developer_mention, get_user_mention
from force_join import force_join

logger = logging.getLogger(__name__)

# ===== CONFIG =====
SK_API_URL = "http:///skbased"
SK_KEY = "OAwc"
PK_KEY = "pA2nBJ7Cf6oOolU5OdQAyl6mBuxmkHVXXOZqctSEDmnVYDlvwycpFeF2qP6XnWaRj88NMZomtt0Kna2w2kr00Jh5aQWSs"
PROXY = "px023005.pointtoserver.com:10780:purevpn0s13918563:fV21iqc3trwCAs"

# ===== CARD PATTERN =====
CARD_PATTERN = re.compile(
    r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b"
)

# ===== MAIN SK PROCESSING FUNCTION =====
async def process_sk_charge(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str, amount: int, cmd_type: str):
    """Process SK-Based charge"""
    import time
    start_time = time.time()
    processing_msg = None

    try:
        user = update.effective_user

        if not await consume_credit(user.id):
            await update.message.reply_text("❌ You don't have enough credits left.")
            return

        parts = payload.split("|")
        if len(parts) != 4:
            await update.message.reply_text("❌ Invalid card format.")
            return

        cc, mm, yy, cvv = [p.strip() for p in parts]
        full_card = f"{cc}|{mm}|{yy}|{cvv}"
        escaped_card = escape(full_card)

        bullet_link_1 = get_bullet_link()
        bullet_link_2 = get_bullet2_link()

        processing_text = (
            f"<pre><code>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴⏳</code></pre>\n"
            f"<pre><code>{escaped_card}</code></pre>\n\n"
            f"<b>Gateway ↣ 𝐒𝐊-𝐁𝐚𝐬𝐞𝐝 ${amount}</b>\n"
        )

        processing_msg = await update.message.reply_text(processing_text, parse_mode=ParseMode.HTML)

        # API URL
        api_url = f"{SK_API_URL}?cc={full_card}&sk={SK_KEY}&pk={PK_KEY}&proxy={PROXY}"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=50) as resp:
                api_response = await resp.text()

        try:
            data = json.loads(api_response)
        except json.JSONDecodeError:
            await processing_msg.edit_text(
                f"❌ Invalid API response:\n<code>{escape(api_response[:500])}</code>",
                parse_mode=ParseMode.HTML
            )
            return

        # EXTRACT API RESPONSE DATA
        status = data.get("status", "UNKNOWN")
        error_msg = data.get("error", "")
        
        if error_msg and len(error_msg) > 60:
            error_display = error_msg[:57] + "..."
        else:
            error_display = error_msg

        # BIN lookup
        try:
            bin_number = cc[:6]
            bin_details = await get_bin_info(bin_number)
            brand = (bin_details.get("scheme") or "N/A").title()
            issuer = bin_details.get("bank") or "N/A"
            country_name = bin_details.get("country") or "Unknown"
            country_flag = bin_details.get("country_emoji", "")
        except Exception as e:
            brand = issuer = "N/A"
            country_name = "Unknown"
            country_flag = ""

        # User info
        user_clickable = get_user_mention(user)
        developer_clickable = get_developer_mention()

        # DETERMINE HEADER STATUS
        status_upper = str(status).upper()
        
        if "APPROVED" in status_upper or "CHARGED" in status_upper or "SUCCESS" in status_upper:
            header_status = "🔥 Charged"
        elif "DECLINED" in status_upper:
            header_status = "❌ Declined"
        elif "LIVE" in status_upper or "CCN" in status_upper:
            header_status = "✅ CCN Live"
        elif "INSUFFICIENT" in status_upper:
            header_status = "💸 Insufficient Funds"
        else:
            header_status = f"ℹ️ {status}"

        elapsed_time = round(time.time() - start_time, 2)

        # FINAL TEXT
        final_text = (
            f"<pre>{bullet_link_1} 𝙎𝙩𝙖𝙩𝙪𝙨 ↣ ({status})</pre>\n\n"   
            f"{bullet_link_1} 𝘾𝙖𝙧𝙙\n"
            f"⤷ <code>{escaped_card}</code>\n\n"      
            f"{bullet_link_1} 𝙍𝙚𝙨𝙥𝙤𝙣𝙨𝙚 ↣ <i>{escape(error_display) if error_display else 'No response'}</i>\n"
            f"{bullet_link_1} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↣ 𝐒𝐊-𝐁𝐚𝐬𝐞𝐝 ${amount}\n\n"
            
            f"<pre>"
            f"𝑩𝒓𝒂𝒏𝒅 ↬ {escape(brand)}\n"
            f"𝑩𝒂𝒏𝒌 ↬ {escape(issuer)}\n"
            f"𝑪𝒐𝒖𝒏𝒕𝒓𝒚 ↬ {escape(country_name)} {country_flag}"
            f"</pre>\n\n"
            
            f"{bullet_link_2} 𝘿𝙀𝙑 ↬ {developer_clickable}\n"
            f"{bullet_link_2} 𝘾𝙝𝙚𝙘𝙠 𝘽𝙮 ↣ {user_clickable}\n\n"
            
            f"𝙏𝙞𝙢𝙚 ↬ {elapsed_time}s"
        )

        await processing_msg.edit_text(final_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.exception(f"Error in processing SK charge")
        try:
            if processing_msg:
                await processing_msg.edit_text(
                    f"❌ Error: <code>{escape(str(e))}</code>",
                    parse_mode=ParseMode.HTML
                )
        except Exception:
            pass

# ===== SK-Based $1 Command (/cc) =====
@force_join
async def cc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """SK-Based $1 Charge"""
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
            "⚠️ Usage: <code>/cc card|mm|yy|cvv</code>\nOr reply to a message containing a card.", 
            parse_mode=ParseMode.HTML
        )
        return

    card, mm, yy, cvv = card_input
    mm = mm.zfill(2)
    yy = yy[-2:] if len(yy) == 4 else yy
    payload = f"{card}|{mm}|{yy}|{cvv}"

    await process_sk_charge(update, context, payload, 1, "cc")
