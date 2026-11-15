# gates/stripe/mass_gates.py
# Mass gateway commands
# /mass, /masspp, /msh, /chktxt

import asyncio
import aiohttp
import json
import re
import time
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user, update_user

logger = logging.getLogger(__name__)

# Import from other gate files (UPDATED PATHS)
from gates.paypal.masspp import masspp_command, register_masspp_handlers
from gates.shopify.msh import msh_command, register_msh_handlers
from gates.stripe.mstripe import chktxt_command, register_mstripe_callbacks

# ===== MASS STRIPE AUTH (/mass) =====
# Card regex
CARD_REGEX = re.compile(r"\b(\d{12,19})\|(\d{1,2})\|(\d{2,4})\|(\d{3,4})\b")

# Settings
API_URL_TEMPLATE = "cc="
CONCURRENCY = 3
RATE_LIMIT_SECONDS = 5
user_last_command_time = {}
BULLET_GROUP_LINK = "https://t.me/chargegod"

# Credit handler
async def deduct_credit(user_id: int) -> bool:
    try:
        user_data = await get_user(user_id)
        if user_data and user_data.get("credits", 0) > 0:
            await update_user(user_id, credits=user_data["credits"] - 1)
            return True
    except Exception as e:
        logging.error(f"[deduct_credit] Error for user {user_id}: {e}")
    return False

# Extract cards
def extract_cards(text: str) -> list[str]:
    return [match.group(0) for match in re.finditer(CARD_REGEX, text)]

# Escape for MarkdownV2
def mdv2_escape(text: str) -> str:
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in escape_chars else c for c in str(text))

# Single card check
async def check_single_card(session, card: str):
    try:
        async with session.get(API_URL_TEMPLATE + card, timeout=60) as resp:
            if resp.status != 200:
                return f"`{mdv2_escape(card)}`\n𝗦𝘁𝗮𝘁𝘂𝘀 ↣ ❌ _HTTP Error {resp.status}_", "error"
            
            data = await resp.json()
            status = str(data.get("status") or "unknown").strip().lower()
            response = str(data.get("response") or "No response").strip()

            card_md = mdv2_escape(card)
            response_md = mdv2_escape(response)

            if "approved" in status:
                return f"`{card_md}`\n𝗦𝘁𝗮𝘁𝘂𝘀 ↣ ✅ _{response_md}_", "approved"
            elif "declined" in status:
                return f"`{card_md}`\n𝗦𝘁𝗮𝘁𝘂𝘀 ↣ ❌ _{response_md}_", "declined"
            else:
                return f"`{card_md}`\n𝗦𝘁𝗮𝘁𝘂𝘀 ↣ ⚠️ _{response_md}_", "error"

    except Exception as e:
        return f"`{mdv2_escape(card)}`\n𝗦𝘁𝗮𝘁𝘂𝘀 ↣ ❌ _{mdv2_escape(str(e))}_", "error"

# Run mass checker
async def run_mass_checker(msg_obj, cards, user):
    total = len(cards)
    counters = {"checked": 0, "approved": 0, "declined": 0, "error": 0}
    results = []
    start_time = time.time()

    bullet = "⊀"
    bullet_link = f"[{mdv2_escape(bullet)}]({BULLET_GROUP_LINK})"
    gateway_text = mdv2_escape("𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ↣ #𝗠𝗮𝘀𝘀𝗦𝘁𝗿𝗶𝗽𝗲𝗔𝘂𝘁𝗵")
    status_text = mdv2_escape("𝗦𝘁𝗮𝘁𝘂𝘀 ↣ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 🔎...")

    initial_text = (
        f"```𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴⏳```\n"
        f"{bullet_link} {gateway_text}\n"
        f"{bullet_link} {status_text}"
    )

    try:
        msg_obj = await msg_obj.reply_text(
            initial_text,
            parse_mode="MarkdownV2",
            disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"[init] {e}")
        return

    queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async with aiohttp.ClientSession() as session:
        async def worker(card):
            async with semaphore:
                result_text, status = await check_single_card(session, card)
                counters["checked"] += 1
                counters[status] += 1
                await queue.put(result_text)

        tasks = [asyncio.create_task(worker(c)) for c in cards]

        async def consumer():
            update_counter = 0
            while True:
                try:
                    result = await asyncio.wait_for(queue.get(), timeout=2)
                except asyncio.TimeoutError:
                    if all(t.done() for t in tasks):
                        break
                    continue

                results.append(result)
                update_counter += 1
                
                if update_counter % 3 != 0 and not (all(t.done() for t in tasks)):
                    continue
                    
                elapsed = round(time.time() - start_time, 2)
                
                header = (
                    f"{bullet_link} {gateway_text}\n"
                    f"{bullet_link} 𝗧𝗼𝘁𝗮𝗹 ↣ {mdv2_escape(str(counters['checked']))}/{mdv2_escape(str(total))}\n"
                    f"{bullet_link} 𝗔𝗽𝗽𝗿𝗼𝘃𝗲𝗱 ↣ {mdv2_escape(str(counters['approved']))}\n"
                    f"{bullet_link} 𝗗𝗲𝗰𝗹𝗶𝗻𝗲𝗱 ↣ {mdv2_escape(str(counters['declined']))}\n"
                    f"{bullet_link} 𝗘𝗿𝗿𝗼𝗿 ↣ {mdv2_escape(str(counters['error']))}\n"
                    f"{bullet_link} 𝗧𝗶𝗺𝗲 ↣ {mdv2_escape(str(elapsed))} Sec\n"
                    "──────── ⸙ ─────────"
                )
                content = header + "\n" + "\n──────── ⸙ ─────────\n".join(results[-10:])

                try:
                    await msg_obj.edit_text(
                        content,
                        parse_mode="MarkdownV2",
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logging.error(f"[update] {e}")

                await asyncio.sleep(1)

        consumer_task = asyncio.create_task(consumer())
        await asyncio.gather(*tasks)
        await consumer_task

# Mass command handler
async def mass_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    current_time = time.time()

    if user_id in user_last_command_time:
        elapsed = current_time - user_last_command_time[user_id]
        if elapsed < RATE_LIMIT_SECONDS:
            remaining = round(RATE_LIMIT_SECONDS - elapsed, 2)
            await update.message.reply_text(
                f"⚠️ Please wait <b>{remaining}</b>s before using /mass again.",
                parse_mode="HTML"
            )
            return

    if not await deduct_credit(user_id):
        await update.message.reply_text("❌ You have no credits.", parse_mode="HTML")
        return

    user_last_command_time[user_id] = current_time

    text_source = ""
    if context.args:
        text_source = " ".join(context.args)
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        text_source = update.message.reply_to_message.text

    cards = extract_cards(text_source)

    if not cards:
        await update.message.reply_text("🚫 No valid cards found.", parse_mode="HTML")
        return

    if len(cards) > 50:
        await update.message.reply_text(
            "⚠️ Max 50 cards allowed. Only first 50 will be processed.",
            parse_mode="HTML"
        )
        cards = cards[:50]

    # ❌ हटाया गया: initial_text को भेजना
    # अब सीधे run_mass_checker को update.message भेजेंगे
    asyncio.create_task(run_mass_checker(update.message, cards, user))

# gates/mass_gates.py ke end mein yeh line confirm karo
__all__ = [
    'mass_handler',
    'masspp_command',
    'msh_command', 
    'chktxt_command',
    'register_masspp_handlers',
    'register_msh_handlers',
    'register_mstripe_callbacks'
]