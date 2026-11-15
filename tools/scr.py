# tools/scr.py
import re
import os
import asyncio
import logging
import aiofiles
import time
from html import escape
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import API_ID, API_HASH, ADMIN_LIMIT, ADMIN_IDS, DEFAULT_LIMIT

from pyrogram import Client as PyroClient
from pyrogram.errors import (
    PeerIdInvalid, ChannelInvalid, ChannelPrivate,
    UsernameNotOccupied, InviteHashExpired, UserAlreadyParticipant, FloodWait,
)

logging.basicConfig(level=logging.WARNING)
for noisy in (
    "httpx",
    "pyrogram",
    "pyrogram.session.session",
    "pyrogram.connection",
    "pyrogram.client",
    "pyrogram.dispatcher",
    "pyrogram.methods.advanced.resolve_peer",
):
    logging.getLogger(noisy).setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

pyro_user = None
user_last_command = {}
_cooldown_lock = asyncio.Lock()
_executor = ThreadPoolExecutor(max_workers=8)


# ═══════════════════════════════════════
#  ASYNCIO ERROR FILTER — silence harmless Pyrogram peer-resolve noise
# ═══════════════════════════════════════
# Pyrogram's update dispatcher spawns a Task per incoming server update, and
# when it tries to resolve a chat the session hasn't cached yet it raises
# ``ValueError: Peer id invalid: -100...`` (or ``KeyError: 'ID not found'``).
# The dispatcher never awaits the task, so asyncio logs a multi-line "Task
# exception was never retrieved" stack on stderr. The bot's actual command
# handling is unaffected — these are background updates the bot doesn't
# even need. We swallow the noise via the loop exception handler.
_PEER_RESOLVE_HINTS = (
    "Peer id invalid",
    "ID not found",
)


def _silence_peer_resolve_errors(loop, context):
    exc = context.get("exception")
    msg = context.get("message", "")
    if exc is not None:
        text = f"{type(exc).__name__}: {exc}"
        if any(h in text for h in _PEER_RESOLVE_HINTS):
            return
    if any(h in msg for h in _PEER_RESOLVE_HINTS):
        return
    loop.default_exception_handler(context)


# ═══════════════════════════════════════
#  SESSION
# ═══════════════════════════════════════
async def initialize_scraper():
    global pyro_user
    try:
        try:
            asyncio.get_event_loop().set_exception_handler(_silence_peer_resolve_errors)
        except Exception:
            pass

        if not API_ID or not API_HASH:
            return False
        pyro_user = PyroClient(
            name="scraper_session",
            api_id=API_ID,
            api_hash=API_HASH,
            workers=20,
            no_updates=True,
            sleep_threshold=60,
            max_concurrent_transmissions=50,
        )
        await pyro_user.start()
        me = await pyro_user.get_me()
        logger.warning(f"[SCR] Started as: {me.first_name}")
        return True
    except Exception as e:
        logger.error(f"[SCR] Init failed: {e}")
        return False


# ═══════════════════════════════════════
#  COOLDOWN
# ═══════════════════════════════════════
async def enforce_cooldown(user_id: int, update: Update, cooldown_seconds: int = 5) -> bool:
    now = time.time()
    async with _cooldown_lock:
        last = user_last_command.get(user_id, 0)
        if now - last < cooldown_seconds:
            await update.message.reply_text(
                f"⏳ Wait {int(cooldown_seconds - (now - last))}s.",
                parse_mode=ParseMode.HTML
            )
            return False
        user_last_command[user_id] = now
        return True


# ═══════════════════════════════════════
#  DB HELPERS
# ═══════════════════════════════════════
async def get_user(user_id):
    try:
        from db import get_user as _g
        return await _g(user_id)
    except Exception:
        return None

async def update_user(user_id, **kwargs):
    try:
        from db import update_user as _u
        await _u(user_id, **kwargs)
    except Exception:
        pass


# ═══════════════════════════════════════
#  CARD PARSING
# ═══════════════════════════════════════
def is_card_expired(mm: str, yy: str) -> bool:
    try:
        month, year = int(mm), int(yy)
        if len(yy) == 2:
            year += 2000
        now = datetime.now()
        return year < now.year or (year == now.year and month < now.month)
    except Exception:
        return True


def normalize_card(line: str):
    line = re.sub(r'[\n\r|/\-]', ' ', line)
    nums = re.findall(r'\d+', line)
    cc = mm = yy = cvv = ''
    for n in nums:
        ln = len(n)
        if 13 <= ln <= 19 and not cc:
            cc = n
        elif ln == 4 and n.startswith('20') and not yy:
            yy = n
        elif ln == 2 and not mm:
            v = int(n)
            if 1 <= v <= 12:
                mm = n.zfill(2)
        elif ln == 2 and mm and not yy:
            yy = '20' + n
        elif ln in (3, 4) and not cvv:
            cvv = n
    if cc and mm and yy and cvv:
        if len(yy) == 2:
            yy = '20' + yy
        return f"{cc}|{mm}|{yy}|{cvv}"
    return None


_CARD_RE = [
    re.compile(r'\b(\d{13,19})[|\s/\-](\d{1,2})[|\s/\-](\d{2,4})[|\s/\-](\d{3,4})\b'),
    re.compile(r'\b(\d{15,16})(\d{2})(20\d{2})(\d{3,4})\b'),
]


def parse_cards_batch(texts: list, bin_filter=None, bank_filter=None) -> list:
    found, seen = [], set()
    for text in texts:
        if not text:
            continue
        if bank_filter and bank_filter.lower() not in text.lower():
            continue
        for line in text.split('\n'):
            card = normalize_card(line)
            if card and card not in seen:
                cc = card.split('|')[0]
                if not (bin_filter and not cc.startswith(bin_filter[:6])):
                    found.append(card)
                    seen.add(card)
                continue
            for pat in _CARD_RE:
                for m in pat.findall(line):
                    if len(m) != 4:
                        continue
                    cc, mm, yy, cvv = m
                    if len(yy) == 2:
                        yy = '20' + yy
                    mm = mm.zfill(2)
                    s = f"{cc}|{mm}|{yy}|{cvv}"
                    if s not in seen:
                        if bin_filter and not cc.startswith(bin_filter[:6]):
                            continue
                        found.append(s)
                        seen.add(s)
    return found


def remove_duplicates_and_expired(cards: list) -> tuple:
    unique, seen = [], set()
    dups = expired = 0
    for card in cards:
        if card in seen:
            dups += 1
            continue
        seen.add(card)
        parts = card.split('|')
        if len(parts) == 4 and not is_card_expired(parts[1], parts[2]):
            unique.append(card)
        else:
            expired += 1
    return unique, dups, expired


# ═══════════════════════════════════════
#  DIALOG CACHE WARMUP + SEARCH
#
#  ROOT CAUSE OF BUG:
#  Pyrogram "PeerIdInvalid" ka matlab ye hai
#  ke scraper session ke SQLite cache me ye
#  peer stored nahi hai. Chahe scraper member
#  ho — agar us chat se koi message receive
#  nahi hua (no_updates=True) toh cache empty.
#
#  FIX: get_dialogs() se cache warm karo,
#  phir get_chat() dobara try karo.
# ═══════════════════════════════════════
async def _warm_cache_and_find(client, abs_cid: int):
    """
    get_dialogs se cache warm karo aur target chat dhundho.
    abs_cid = absolute value of the chat ID.
    """
    found_chat = None
    try:
        async for dialog in client.get_dialogs():
            c = dialog.chat
            c_abs = abs(c.id)
            # Exact ID match (any sign)
            if c_abs == abs_cid:
                found_chat = c
                break
            # Suffix match — e.g. 1003211028912 ends with 3211028912
            if str(c_abs).endswith(str(abs_cid)) or str(abs_cid).endswith(str(c_abs)):
                found_chat = c
                break
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception as e:
        logger.warning(f"[SCR] cache warm failed: {e}")
    return found_chat


# ═══════════════════════════════════════
#  CHAT RESOLUTION
# ═══════════════════════════════════════
async def resolve_chat_safe(client, raw: str):
    """
    Handles:
      • -1001003211028912  (supergroup/channel with -100 prefix)
      • -1003211028912     (negative group ID)
      •  1003211028912     (positive ID)
      • @username / username
      • https://t.me/username
      • https://t.me/+HASH  /  https://t.me/joinchat/HASH
    """
    s = raw.strip()

    # ── 1. Numeric ID ──────────────────────────────────────────────
    if re.match(r'^-?\d+$', s):
        cid     = int(s)
        abs_cid = abs(cid)

        # Always build the proper -100XXXXXXXXXX supergroup ID
        # regardless of what was given (-100X, -X, or +X)
        canonical = int(f"-100{abs_cid}")

        # Try order: canonical → as-is → positive
        candidates = []
        seen_ids = set()
        for x in [canonical, cid, abs_cid]:
            if x not in seen_ids:
                seen_ids.add(x)
                candidates.append(x)

        # --- Pass 1: direct get_chat for each candidate ---
        last_err = None
        need_join = False
        for attempt in candidates:
            try:
                chat = await client.get_chat(attempt)
                return chat, None
            except (ChannelPrivate, ChannelInvalid):
                need_join = True
                last_err = attempt
                continue
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                try:
                    return await client.get_chat(attempt), None
                except Exception as ex:
                    last_err = str(ex)
                    continue
            except (PeerIdInvalid, KeyError, ValueError):
                # Cache miss — will handle in Pass 2
                last_err = f"cache miss for {attempt}"
                continue
            except Exception as e:
                last_err = str(e)
                continue

        # --- Pass 2: cache miss → warm via get_dialogs then retry ---
        chat = await _warm_cache_and_find(client, abs_cid)
        if chat:
            # Cache is now warm — retry get_chat with the real ID
            try:
                refreshed = await client.get_chat(chat.id)
                return refreshed, None
            except Exception:
                return chat, None  # return dialog result directly

        # --- Pass 3: private chat — try joining ---
        if need_join or isinstance(last_err, int):
            join_target = last_err if isinstance(last_err, int) else canonical
            try:
                chat = await client.join_chat(join_target)
                return chat, None
            except UserAlreadyParticipant:
                # Already member but cache miss — warm and retry
                chat = await _warm_cache_and_find(client, abs_cid)
                if chat:
                    return chat, None
                return None, (
                    f"⚠️ Scraper already is a member but can't fetch chat.\n"
                    f"<b>Fix:</b> Restart the bot once to rebuild Pyrogram cache,\n"
                    f"or use <code>@username</code> / invite link instead of numeric ID."
                )
            except FloodWait as e:
                return None, f"⏳ FloodWait {e.value}s — baad me try karo."
            except Exception as je:
                return None, f"Join failed: {je}"

        return None, (
            f"❌ ID <code>{s}</code> resolve nahi hua.\n\n"
            f"<b>Possible reasons:</b>\n"
            f"• Scraper member nahi hai — invite link bhejo\n"
            f"• Public channel hai toh <code>@username</code> use karo\n"
            f"• Bot restart karo (Pyrogram cache rebuild hoga)"
        )

    # ── 2. Private invite link ─────────────────────────────────────
    if re.search(r't(?:elegram)?\.me/(?:\+|joinchat/)', s):
        try:
            chat = await client.join_chat(s)
            return chat, None
        except UserAlreadyParticipant:
            try:
                chat = await client.get_chat(s)
                return chat, None
            except Exception:
                pass
            # Fallback: latest dialog
            try:
                async for dialog in client.get_dialogs(limit=20):
                    return dialog.chat, None
            except Exception:
                pass
            return None, "Already member — numeric ID ya @username do."
        except InviteHashExpired:
            return None, "Invite link expire ho gaya."
        except FloodWait as e:
            return None, f"⏳ FloodWait {e.value}s."
        except Exception as e:
            return None, f"Invite se join nahi hua: {e}"

    # ── 3. t.me/username link → extract username ───────────────────
    if 't.me/' in s or 'telegram.me/' in s:
        s = '@' + s.rstrip('/').split('/')[-1]

    # ── 4. Ensure @ prefix ─────────────────────────────────────────
    if not s.startswith('@'):
        s = f"@{s}"

    # ── 5. Username resolution ─────────────────────────────────────
    try:
        chat = await client.get_chat(s)
        return chat, None
    except UsernameNotOccupied:
        return None, f"{s} exist nahi karta."
    except (ChannelPrivate, ChannelInvalid):
        try:
            chat = await client.join_chat(s)
            return chat, None
        except UserAlreadyParticipant:
            try:
                return await client.get_chat(s), None
            except Exception:
                pass
            return None, f"{s} already joined but fetch failed — ID use karo."
        except FloodWait as e:
            return None, f"⏳ FloodWait {e.value}s."
        except Exception as e:
            return None, f"{s} private hai, join fail: {e}"
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
        try:
            return await client.get_chat(s), None
        except Exception as ex:
            return None, f"FloodWait ke baad bhi fail: {ex}"
    except PeerIdInvalid:
        return None, f"{s} invalid ya scraper ne kabhi nahi dekha."
    except Exception as e:
        return None, f"Error: {e}"


# ═══════════════════════════════════════
#  FAST SCRAPER
# ═══════════════════════════════════════
async def scrape_messages(client, chat_id: int, limit: int,
                           bin_filter=None, bank_filter=None) -> list:
    BATCH = 400
    SCAN  = limit * 60
    loop  = asyncio.get_event_loop()

    found, seen = [], set()
    batch, tasks = [], []

    async def flush(b):
        return await loop.run_in_executor(
            _executor, parse_cards_batch, b, bin_filter, bank_filter
        )

    def collect(results):
        for cards in results:
            for c in cards:
                if c not in seen and len(found) < limit:
                    seen.add(c)
                    found.append(c)

    try:
        async for msg in client.get_chat_history(chat_id, limit=SCAN):
            if len(found) >= limit:
                break
            text = msg.text or msg.caption
            if text:
                batch.append(text)
            if len(batch) >= BATCH:
                tasks.append(asyncio.create_task(flush(batch[:])))
                batch = []
                if len(tasks) >= 6:
                    collect(await asyncio.gather(*tasks))
                    tasks = []
                    if len(found) >= limit:
                        break
    except FloodWait as e:
        await asyncio.sleep(e.value + 2)
    except Exception as e:
        logger.error(f"[SCR] scrape_messages error: {e}")

    if batch:
        tasks.append(asyncio.create_task(flush(batch)))
    if tasks:
        collect(await asyncio.gather(*tasks))

    return found[:limit]


# ═══════════════════════════════════════
#  SEND RESULTS
# ═══════════════════════════════════════
async def send_scraped_results(update: Update, unique_cards, dup_count, expired_count,
                                source_name, bin_filter=None, bank_filter=None):
    if not unique_cards:
        await update.effective_message.reply_text(
            "<b>❌ 𝙉𝙤 𝘾𝙘 𝙁𝙤𝙪𝙣𝙙</b>\n\n"
            "No live cards found. Try a bigger limit or remove filters.",
            parse_mode=ParseMode.HTML
        )
        return

    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe      = "".join(c for c in source_name if c.isalnum() or c in (' ', '_')).strip()
    file_path = f"/tmp/DXC_{len(unique_cards)}_{safe}_{ts}.txt"

    async with aiofiles.open(file_path, 'w') as f:
        await f.write("\n".join(unique_cards))

    user      = update.effective_user
    user_link = f'<a href="tg://user?id={user.id}">{escape(user.first_name or "User")}</a>'

    cap = (
        f"💎 𝙎𝙥𝙖𝙘𝙚 𝘾𝙝𝙠 𝘾𝙘 𝙎𝙘𝙧𝙚𝙥𝙚𝙧 💸\n\n"
        f"☑️ <b>𝙎𝙘𝙧𝙖𝙥𝙥𝙚𝙙 𝙎𝙐𝘾𝘾𝙀𝙎𝙎𝙁𝙐𝙇𝙇𝙔</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧠 <b>𝙎𝙤𝙪𝙧𝙘𝙚 ↭</b> <code>{escape(source_name)}</code>\n"
        f"💀 <b>𝙏𝙤𝙩𝙖𝙡 𝘾𝙘 ↭</b> <code>{len(unique_cards)}</code>\n"
        f"🗑️ <b>𝘿𝙪𝙥𝙡𝙞𝙘𝙖𝙩𝙚𝙨 ↭</b> <code>{dup_count}</code>\n"
        f"⏳ <b>𝙀𝙭𝙥𝙞𝙧𝙚𝙙 ↭</b> <code>{expired_count}</code>\n"
    )
    if bin_filter:
        cap += f"🔍 <b>𝐁𝐈𝐍:</b> <code>{bin_filter}</code>\n"
    if bank_filter:
        cap += f"🏦 <b>𝐁𝐀𝐍𝐊:</b> <code>{escape(bank_filter)}</code>\n"
    cap += f"━━━━━━━━━━━━━━━━━━━━━━\n💎 <b>𝙎𝙘𝙧𝙖𝙥𝙥𝙚𝙙 𝘽𝙮 ⇾</b> {user_link}\n"

    try:
        with open(file_path, 'rb') as f:
            await update.effective_message.reply_document(
                document=f,
                filename=os.path.basename(file_path),
                caption=cap,
                parse_mode=ParseMode.HTML
            )
    finally:
        try:
            os.remove(file_path)
        except Exception:
            pass


# ═══════════════════════════════════════
#  /scr COMMAND
# ═══════════════════════════════════════
async def scr_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if pyro_user is None:
        await update.message.reply_text("❌ Scraper not initialized.", parse_mode=ParseMode.HTML)
        return

    user = update.effective_user
    if not await enforce_cooldown(user.id, update):
        return

    parts = update.message.text.strip().split()
    if len(parts) < 3:
        await update.message.reply_text(
            "💎 𝙎𝙥𝙖𝙘𝙚 𝘾𝙝𝙠 𝘾𝙘 𝙎𝙘𝙧𝙚𝙥𝙚𝙧 💸\n\n"
            "🧠 <b>Usage:</b> <code>/scr &lt;chat&gt; &lt;amount&gt; [bin|bank]</code>\n\n"
            "<b>Examples:</b>\n"
            "<code>/scr @channel 500</code>\n"
            "<code>/scr -1001234567890 200</code>\n"
            "<code>/scr 1234567890 300 414720</code>\n"
            "<code>/scr https://t.me/+abc 150 HDFC</code>\n"
            "<code>/scr channelname 100</code>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        return

    chat_id_raw = parts[1]
    try:
        limit = int(parts[2])
    except ValueError:
        await update.message.reply_text("❌ Invalid limit number.", parse_mode=ParseMode.HTML)
        return

    bin_filter = bank_filter = None
    if len(parts) > 3:
        if parts[3].isdigit():
            bin_filter = parts[3][:6]
        else:
            bank_filter = " ".join(parts[3:])

    max_lim = ADMIN_LIMIT if user.id in ADMIN_IDS else DEFAULT_LIMIT
    if limit > max_lim:
        await update.message.reply_text(
            f"🚫 Your max limit is <b>{max_lim}</b>.", parse_mode=ParseMode.HTML
        )
        return

    asyncio.create_task(_run_scr(update, chat_id_raw, limit, bin_filter, bank_filter))


async def _run_scr(update, chat_id_raw, limit, bin_filter, bank_filter):
    status = await update.message.reply_text(
        "<b>⏳ Scraping started...</b>",
        parse_mode=ParseMode.HTML
    )
    try:
        chat, err = await resolve_chat_safe(pyro_user, chat_id_raw)
        if err:
            await status.edit_text(err, parse_mode=ParseMode.HTML)
            return

        chat_name = chat.title or chat_id_raw
        await status.edit_text(
            f"<b>⚡ Scraping:</b> <code>{escape(chat_name)}</code>",
            parse_mode=ParseMode.HTML
        )

        raw = await scrape_messages(pyro_user, chat.id, limit, bin_filter, bank_filter)
        uniq, dups, expired = remove_duplicates_and_expired(raw)

        try:
            await status.delete()
        except Exception:
            pass

        await send_scraped_results(update, uniq, dups, expired,
                                   chat_name, bin_filter, bank_filter)
    except Exception as e:
        try:
            await status.edit_text(f"❌ Error: {escape(str(e))}", parse_mode=ParseMode.HTML)
        except Exception:
            pass


# ═══════════════════════════════════════
#  /mc COMMAND  (multi-chat)
# ═══════════════════════════════════════
async def mc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if pyro_user is None:
        await update.message.reply_text("❌ Scraper not initialized.", parse_mode=ParseMode.HTML)
        return

    user = update.effective_user
    if not await enforce_cooldown(user.id, update):
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "💎 <b>Multi Scraper</b>\n\n"
            "<b>Usage:</b> <code>/mc chat1 chat2 ... amount</code>\n"
            "<b>Example:</b> <code>/mc @ch1 -10012345 channelname 500</code>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        limit = int(args[-1])
    except ValueError:
        await update.message.reply_text("❌ Last argument must be a number.", parse_mode=ParseMode.HTML)
        return

    chat_list = args[:-1]
    max_lim   = ADMIN_LIMIT if user.id in ADMIN_IDS else DEFAULT_LIMIT
    if limit > max_lim:
        await update.message.reply_text(f"🚫 Max limit: <b>{max_lim}</b>.", parse_mode=ParseMode.HTML)
        return

    asyncio.create_task(_run_mc(update, chat_list, limit))


async def _run_mc(update, chat_list, limit):
    status = await update.message.reply_text(
        "<b>⏳ Scraping started...</b>",
        parse_mode=ParseMode.HTML
    )
    try:
        resolved = await asyncio.gather(
            *[resolve_chat_safe(pyro_user, c) for c in chat_list]
        )

        valid, failed = [], []
        for ident, (chat, err) in zip(chat_list, resolved):
            if err:
                failed.append(f"{ident}: {err}")
            else:
                valid.append(chat)

        results = await asyncio.gather(
            *[scrape_messages(pyro_user, chat.id, limit) for chat in valid],
            return_exceptions=True
        )

        all_cards = []
        for r in results:
            if isinstance(r, list):
                all_cards.extend(r)

        uniq, dups, expired = remove_duplicates_and_expired(all_cards)
        uniq = uniq[:limit]

        try:
            await status.delete()
        except Exception:
            pass

        await send_scraped_results(update, uniq, dups, expired, f"{len(valid)} chats")

        if failed:
            await update.message.reply_text(
                f"⚠️ <b>Failed ({len(failed)}):</b>\n"
                f"<code>{escape(chr(10).join(str(f)[:100] for f in failed[:5]))}</code>",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        try:
            await status.edit_text(f"❌ Error: {escape(str(e))}", parse_mode=ParseMode.HTML)
        except Exception:
            pass
