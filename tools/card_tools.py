# tools/card_tools.py - Without gen command
import re
import random
import io
import aiohttp
import asyncio
import time
import html
from datetime import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user, update_user
from bin import get_bin_info
from utils.decorators import enforce_cooldown
from utils.credits import consume_credit
from utils.helpers import luhn_checksum, escape_html, extract_cards_from_text
from utils.bullet import get_bullet_link, get_bullet2_link, get_developer_mention, get_user_mention
from force_join import force_join

# ===== /bin COMMAND =====
async def bin_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Performs a BIN lookup and shows full info."""
    user = update.effective_user

    bullet_link = get_bullet_link()
    developer_clickable = get_developer_mention()

    bin_input = None
    if context.args:
        bin_input = context.args[0]
    elif update.effective_message and update.effective_message.text:
        parts = update.effective_message.text.split(maxsplit=1)
        if len(parts) > 1:
            bin_input = parts[1]

    if not bin_input or not bin_input.isdigit() or len(bin_input) < 6:
        return await update.effective_message.reply_text(
            "❌ Please provide a valid 6-digit BIN. Usage: /bin [bin]",
            parse_mode="HTML"
        )

    bin_number = bin_input[:6]

    try:
        bin_details = await get_bin_info(bin_number)

        brand = (bin_details.get("scheme") or "N/A").upper()
        type_ = (bin_details.get("type") or "N/A").upper()
        level = (bin_details.get("brand") or "N/A").upper()
        issuer = bin_details.get("bank") or "N/A"
        country_name = bin_details.get("country") or "N/A"
        country_flag = bin_details.get("country_emoji", "")
        card_length = bin_details.get("length", "N/A")

        bin_info_box = (
            f"✦━━━[ <b>𝐁𝐈𝐍 𝐈𝐍𝐅𝐎</b> ]━━━✦\n"
            f"{bullet_link} <b>BIN</b> ➳ <code>{bin_number}</code>\n"
            f"{bullet_link} <b>Info</b> ➳ <code>{escape_html(brand)} - {escape_html(type_)} - {escape_html(level)}</code>\n"
            f"{bullet_link} <b>Issuer/Bank</b> ➳ <code>{escape_html(issuer)}</code>\n"
            f"{bullet_link} <b>Country</b> ➳ <code>{escape_html(country_name)} {country_flag}</code>\n"
            f"{bullet_link} <b>Length</b> ➳ <code>{card_length}</code>\n"
            f"{bullet_link} <b>Requested By</b> ➳ {get_user_mention(user)}\n"
            f"{bullet_link} <b>Bot By</b> ➳ {developer_clickable}\n"
        )

        await update.effective_message.reply_text(
            bin_info_box,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    except Exception as e:
        await update.effective_message.reply_text(
            f"❌ Error fetching BIN info: {escape_html(str(e))}",
            parse_mode="HTML"
        )

# ===== /vbv COMMAND =====
async def vbv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check 3D Secure / VBV status for a card."""
    user = update.effective_user
    user_id = user.id

    if not await consume_credit(user_id):
        await update.message.reply_text("❌ You don't have enough credits to use /vbv.")
        return

    card_data = None
    raw_text = ""

    if context.args:
        raw_text = " ".join(context.args).strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        raw_text = update.message.reply_to_message.text.strip()

    if raw_text:
        match = re.search(r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b", raw_text)
        if match:
            cc, mm, yy, cvv = match.groups()
            mm = mm.zfill(2)
            yy = yy[-2:] if len(yy) == 4 else yy
            card_data = f"{cc}|{mm}|{yy}|{cvv}"

    if not card_data:
        await update.message.reply_text(
            "⚠️ Usage:\n"
            "<code>/vbv 4111111111111111|07|2027|123</code>\n"
            "Or reply to a message containing a card.",
            parse_mode=ParseMode.HTML
        )
        return

    processing_text = (
        f"<pre><code>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴⏳</code></pre>\n"
        f"<pre><code>𝗩𝗕𝗩 𝗖𝗵𝗲𝗰𝗸 𝗢𝗻𝗴𝗼𝗶𝗻𝗴</code></pre>\n"
        f"𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↣ 𝟯𝐃 𝗦𝗲𝗰𝘂𝗿𝗲 / 𝗩𝗕𝗩 𝗟𝗼𝗼𝗸𝘂𝗽\n"
    )

    msg = await update.message.reply_text(
        processing_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )

    asyncio.create_task(run_vbv_check(msg, update, card_data))

async def run_vbv_check(msg, update, card_data: str):
    """Background VBV check"""
    import time
    start_time = time.time()
    
    try:
        cc, mes, ano, cvv = card_data.split("|")
    except ValueError:
        await msg.edit_text("❌ Invalid format. Use: /vbv 4111111111111111|07|2027|123")
        return

    bin_number = cc[:6]
    api_url = f"https://api.voidapi.xyz/v2/vbv?key=VDX-SHA2X-NZ0RS-O7HAM&card={card_data}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=50) as resp:
                if resp.status != 200:
                    await msg.edit_text(f"❌ API Error (Status {resp.status}). Try again later.")
                    return
                vbv_data = await resp.json(content_type=None)
    except asyncio.TimeoutError:
        await msg.edit_text("❌ API request failed: Timed out ⏳")
        return
    except Exception as e:
        await msg.edit_text(f"❌ API request failed: {e}")
        return

    success = vbv_data.get("success", False)
    data = vbv_data.get("data", {})
    
    vbv_status = data.get("status", "").lower()
    
    vbv_pass_statuses = [
        "authenticate_successful",
        "authenticate_attempt_successful",
        "authenticate_passed",
        "authenticate_approved",
        "authenticate_verified"
    ]
    
    if vbv_status in vbv_pass_statuses:
        header_status = "𝙑𝘽𝙑 𝙋𝙖𝙨𝙨 ✅"
        response_text = vbv_status.replace("_", " ").title()
    elif vbv_status == "challenge_required":
        header_status = "✖️ 3𝘿𝙎 𝙍𝙚𝙦𝙪𝙞𝙧𝙚𝙙"
        response_text = "3D Secure Required"
    else:
        header_status = "✖️ 3𝘿𝙎 𝙍𝙚𝙦𝙪𝙞𝙧𝙚𝙙"
        response_text = vbv_status.replace("_", " ").title() if vbv_status else "Unknown"

    try:
        bin_details = await get_bin_info(bin_number)
        brand = (bin_details.get("scheme") or "N/A").upper()
        type_ = (bin_details.get("type") or "N/A").upper()
        level = (bin_details.get("brand") or "N/A").upper()
        issuer = bin_details.get("bank") or "N/A"
        country_name = bin_details.get("country") or "Unknown"
        country_flag = bin_details.get("country_emoji", "")
    except Exception:
        brand = type_ = level = issuer = "N/A"
        country_name = "Unknown"
        country_flag = ""

    user = update.effective_user
    bullet_link_1 = get_bullet_link()
    bullet_link_2 = get_bullet2_link()
    developer_clickable = get_developer_mention()
    user_clickable = get_user_mention(user)

    elapsed_time = round(time.time() - start_time, 2)
    escaped_card = escape_html(card_data)

    final_text = (
        f"<b>{header_status}</b>\n\n"
        f"{bullet_link_1} 𝘾𝙖𝙧𝙙\n"
        f"⤷ <code>{escaped_card}</code>\n\n"
        f"{bullet_link_1} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↣ 𝙑𝘽𝙑 𝙇𝙤𝙤𝙠 𝙐𝙥\n"
        f"{bullet_link_1} 𝙍𝙚𝙨𝙥𝙤𝙣𝙨𝙚 ↣ <code>{escape_html(response_text)}</code>\n\n"
        f"<pre>"
        f"𝐈𝐧𝐟𝐨 ↣ {escape_html(brand)} - {escape_html(type_)} - {escape_html(level)}\n"
        f"𝐁𝐚𝐧𝐤 ↣ {escape_html(issuer)}\n"
        f"𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ↣ {escape_html(country_name)} {country_flag}"
        f"</pre>\n\n"
        f"{bullet_link_2} 𝘿𝙀𝙑 ↣ {developer_clickable}\n"
        f"{bullet_link_2} 𝘾𝙝𝙚𝙘𝙠 𝘽𝙮 ↣ {user_clickable}\n\n"
        f"𝙏𝙞𝙢𝙚 ↣ {elapsed_time}𝙨"
    )

    await msg.edit_text(final_text, parse_mode="HTML", disable_web_page_preview=True)
