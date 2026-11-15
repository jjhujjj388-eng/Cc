# proxy.py
"""
Proxy Management Module for Black X Card Bot
Commands: /addpxy, /rmpxy, /mypxy
"""

import re
import logging
import aiohttp
import asyncio
import random
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from telegram.constants import ParseMode

# Import from your existing modules
from db import get_user, update_user
try:
    from gates.shopify.defaults import DEFAULT_PROXIES
except Exception:
    DEFAULT_PROXIES = []

# Configure logging
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
PROXY_TEST_URL = "http://httpbin.org/ip"
MAX_PROXIES_PER_USER = 50

### ----------------------- MOJI ID's ----------------------- ###
TEST_MOJI = "5212985021870123409"      # 🔄
RED_MOJI = "5323535839391653590"        # 👀
WORK_MOJI = "4958610528588008305"       # ✅ (working)
USE_MOJI = "5195033767969839232"        # ⚠️
AY_MOJI = "5332455502917949981"         # 📊
YY_MOJI = "5224450179368767019"         # 📊
# ==================== PROXY FORMAT FIXER ====================

def auto_fix_proxy_format(raw_proxy: str) -> Optional[str]:
    """
    Auto-detects and corrects various proxy formats to 'http://user:pass@host:port'.
    Handles:
    - IP:Port:User:Pass
    - Domain:Port:User:Pass
    - User:Pass@IP:Port
    - http://IP:Port (Transparent)
    - IP:Port (Transparent)
    - Protocols (http/https) and typos
    
    Args:
        raw_proxy: Raw proxy string
        
    Returns:
        Normalized proxy string (http://user:pass@host:port) or None if invalid
    """
    if not raw_proxy:
        return None

    # 1. Clean the string
    p = raw_proxy.strip()
    
    # 2. Handle protocol typo
    if p.startswith('hytp://'):
        p = 'http://' + p[7:]
    
    # 3. Extract protocol if present
    protocol = "http"
    if p.startswith(('http://', 'https://')):
        parts = p.split('://', 1)
        protocol = parts[0] 
        core = parts[1]
    else:
        core = p

    # 4. Analyze the core structure
    
    # Case A: Contains '@' (Standard format)
    if '@' in core:
        # Split by last '@' to handle passwords that might contain '@'
        auth_part, host_port_part = core.rsplit('@', 1)
        
        # Validate host:port part
        if ':' in host_port_part:
            return f"{protocol}://{auth_part}@{host_port_part}"
        else:
            return None

    # Case B: No '@' (Could be Host:Port:User:Pass or Host:Port)
    parts = core.split(':')
    
    # Check if it looks like Host:Port:User:Pass (like p102.squidproxies.com:9206:596:UYhumtl3N1Mi)
    if len(parts) >= 4 and parts[1].isdigit():
        host = parts[0] + ':' + parts[1]  # Combine host and port
        port = parts[1]
        user = parts[2]
        password = ':'.join(parts[3:])
        return f"{protocol}://{user}:{password}@{host}"
        
    # Check if it looks like Transparent Proxy (Host:Port)
    if len(parts) == 2 and parts[1].isdigit():
        return f"{protocol}://{parts[0]}:{parts[1]}"

    return None

def normalize_proxy_format(proxy: str) -> str:
    """Wrapper for auto_fix_proxy_format to maintain compatibility."""
    fixed = auto_fix_proxy_format(proxy)
    if fixed:
        return fixed
    
    proxy = proxy.strip()
    if proxy.startswith('hytp://'):
        proxy = 'http://' + proxy[7:]
    if not proxy.startswith(('http://', 'https://')):
        return f"http://{proxy}"
    return proxy

# ==================== PROXY TESTING ====================

async def test_proxy(proxy: str) -> Tuple[bool, str]:
    """
    Test if a proxy works by making a request to httpbin.org/ip.
    
    Args:
        proxy: Proxy string to test
        
    Returns:
        Tuple of (success, message)
    """
    normalized_proxy = normalize_proxy_format(proxy)
    
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(PROXY_TEST_URL, proxy=normalized_proxy) as response:
                response.raise_for_status()
                data = await response.json()
                if 'origin' in data and data['origin']:
                    return True, f"<tg-emoji emoji-id='{WORK_MOJI}'>✅</tg-emoji> Working (IP: {data['origin']})"
                else:
                    return False, f"<tg-emoji emoji-id='{RED_MOJI}'>❌</tg-emoji> Failed"
    except Exception as e:
        logger.error(f"Proxy test error: {e}")
        return False, f"<tg-emoji emoji-id='{RED_MOJI}'>❌</tg-emoji> Failed"

async def test_proxy_with_semaphore(semaphore, proxy: str) -> Tuple[bool, str]:
    """Test a proxy with a semaphore to limit concurrent connections."""
    async with semaphore:
        return await test_proxy(proxy)

# ==================== DATABASE FUNCTIONS ====================

async def get_user_proxies_from_db(user_id: int) -> list:
    """Get user's proxies from database, else built-in DEFAULT_PROXIES / proxy.txt."""
    try:
        user_data = await get_user(user_id)
        if user_data and user_data.get("proxies"):
            return user_data["proxies"]
    except Exception as e:
        logger.error(f"Error getting proxies for {user_id}: {e}")
    # Built-in proxies so users need not /addproxy
    if DEFAULT_PROXIES:
        return list(DEFAULT_PROXIES)
    try:
        import os
        for base in (os.path.dirname(os.path.abspath(__file__)), os.getcwd()):
            p = os.path.join(base, "proxy.txt")
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
                if lines:
                    return lines
    except Exception:
        pass
    return []

async def add_user_proxy_to_db(user_id: int, proxy: str) -> Tuple[bool, str]:
    """Add a proxy to user's proxy list."""
    try:
        user_data = await get_user(user_id)
        if not user_data:
            return False, "User not found"
        
        proxies = user_data.get('proxies', [])
        
        if len(proxies) >= MAX_PROXIES_PER_USER:
            return False, f"Maximum {MAX_PROXIES_PER_USER} proxies allowed"
        
        if proxy in proxies:
            return False, "Already Added"  # 👈 Changed message
        
        proxies.append(proxy)
        await update_user(user_id, proxies=proxies)
        return True, "Proxy added successfully"
    
    except Exception as e:
        logger.error(f"Error adding proxy for {user_id}: {e}")
        return False, "Database error"

async def remove_user_proxies_from_db(user_id: int, count: int = -1, specific_proxy: str = None) -> Tuple[bool, str]:
    """Remove proxies from user's proxy list."""
    try:
        user_data = await get_user(user_id)
        if not user_data:
            return False, "User not found"
        
        proxies = user_data.get('proxies', [])
        
        if not proxies:
            return False, "No proxies to remove"
        
        # 👇 NEW: Remove specific proxy if provided
        if specific_proxy:
            if specific_proxy in proxies:
                proxies.remove(specific_proxy)
                await update_user(user_id, proxies=proxies)
                return True, f"Removed proxy: {format_proxy_for_display(specific_proxy)}"
            else:
                return False, "Proxy not found"
        
        # Remove by count
        if count == -1 or count >= len(proxies):
            removed_count = len(proxies)
            await update_user(user_id, proxies=[])
            return True, f"Removed all {removed_count} proxies"
        else:
            removed = proxies[:count]
            remaining = proxies[count:]
            await update_user(user_id, proxies=remaining)
            return True, f"Removed {len(removed)} proxies"
    
    except Exception as e:
        logger.error(f"Error removing proxies for {user_id}: {e}")
        return False, "Database error"

def get_user_tier(user_id: int) -> str:
    """Get user tier (simplified version)."""
    try:
        return 'Free'
    except:
        return 'Free'

# ==================== FORMAT PROXY FOR DISPLAY ====================

def format_proxy_for_display(proxy: str) -> str:
    """Format proxy for display without username:password and without backticks"""
    try:
        # Remove protocol
        if '://' in proxy:
            proxy = proxy.split('://', 1)[1]
        
        # Handle user:pass@host:port format
        if '@' in proxy:
            auth_part, host_part = proxy.split('@', 1)
            # Just return the host part
            return host_part
        else:
            # Already just host:port
            return proxy
    except:
        return proxy

# ==================== COMMAND HANDLERS ====================

async def addpxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /addpxy command to add proxies."""
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or "User"
    
    # Get proxies from command or replied message
    if not context.args and not update.message.reply_to_message:
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{USE_MOJI}'>⚠️</tg-emoji> 𝘜𝘴𝘢𝘨𝘦:\n/addpxy user:pass@host:port\n/addpxy host:port:user:pass\nOr reply to a file with /addpxy",
            parse_mode="HTML"
        )
        return
    
    # Extract proxies
    proxy_text = ""
    if context.args:
        proxy_text = " ".join(context.args)
    elif update.message.reply_to_message:
        msg = update.message.reply_to_message
        if msg.text:
            proxy_text = msg.text
        elif msg.document and msg.document.mime_type == "text/plain":
            file = await context.bot.get_file(msg.document.file_id)
            file_content = await file.download_as_bytearray()
            proxy_text = file_content.decode('utf-8')
    
    # Parse proxies
    candidates = []
    for line in proxy_text.split('\n'):
        if line.strip():
            candidates.extend(line.strip().split())
    
    proxies = []
    original_proxies = []  # Store original format for display
    for raw in candidates:
        normalized = auto_fix_proxy_format(raw)
        if normalized:
            proxies.append(normalized)
            original_proxies.append(raw.strip())  # Keep original for display
    
    if not proxies:
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{USE_MOJI}'>⚠️</tg-emoji> No valid proxies found!",
            parse_mode="HTML"
        )
        return
    
    # Check current proxy count
    current_proxies = await get_user_proxies_from_db(user_id)
    if len(current_proxies) >= MAX_PROXIES_PER_USER:
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{USE_MOJI}'>⚠️</tg-emoji> Maximum {MAX_PROXIES_PER_USER} proxies reached! Use /rmpxy to remove some.",
            parse_mode="HTML"
        )
        return
    
    # Limit new proxies
    max_add = MAX_PROXIES_PER_USER - len(current_proxies)
    if len(proxies) > max_add:
        proxies = proxies[:max_add]
        original_proxies = original_proxies[:max_add]
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{USE_MOJI}'>⚠️</tg-emoji> Adding only {max_add} proxies (limit)",
            parse_mode="HTML"
        )
    
    # Processing message
    msg = await update.message.reply_text(
        f"<tg-emoji emoji-id='{TEST_MOJI}'>⏳</tg-emoji> Testing {len(proxies)} proxies...",
        parse_mode="HTML"
    )
    
    # Test proxies
    semaphore = asyncio.Semaphore(20)
    tasks = [test_proxy_with_semaphore(semaphore, p) for p in proxies]
    results = await asyncio.gather(*tasks)
    
    # Process results
    working = []
    failed = []
    already_added = []
    
    for proxy, original, (is_working, res_msg) in zip(proxies, original_proxies, results):
        if is_working:
            success, db_msg = await add_user_proxy_to_db(user_id, proxy)
            if success:
                working.append(original)  # Store original format
            else:
                if "Already Added" in db_msg:
                    already_added.append(original)  # Store original format
                else:
                    failed.append(original)  # Store original format
        else:
            failed.append(original)  # Store original format
    
    # Format response - SIRF PROXY NAME, NO MESSAGES
    response_parts = []
    
    response_parts.append(f"<tg-emoji emoji-id='{AY_MOJI}'>📊</tg-emoji> 𝑷𝒓𝒐𝒙𝒚 𝑹𝒆𝒔𝒖𝒍𝒕𝒔\n")
    
    if working:
        response_parts.append(f"\n<tg-emoji emoji-id='{WORK_MOJI}'>✅</tg-emoji> 𝘞𝘰𝘳𝘬𝘪𝘯𝘨: {len(working)}")
        for proxy in working:
            response_parts.append(f"<code>{proxy}</code>")
    
    if already_added:
        response_parts.append(f"\n<tg-emoji emoji-id='{USE_MOJI}'>⚠️</tg-emoji> 𝘈𝘭𝘳𝘦𝘢𝘥𝘺 𝘈𝘥𝘥𝘦𝘥: {len(already_added)}")
        for proxy in already_added:
            response_parts.append(f"<code>{proxy}</code>")
    
    if failed:
        response_parts.append(f"\n<tg-emoji emoji-id='{RED_MOJI}'>❌</tg-emoji> 𝘍𝘢𝘪𝘭𝘦𝘥: {len(failed)}")
        for proxy in failed:
            response_parts.append(f"<code>{proxy}</code>")
    
    await msg.edit_text("\n".join(response_parts), parse_mode="HTML")
    
async def rmpxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /rmpxy command to remove proxies."""
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or "User"
    
    specific_proxy = None
    count = -1
    remove_all = False
    
    if context.args:
        arg = " ".join(context.args).lower().strip()
        
        # 👇 CHECK IF USER TYPED "ALL"
        if arg == "all":
            remove_all = True
            count = -1  # Remove all proxies
        
        # Check if it looks like a proxy (contains . or : or digits)
        elif ':' in arg or '.' in arg:
            # Try to normalize it as a proxy
            normalized = auto_fix_proxy_format(arg)
            if normalized:
                specific_proxy = normalized
            else:
                # Try to parse as count
                try:
                    count = int(arg)
                except:
                    await update.message.reply_text(
                        f"<tg-emoji emoji-id='{USE_MOJI}'>⚠️</tg-emoji> 𝘜𝘴𝘢𝘨𝘦: /rmpxy [count] or /rmpxy [proxy] or /rmpxy all",
                        parse_mode="HTML"
                    )
                    return
        else:
            # Try to parse as count
            try:
                count = int(arg)
            except:
                await update.message.reply_text(
                    f"<tg-emoji emoji-id='{USE_MOJI}'>⚠️</tg-emoji> 𝘜𝘴𝘢𝘨𝘦: /rmpxy [count] or /rmpxy [proxy] or /rmpxy all",
                    parse_mode="HTML"
                )
                return
    
    # Remove proxies
    if remove_all:
        success, message = await remove_user_proxies_from_db(user_id, -1, None)
        response = f"<tg-emoji emoji-id='{AY_MOJI}'>📊</tg-emoji> Proxy Removal\n\n{message}"
    elif specific_proxy:
        success, message = await remove_user_proxies_from_db(user_id, -1, specific_proxy)
        response = f"<tg-emoji emoji-id='{AY_MOJI}'>📊</tg-emoji> Proxy Removal\n\n{message}"
    else:
        success, message = await remove_user_proxies_from_db(user_id, count, None)
        response = f"<tg-emoji emoji-id='{AY_MOJI}'>📊</tg-emoji> Proxy Removal\n\n{message}"
    
    await update.message.reply_text(response, parse_mode="HTML")
    
async def mypxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mypxy command to list proxies."""
    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or "User"
    
    # 👇 COOLDOWN HATAYA
    
    # Get proxies
    proxies = await get_user_proxies_from_db(user_id)
    
    if not proxies:
        response = f"<tg-emoji emoji-id='{AY_MOJI}'>📊</tg-emoji> No Proxies\n\nYou have no proxies saved.\nUse /addpxy to add some."
        await update.message.reply_text(response, parse_mode="HTML")
        return
    
    # Format list - WITHOUT numbers and WITHOUT backticks
    proxy_list = ""
    for proxy in proxies:
        display_proxy = format_proxy_for_display(proxy)
        proxy_list += f"{display_proxy}\n"
    
    # NO USER LINE AT BOTTOM
    response = f"<tg-emoji emoji-id='{AY_MOJI}'>📊</tg-emoji> 𝙔𝙤𝙪𝙧 𝙋𝙧𝙤𝙭𝙞𝙚𝙨 ({len(proxies)}/{MAX_PROXIES_PER_USER})\n\n{proxy_list}"
    
    await update.message.reply_text(response, parse_mode="HTML")

# ==================== REGISTRATION FUNCTION ====================

async def chkpxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/chkpxy — test every saved proxy live or dead, remove dead ones."""
    user = update.effective_user
    user_id = user.id

    proxies = await get_user_proxies_from_db(user_id)
    if not proxies:
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{AY_MOJI}'>📊</tg-emoji> No proxies to check.\nUse /addpxy first.",
            parse_mode="HTML",
        )
        return

    msg = await update.message.reply_text(
        f"<tg-emoji emoji-id='{TEST_MOJI}'>⏳</tg-emoji> Testing {len(proxies)} proxies live/dead...",
        parse_mode="HTML",
    )

    semaphore = asyncio.Semaphore(20)
    tasks = [test_proxy_with_semaphore(semaphore, p) for p in proxies]
    results = await asyncio.gather(*tasks)

    live: list[str] = []
    dead: list[str] = []
    for proxy, (is_working, _res) in zip(proxies, results):
        if is_working:
            live.append(proxy)
        else:
            dead.append(proxy)

    # Silently remove dead proxies so the user's pool stays healthy
    if dead:
        try:
            await update_user(user_id, proxies=live)
        except Exception as e:
            logger.warning(f"chkpxy: could not persist cleanup: {e}")

    parts = [f"<tg-emoji emoji-id='{AY_MOJI}'>📊</tg-emoji> 𝑷𝒓𝒐𝒙𝒚 𝑯𝒆𝒂𝒍𝒕𝒉 𝑪𝒉𝒆𝒄𝒌\n"]
    parts.append(f"\n<tg-emoji emoji-id='{WORK_MOJI}'>✅</tg-emoji> 𝙇𝙞𝙫𝙚: {len(live)}")
    for p in live:
        parts.append(f"<code>{format_proxy_for_display(p)}</code>")
    parts.append(f"\n<tg-emoji emoji-id='{RED_MOJI}'>❌</tg-emoji> 𝘿𝙚𝙖𝙙 (removed): {len(dead)}")
    for p in dead:
        parts.append(f"<code>{format_proxy_for_display(p)}</code>")

    text = "\n".join(parts)
    # Telegram message limit safety
    if len(text) > 3800:
        text = text[:3800] + "\n..."
    await msg.edit_text(text, parse_mode="HTML")


def register_proxy_handlers(application):
    """Register all proxy-related handlers."""
    application.add_handler(CommandHandler("addpxy", addpxy_command))
    application.add_handler(CommandHandler("rmpxy", rmpxy_command))
    application.add_handler(CommandHandler("mypxy", mypxy_command))
    application.add_handler(CommandHandler("chkpxy", chkpxy_command))
    logger.info("✅ Proxy handlers registered: /addpxy, /rmpxy, /mypxy")