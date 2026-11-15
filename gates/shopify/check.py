# gates/check.py
"""
Site Checker Command for Black X Card Bot
Command: /check - Check if sites are working or dead
"""

import re
import time
import asyncio
import aiohttp
import urllib.parse
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from db import get_user, update_user
from proxy import get_user_proxies_from_db

logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
API_BASE_URL = "http://108.165.12.183:8081/"
TEST_CARD = "4031630422575208|01|2030|280"
DEAD_MOJI = "5210952531676504517"
MAX_CONCURRENT_CHECKS = 5  # एक साथ कितनी साइट्स चेक करनी हैं

# ==================== GLOBAL STATE ====================
CHECK_WORKING_SITES = {}    # user_id -> {"working": [], "expiry": timestamp}
DB_CHECK_PROCESSING = {}    # user_id -> True/False
dead_proxies = {}           # user_id -> [proxy1, proxy2, ...]
proxy_index_counter = {}    # user_id -> current_index

# ==================== UTILITY FUNCTIONS ====================

async def get_user_sites(user_id: int) -> list:
    """Get user's custom URLs from database"""
    try:
        user_data = await get_user(user_id)
        if not user_data:
            return []
        return user_data.get('custom_urls', [])
    except Exception as e:
        logger.error(f"Error getting user sites for {user_id}: {e}")
        return []

async def save_user_sites(user_id: int, sites: list) -> bool:
    """Save user's custom URLs to database"""
    try:
        return await update_user(user_id, custom_urls=sites)
    except Exception as e:
        logger.error(f"Error saving user sites for {user_id}: {e}")
        return False

async def get_user_proxies(user_id: int) -> list:
    """Get user's proxies from database"""
    return await get_user_proxies_from_db(user_id)

async def get_next_proxy(user_id: int) -> str:
    """Get next working proxy in rotation"""
    proxies = await get_user_proxies(user_id)
    if not proxies:
        return None
    
    # Filter out dead proxies
    user_dead = dead_proxies.get(user_id, [])
    available = [p for p in proxies if p not in user_dead]
    
    if not available:
        # All proxies dead, reset and try again
        dead_proxies[user_id] = []
        available = proxies
    
    if user_id not in proxy_index_counter:
        proxy_index_counter[user_id] = 0
    else:
        proxy_index_counter[user_id] = (proxy_index_counter[user_id] + 1) % len(available)
    
    return available[proxy_index_counter[user_id]]

async def mark_proxy_dead(user_id: int, proxy: str):
    """Mark a proxy as dead"""
    if user_id not in dead_proxies:
        dead_proxies[user_id] = []
    if proxy not in dead_proxies[user_id]:
        dead_proxies[user_id].append(proxy)

def extract_urls_from_text(text: str) -> list:
    """Extract valid URLs/domains from text"""
    clean_urls = set()
    if not text:
        return []
    
    # पहले से मौजूद URLs को सीधे पकड़ो
    url_pattern = r'(?:https?://)?(?:www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?'
    matches = re.findall(url_pattern, text)
    
    for match in matches:
        # प्रोटोकॉल नहीं है तो https:// लगा दो
        if not match.startswith(('http://', 'https://')):
            match = 'https://' + match
        
        # ट्रेलिंग स्लैश और अन्य कचरा हटाओ
        match = match.rstrip('/')
        clean_urls.add(match)
    
    return list(clean_urls)
    
def extract_json_from_response(response_text: str) -> dict:
    """Extract JSON from API response"""
    if not response_text:
        return None
    start = response_text.find('{')
    if start == -1:
        return None
    
    brace_count = 0
    for i in range(start, len(response_text)):
        if response_text[i] == '{':
            brace_count += 1
        elif response_text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                try:
                    import json
                    return json.loads(response_text[start:i+1])
                except:
                    return None
    return None

def is_site_dead(response_text: str) -> bool:
    """Check if site returned a dead response"""
    if not response_text:
        return True
    
    response_lower = response_text.lower()
    dead_indicators = [
        "receipt id is empty", "handle is empty", "product id is empty",
        "tax amount is empty", "r4 token empty", "del ammount empty",
        "invalid json format", "item is out of stock", "token empty",
        "id empty", "r2 id empty", "hcaptcha detected", "clinte token",
        "py id empty", "tax ammount empty", "invalid_token",
        "delivery ammount empty", "r3 token empty",
        "payment method identifier is empty", "invalid url",
        "error in 1st req", "cloudflare", "failed",
        "connection failed", "timed out", "access denied",
        "could not resolve", "domain name not found",
        "empty reply from server", "http_error_504", "gateway timeout",
        "internal server error", "service unavailable",
        "captcha_required", "bad gateway", "Failed to get session token",
        "site dead", "Cart failed with status 429", "Site requires login!",
        "NO_SESSION_TOKEN", "Submit Rejected:", "Failed to perform, curl:"
    ]
    return any(indicator in response_lower for indicator in dead_indicators)

# ==================== SITE TESTING ====================

async def test_single_site(session: aiohttp.ClientSession, site: str, proxy: str = None) -> dict:
    """Test a single site by hitting the real Shopify charging API used by /sh.

    A site is only considered dead if the API returns a hard kill signal
    (``site dead``, ``invalid url``, ``site requires login``, etc.). Normal
    decline responses like ``CARD_DECLINED`` or ``insufficient_funds`` mean
    the site is **working** — the gateway just rejected the test card.
    """
    from .common import call_shopify_api, is_site_killed_by

    try:
        api_response = await call_shopify_api(
            TEST_CARD, site, proxy or "", timeout=45, session=session
        )
    except Exception as e:
        return {"status": "dead", "response": str(e), "site": site}

    response_msg = (api_response.get("Response") or "").strip()

    # Hard transport / unparseable failure
    if api_response.get("raw") is None:
        return {"status": "dead", "response": response_msg or "No response", "site": site}

    # Site explicitly told us it can't be used
    if is_site_killed_by(api_response):
        return {"status": "dead", "response": response_msg or "Site dead", "site": site}

    price = api_response.get("Price", 0)
    try:
        price_str = f"${float(price):.2f}"
    except (TypeError, ValueError):
        price_str = "$0.00"
    return {
        "status": "working",
        "response": response_msg or "OK",
        "site": site,
        "price": price_str,
    }

# ==================== /check COMMAND ====================

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Check sites for working status
    Format: /check site1.com site2.com
    Or just /check to check DB sites
    """
    user = update.effective_user
    user_id = user.id
    
    if context.args:
        # Manual sites provided
        check_text = " ".join(context.args)
        sites_to_check = extract_urls_from_text(check_text)
        
        if not sites_to_check:
            await update.message.reply_text(
                f'<tg-emoji emoji-id="{DEAD_MOJI}">❌</tg-emoji> No valid URLs/domains found!\n\n'
                '💡 Example:\n<code>/check example.com site2.com</code>',
                parse_mode=ParseMode.HTML
            )
            return
        
        if len(sites_to_check) > 20:
            await update.message.reply_text(
                f"⚠️ Found {len(sites_to_check)} sites, checking only first 20.",
                parse_mode=ParseMode.HTML
            )
            sites_to_check = sites_to_check[:20]
        
        # Store working sites for later adding
        CHECK_WORKING_SITES[user_id] = {
            "working": [],
            "expiry": time.time() + 300  # 5 minutes expiry
        }
        
        # Start background check
        asyncio.create_task(process_manual_check(update, context, sites_to_check, user_id))
    
    else:
        # Show DB check option
        buttons = [[InlineKeyboardButton("🔍 𝘾𝙝𝙚𝙘𝙠 𝙈𝙮 𝘿𝘽 𝙎𝙞𝙩𝙚𝙨", callback_data="check_db_sites")]]
        
        instruction_text = """🔍 𝙎𝙞𝙩𝙚 𝘾𝙝𝙚𝙘𝙠𝙚𝙧

𝙏𝙤 𝙘𝙝𝙚𝙘𝙠 𝙨𝙥𝙚𝙘𝙞𝙛𝙞𝙘 𝙨𝙞𝙩𝙚𝙨:
<code>/check example.com site2.com</code>

𝙊𝙧 𝙘𝙡𝙞𝙘𝙠 𝙗𝙚𝙡𝙤𝙬 𝙩𝙤 𝙘𝙝𝙚𝙘𝙠 𝙮𝙤𝙪𝙧 𝙨𝙖𝙫𝙚𝙙 𝘿𝘽 𝙨𝙞𝙩𝙚𝙨:"""
        
        await update.message.reply_text(
            instruction_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )

async def process_manual_check(update: Update, context: ContextTypes.DEFAULT_TYPE, sites: list, user_id: int):
    """Process manual site check in background"""
    total_sites = len(sites)
    
    status_msg = await update.message.reply_text(
        f"<pre>🔍 Checking {total_sites} sites...</pre>",
        parse_mode=ParseMode.HTML
    )
    
    working_sites = []
    dead_sites = []
    
    # Use a single session for all requests
    async with aiohttp.ClientSession() as session:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
        
        async def check_with_semaphore(site):
            async with semaphore:
                proxy = await get_next_proxy(user_id)
                return await test_single_site(session, site, proxy)
        
        tasks = [check_with_semaphore(site) for site in sites[:10]]  # Max 10 for manual
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for site, result in zip(sites[:10], results):
            if isinstance(result, Exception):
                dead_sites.append({"site": site, "price": "$0.00"})
            elif result["status"] == "working":
                working_sites.append({
                    "site": site,
                    "price": result.get("price", "$0.00")
                })
            else:
                dead_sites.append({
                    "site": site,
                    "price": result.get("price", "$0.00")
                })
    
    # Store working sites for later adding
    if user_id in CHECK_WORKING_SITES:
        CHECK_WORKING_SITES[user_id]["working"] = [s["site"] for s in working_sites]
    
    # Build result message
    final_text = f"""✅ 𝙎𝙞𝙩𝙚 𝘾𝙝𝙚𝙘𝙠 𝘾𝙤𝙢𝙥𝙡𝙚𝙩𝙚!

📊 𝙍𝙚𝙨𝙪𝙡𝙩𝙨:
🟢 𝙒𝙤𝙧𝙠𝙞𝙣𝙜 𝙎𝙞𝙩𝙚𝙨: {len(working_sites)}
🔴 𝘿𝙚𝙖𝙙 𝙎𝙞𝙩𝙚𝙨: {len(dead_sites)}

"""
    
    if working_sites:
        final_text += "✅ 𝙒𝙤𝙧𝙠𝙞𝙣𝙜 𝙎𝙞𝙩𝙚𝙨:\n"
        for idx, site_data in enumerate(working_sites, 1):
            final_text += f"{idx}. {site_data['site']} - {site_data['price']}\n"
        final_text += "\n"
    
    if dead_sites:
        final_text += "❌ 𝘿𝙚𝙖𝙙 𝙎𝙞𝙩𝙚𝙨:\n"
        for idx, site_data in enumerate(dead_sites[:5], 1):
            final_text += f"{idx}. {site_data['site']}\n"
    
    buttons = []
    if working_sites:
        buttons.append([InlineKeyboardButton(
            "➕ 𝘼𝙙𝙙 𝙒𝙤𝙧𝙠𝙞𝙣𝙜 𝙎𝙞𝙩𝙚𝙨 𝙩𝙤 𝘿𝘽",
            callback_data=f"add_working:{user_id}"
        )])
    
    try:
        await status_msg.edit_text(
            final_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
        )
    except Exception as e:
        logger.error(f"Failed to edit status message: {e}")

# ==================== DB SITE CHECK (IMPROVED) ====================

async def check_db_sites_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Check My DB Sites' button click"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_sites = await get_user_sites(user_id)
    
    if not user_sites:
        await query.edit_message_text(
            "❌ 𝙔𝙤𝙪 𝙝𝙖𝙫𝙚𝙣'𝙩 𝙖𝙙𝙙𝙚𝙙 𝙖𝙣𝙮 𝙨𝙞𝙩𝙚𝙨 𝙮𝙚𝙩!\n\n"
            "Use /add &lt;site&gt; to add sites.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Check if already processing
    if DB_CHECK_PROCESSING.get(user_id, False):
        await query.answer("⚠️ Already checking your sites...", show_alert=True)
        return
    
    # Start background task (prevents freezing)
    asyncio.create_task(process_db_check(query, context, user_sites, user_id))

async def process_db_check(query, context, user_sites: list, user_id: int):
    """Process DB site check in background"""
    DB_CHECK_PROCESSING[user_id] = True
    total_sites = len(user_sites)
    
    # Setup initial message
    buttons = [
        [InlineKeyboardButton(f"✅ Working: 0", callback_data="none")],
        [InlineKeyboardButton(f"❌ Dead: 0", callback_data="none")],
        [InlineKeyboardButton(f"📊 Progress: 0/{total_sites}", callback_data="none")],
        [InlineKeyboardButton("⛔ STOP", callback_data=f"stop_db_check:{user_id}")]
    ]
    
    try:
        status_msg = await query.edit_message_text(
            f"<pre>🔍 Checking Your DB Sites...</pre>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except:
        status_msg = await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"<pre>🔍 Checking Your DB Sites...</pre>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    
    working_sites = []
    dead_sites = []
    checked = 0
    
    # Use a single session for all requests
    async with aiohttp.ClientSession() as session:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
        
        async def check_one_site(site):
            nonlocal checked
            if not DB_CHECK_PROCESSING.get(user_id, False):
                return None
            
            async with semaphore:
                proxy = await get_next_proxy(user_id)
                result = await test_single_site(session, site, proxy)
                
                if not DB_CHECK_PROCESSING.get(user_id, False):
                    return None
                
                checked += 1
                return result
        
        # Process in batches
        batch_size = 10
        for i in range(0, len(user_sites), batch_size):
            if not DB_CHECK_PROCESSING.get(user_id, False):
                break
            
            batch = user_sites[i:i+batch_size]
            tasks = [check_one_site(site) for site in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for site, result in zip(batch, results):
                if result is None:
                    continue
                if isinstance(result, Exception) or result["status"] == "dead":
                    dead_sites.append(site)
                else:
                    working_sites.append(site)
            
            # Update message every batch
            if DB_CHECK_PROCESSING.get(user_id, False):
                buttons = [
                    [InlineKeyboardButton(f"✅ Working: {len(working_sites)}", callback_data="none")],
                    [InlineKeyboardButton(f"❌ Dead: {len(dead_sites)}", callback_data="none")],
                    [InlineKeyboardButton(f"📊 Progress: {checked}/{total_sites}", callback_data="none")],
                    [InlineKeyboardButton("⛔ STOP", callback_data=f"stop_db_check:{user_id}")]
                ]
                try:
                    await status_msg.edit_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))
                except:
                    pass
            
            # Small delay between batches
            await asyncio.sleep(0.5)
    
    DB_CHECK_PROCESSING[user_id] = False
    
    # Remove dead sites from user's DB
    if dead_sites:
        current_sites = await get_user_sites(user_id)
        updated_sites = [s for s in current_sites if s not in dead_sites]
        await save_user_sites(user_id, updated_sites)
    
    # Build final message
    if checked < total_sites:
        final_text = f"""<pre>⛔ Checking Stopped!

📊 Results:
✅ Working: {len(working_sites)}
❌ Dead Removed: {len(dead_sites)}
📊 Checked: {checked}/{total_sites}</pre>"""
    else:
        final_text = f"""<pre>✅ DB Site Check Complete!

📊 Results:
✅ Working: {len(working_sites)}
❌ Dead Removed: {len(dead_sites)}
📊 Total: {total_sites}</pre>"""
    
    final_buttons = [
        [InlineKeyboardButton(f"✅ Working: {len(working_sites)}", callback_data="none")],
        [InlineKeyboardButton(f"❌ Dead Removed: {len(dead_sites)}", callback_data="none")],
        [InlineKeyboardButton(f"📊 Total: {total_sites}", callback_data="none")]
    ]
    
    try:
        await status_msg.edit_text(
            final_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(final_buttons)
        )
    except:
        pass

# ==================== STOP DB CHECK ====================

async def stop_db_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stop DB check button"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if ":" not in data:
        return
    
    user_id = int(data.split(":")[1])
    clicking_user_id = query.from_user.id
    
    if clicking_user_id != user_id:
        await query.answer("❌ You can't stop this check!", show_alert=True)
        return
    
    DB_CHECK_PROCESSING[user_id] = False
    await query.answer("⛔ Stopping...", show_alert=False)

# ==================== ADD WORKING SITES ====================

async def add_working_sites_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle add working sites button"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if ":" not in data:
        return
    
    user_id = int(data.split(":")[1])
    clicking_user_id = query.from_user.id
    
    if clicking_user_id != user_id:
        await query.answer("❌ You can't use this button!", show_alert=True)
        return
    
    if user_id not in CHECK_WORKING_SITES:
        await query.answer("❌ No sites data found! Run /check again", show_alert=True)
        return
    
    site_data = CHECK_WORKING_SITES[user_id]
    
    if time.time() > site_data.get("expiry", 0):
        await query.answer("❌ Data expired! Run /check again", show_alert=True)
        del CHECK_WORKING_SITES[user_id]
        return
    
    working_sites = site_data.get("working", [])
    
    if not working_sites:
        await query.answer("❌ No working sites to add!", show_alert=True)
        return
    
    current_sites = await get_user_sites(user_id)
    added = 0
    duplicates = 0
    
    for site in working_sites:
        if site not in current_sites:
            current_sites.append(site)
            added += 1
        else:
            duplicates += 1
    
    await save_user_sites(user_id, current_sites)
    del CHECK_WORKING_SITES[user_id]
    
    result_msg = f"""✅ Sites Added to DB!

📊 Results:
✅ New Sites Added: {added}
⚠️ Duplicates Skipped: {duplicates}
📈 Total Sites Now: {len(current_sites)}"""
    
    await query.edit_message_text(result_msg, parse_mode=ParseMode.HTML)

# ==================== NOOP CALLBACK ====================

async def none_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle non-functional buttons"""
    query = update.callback_query
    await query.answer()

# ==================== REGISTRATION ====================

def register_check_handlers(application):
    """Register all check command handlers"""
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CallbackQueryHandler(check_db_sites_callback, pattern="^check_db_sites$"))
    application.add_handler(CallbackQueryHandler(stop_db_check_callback, pattern="^stop_db_check:"))
    application.add_handler(CallbackQueryHandler(add_working_sites_callback, pattern="^add_working:"))
    application.add_handler(CallbackQueryHandler(none_callback, pattern="^none$"))
    
    logger.info("✅ /check command registered (with background processing)")