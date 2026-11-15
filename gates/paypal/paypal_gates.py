# gates/paypal_gates.py
import re
import asyncio
import aiohttp
import json
import time
import logging
import html
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user, update_user
from bin import get_bin_info
from utils.decorators import enforce_cooldown
from utils.credits import consume_credit, is_unlimited
from utils.helpers import escape_html
from utils.bullet import get_bullet_link, get_bullet2_link, get_developer_mention, get_user_mention
from utils.cards_ui import result_buttons as _result_buttons
from config import OWNER_ID, ADMIN_IDS
from force_join import force_join


def _plan_badge(plan: str) -> str:
    p = (plan or "").lower()
    if "owner" in p: return "👑"
    if "admin" in p: return "🛡️"
    if "diamond" in p: return "🔷"
    if "platinum" in p: return "💎"
    if "gold" in p: return "🥇"
    if "silver" in p: return "🥈"
    if "trial" in p: return "🧪"
    if "prime" in p: return "🏆"
    if "premium" in p: return "✨"
    if "plus" in p: return "➕"
    return "🎟️"


async def _user_plan_label(user_id: int) -> str:
    if user_id == OWNER_ID:
        return f"Owner {_plan_badge('owner')}"
    if user_id in ADMIN_IDS:
        return f"Admin {_plan_badge('admin')}"
    try:
        data = await get_user(user_id) or {}
        plan = str(data.get("plan", "Free")) or "Free"
        return f"{plan} {_plan_badge(plan)}"
    except Exception:
        return f"Free {_plan_badge('free')}"

logger = logging.getLogger(__name__)


# === HIT DETECTION ===
_HIT_KEYWORDS = (
    "approved", "success", "charged", "thank you", "thanks for",
    "ccn live", "card added", "payment success", "transaction success",
    "transaction successful", "paid", "captured", "live", "hit",
    "completed", "order received", "order confirmed",
)


def _is_hit(status: str, response: str) -> bool:
    blob = f"{status or ''} {response or ''}".lower()
    if "decline" in blob or "do not honor" in blob or "insufficient" in blob:
        return False
    return any(k in blob for k in _HIT_KEYWORDS)

# === CONFIG ===
PP_1_API = "http://65.109.212.144:8080/check?cc="
PC_API = "http://162.217.248.95:7000/check?gate=paypal0.1&cc="

# === GROUP IDs ===
PUBLIC_GROUP_ID = -1003814496328

# === CARD PATTERN ===
CARD_PATTERN = re.compile(
    r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b"
)

# === PREMIUM EMOJI IDS ===
EMOJI_LOADING = '5195033767969839232'
EMOJI_SUCCESS = '5323307196807653127'
EMOJI_ERROR = '5323535839391653590'
EMOJI_DEAD = '5210952531676504517'

# ===== HIT  =====
_HIT_STATUS_EMOJI = {
    "CHARGED": ("5041796412954641308", "💎"),
    "APPROVED": ("5125343104638912114", "✅"),
    "DECLINED": ("5855085385696156087", "❌"),
}


def _hit_status_html(status: str) -> str:
    eid, fb = _HIT_STATUS_EMOJI.get((status or "").upper(), ("", ""))
    safe = html.escape(status)
    if eid:
        return f'{safe} <tg-emoji emoji-id="{eid}">{fb}</tg-emoji>'
    return safe


async def send_hit(update: Update, context: ContextTypes.DEFAULT_TYPE, card: str, status: str, response: str, gateway: str):
    """Send Hit notification to public group (with bot link preview as bottom box)."""
    user = update.effective_user
    user_mention = f'<a href="tg://user?id={user.id}">{html.escape(user.first_name or "User")}</a>'
    bot_link = '<a href="https://t.me/DarkCxC_Bot">𝘚𝘱𝘢𝘤𝘦 𝘊𝘩𝘬</a>'

    hit_message = (
        '<tg-emoji emoji-id="5219804923130038865">💎</tg-emoji> '
        '<b>𝑯𝑰𝑻 𝑫𝒆𝒕𝒆𝒄𝒕𝒆𝒅</b> '
        '<tg-emoji emoji-id="4916036072560919511">💎</tg-emoji>\n'
        '━━━━━━━━\n'
        f'𝘜𝘴𝘦𝘳 ➞ {user_mention}\n'
        f'𝘚𝘵𝘢𝘵𝘶𝘴 ➞ {_hit_status_html(status)}\n'
        f'𝘙𝘦𝘴𝘱𝘰𝘯𝘴𝘦 ➞ <code>{html.escape(response)}</code>\n'
        f'𝘎𝘢𝘵𝘦𝘸𝘢𝘺 ➞ {html.escape(gateway)}\n'
        '━━━━━━━━\n'
        f'𝑯𝑰𝑻 𝑭𝒓𝒐𝒎 ➞ {bot_link}'
    )
    try:
        await context.bot.send_message(
            chat_id=PUBLIC_GROUP_ID,
            text=hit_message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
    except Exception as e:
        logger.error(f"❌ Failed to send Hit to public group: {e}")

# ===== PAYPAL 1$ (/pp) =====
async def process_pp(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str):
    """Process PayPal 1$ charge"""
    start_time = time.time()
    msg = None

    try:
        user = update.effective_user

        processing_text = (
            f'<tg-emoji emoji-id="{EMOJI_LOADING}">⏳</tg-emoji> '
            '𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜 𝙋𝙖𝙮𝙋𝙖𝙡...\n'
            f'<code>{html.escape(payload)}</code>'
        )

        msg = await update.message.reply_text(processing_text, parse_mode=ParseMode.HTML)

        if not is_unlimited(user.id) and not await consume_credit(user.id):
            await msg.edit_text("❌ No credits left")
            return

        api_url = f"{PP_1_API}{payload}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=40) as resp:
                    if resp.status != 200:
                        error_text = (
                            f'<tg-emoji emoji-id="{EMOJI_ERROR}">❌</tg-emoji> '
                            '𝙂𝙖𝙩𝙚𝙬𝙖𝙮 𝙐𝙣𝙖𝙫𝙖𝙞𝙡𝙖𝙗𝙡𝙚\n'
                            'PayPal gateway is currently down.'
                        )
                        await msg.edit_text(error_text, parse_mode=ParseMode.HTML)
                        return

                    data = await resp.json()

        except asyncio.TimeoutError:
            timeout_text = (
                f'<tg-emoji emoji-id="{EMOJI_ERROR}">❌</tg-emoji> '
                '𝙍𝙚𝙦𝙪𝙚𝙨𝙩 𝙏𝙞𝙢𝙚𝙤𝙪𝙩\n'
                'Gateway is not responding.'
            )
            await msg.edit_text(timeout_text, parse_mode=ParseMode.HTML)
            return
        except Exception as e:
            error_text = (
                f'<tg-emoji emoji-id="{EMOJI_ERROR}">❌</tg-emoji> '
                f'𝘾𝙤𝙣𝙣𝙚𝙘𝙩𝙞𝙤𝙣 𝙀𝙧𝙧𝙤𝙧\n'
                f'<code>{html.escape(str(e)[:50])}</code>'
            )
            await msg.edit_text(error_text, parse_mode=ParseMode.HTML)
            return

        status = data.get("status", "unknown").upper()
        response_msg = data.get("response", "No response")

        is_approved = _is_hit(status, response_msg)
        if is_approved:
            status_text = '𝑨𝒑𝒑𝒓𝒐𝒗𝒆𝒅 <tg-emoji emoji-id="5870702999180942496">💎</tg-emoji>'
            # ✅ Send Hit
            await send_hit(update, context, payload, "Approved", response_msg, "PayPal 1$")
        else:
            status_text = '𝑫𝒆𝒄𝒍𝒊𝒏𝒆𝒅 <tg-emoji emoji-id="5855085385696156087">💎</tg-emoji>'

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

        elapsed = round(time.time() - start_time, 2)

        owner_mention = get_developer_mention()
        user_mention = get_user_mention(user)
        plan_label = await _user_plan_label(user.id)

        final_text = (
            f'[<tg-emoji emoji-id="5125437164422694571">💎</tg-emoji>] <b><i>Card</i></b> ➜ <code>{html.escape(payload)}</code>\n'
            f'━━━━━━━━━━━\n'
            f'[ﾒ] <b><i>Status</i></b> ➜ {status_text}\n'
            f'[ﾒ] <b><i>Response</i></b> ➜ <b><i>{html.escape(response_msg)}</i></b>\n'
            f'[ﾒ] <b><i>Gateway</i></b> ➜ <b><i>PayPal 1$</i></b>\n'
            f'━━━━━━━━━━━\n'
            f'[ﾒ] <b><i>Info</i></b> ➜ <b><i>{html.escape(brand)} - {html.escape(type_)} - {html.escape(level)}</i></b>\n'
            f'[ﾒ] <b><i>Bank</i></b> ➜ <b><i>{html.escape(issuer)}</i></b>\n'
            f'[ﾒ] <b><i>Country</i></b> ➜ <b><i>{html.escape(country)} {html.escape(flag)}</i></b>\n'
            f'━━━━━━━━━━━\n'
            f'[<tg-emoji emoji-id="5134452506935427991">💎</tg-emoji>] <b><i>Checked By</i></b> ➜ {user_mention} [{html.escape(plan_label)}]\n'
            f'[<tg-emoji emoji-id="5852557780262592341">💎</tg-emoji>] <b><i>Dev</i></b> ➜ {owner_mention}'
        )

        await msg.edit_text(final_text, parse_mode=ParseMode.HTML, reply_markup=_result_buttons())

    except Exception as e:
        logger.exception("Error in /pp")
        try:
            if msg:
                await msg.edit_text(f"❌ Error: {html.escape(str(e))}")
        except:
            pass

@force_join
async def pp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "⚠️ Usage: <code>/pp card|mm|yy|cvv</code>",
            parse_mode=ParseMode.HTML
        )
        return

    card, mm, yy, cvv = card_input
    mm = mm.zfill(2)
    yy = yy[-2:] if len(yy) == 4 else yy
    payload = f"{card}|{mm}|{yy}|{cvv}"

    asyncio.create_task(process_pp(update, context, payload))

# ===== PAYPAL 0.1$ (/pc) =====
async def process_pc(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str):
    """Process PayPal 0.1$ charge (same format as /pp)"""
    start_time = time.time()
    msg = None

    try:
        user = update.effective_user

        processing_text = (
            f'<tg-emoji emoji-id="{EMOJI_LOADING}">⏳</tg-emoji> '
            '𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜 𝙋𝙖𝙮𝙋𝙖𝙡 𝟬.𝟭$...\n'
            f'<code>{html.escape(payload)}</code>'
        )

        msg = await update.message.reply_text(processing_text, parse_mode=ParseMode.HTML)

        if not is_unlimited(user.id) and not await consume_credit(user.id):
            await msg.edit_text("❌ No credits left")
            return

        api_url = f"{PC_API}{payload}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=40) as resp:
                    if resp.status != 200:
                        error_text = (
                            f'<tg-emoji emoji-id="{EMOJI_ERROR}">❌</tg-emoji> '
                            '𝙂𝙖𝙩𝙚𝙬𝙖𝙮 𝙐𝙣𝙖𝙫𝙖𝙞𝙡𝙖𝙗𝙡𝙚\n'
                            'PayPal gateway is currently down.'
                        )
                        await msg.edit_text(error_text, parse_mode=ParseMode.HTML)
                        return

                    data = await resp.json()

        except asyncio.TimeoutError:
            timeout_text = (
                f'<tg-emoji emoji-id="{EMOJI_ERROR}">❌</tg-emoji> '
                '𝙍𝙚𝙦𝙪𝙚𝙨𝙩 𝙏𝙞𝙢𝙚𝙤𝙪𝙩\n'
                'Gateway is not responding.'
            )
            await msg.edit_text(timeout_text, parse_mode=ParseMode.HTML)
            return
        except Exception as e:
            error_text = (
                f'<tg-emoji emoji-id="{EMOJI_ERROR}">❌</tg-emoji> '
                f'𝘾𝙤𝙣𝙣𝙚𝙘𝙩𝙞𝙤𝙣 𝙀𝙧𝙧𝙤𝙧\n'
                f'<code>{html.escape(str(e)[:50])}</code>'
            )
            await msg.edit_text(error_text, parse_mode=ParseMode.HTML)
            return

        status = data.get("status", "unknown").upper()
        response_msg = data.get("response", "No response")

        is_approved = _is_hit(status, response_msg)
        if is_approved:
            status_text = '𝑨𝒑𝒑𝒓𝒐𝒗𝒆𝒅 <tg-emoji emoji-id="5870702999180942496">💎</tg-emoji>'
            # ✅ Send Hit 
            await send_hit(update, context, payload, "Approved", response_msg, "PayPal 0.1$")
        else:
            status_text = '𝑫𝒆𝒄𝒍𝒊𝒏𝒆𝒅 <tg-emoji emoji-id="5855085385696156087">💎</tg-emoji>'

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

        elapsed = round(time.time() - start_time, 2)

        owner_mention = get_developer_mention()
        user_mention = get_user_mention(user)
        plan_label = await _user_plan_label(user.id)

        final_text = (
            f'[<tg-emoji emoji-id="5125437164422694571">💎</tg-emoji>] <b><i>Card</i></b> ➜ <code>{html.escape(payload)}</code>\n'
            f'━━━━━━━━━━━\n'
            f'[ﾒ] <b><i>Status</i></b> ➜ {status_text}\n'
            f'[ﾒ] <b><i>Response</i></b> ➜ <b><i>{html.escape(response_msg)}</i></b>\n'
            f'[ﾒ] <b><i>Gateway</i></b> ➜ <b><i>PayPal 0.1$</i></b>\n'
            f'━━━━━━━━━━━\n'
            f'[ﾒ] <b><i>Info</i></b> ➜ <b><i>{html.escape(brand)} - {html.escape(type_)} - {html.escape(level)}</i></b>\n'
            f'[ﾒ] <b><i>Bank</i></b> ➜ <b><i>{html.escape(issuer)}</i></b>\n'
            f'[ﾒ] <b><i>Country</i></b> ➜ <b><i>{html.escape(country)} {html.escape(flag)}</i></b>\n'
            f'━━━━━━━━━━━\n'
            f'[<tg-emoji emoji-id="5134452506935427991">💎</tg-emoji>] <b><i>Checked By</i></b> ➜ {user_mention} [{html.escape(plan_label)}]\n'
            f'[<tg-emoji emoji-id="5852557780262592341">💎</tg-emoji>] <b><i>Dev</i></b> ➜ {owner_mention}'
        )

        await msg.edit_text(final_text, parse_mode=ParseMode.HTML, reply_markup=_result_buttons())

    except Exception as e:
        logger.exception("Error in /pc")
        try:
            if msg:
                await msg.edit_text(f"❌ Error: {html.escape(str(e))}")
        except:
            pass

@force_join
async def pc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            "⚠️ Usage: <code>/pc card|mm|yy|cvv</code>",
            parse_mode=ParseMode.HTML
        )
        return

    card, mm, yy, cvv = card_input
    mm = mm.zfill(2)
    yy = yy[-2:] if len(yy) == 4 else yy
    payload = f"{card}|{mm}|{yy}|{cvv}"

    asyncio.create_task(process_pc(update, context, payload))
