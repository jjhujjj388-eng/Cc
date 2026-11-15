# gates/rm.py
# ==================== rm.py ====================
# Site removal commands for Black X Card Bot
# Commands: /rm, /removeall, /show
# ===============================================

import re
import time
import os
import asyncio
import aiofiles
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler
from db import get_user, update_user

# ------------------ HELPER FUNCTIONS ------------------

def extract_urls_from_text(text: str) -> list:
    """
    Extract URLs/domains from text
    Supports: domain.com, http://domain.com, https://domain.com
    """
    url_pattern = re.compile(
        r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+(?:\.[a-zA-Z]{2,})+)'
    )
    matches = url_pattern.findall(text)
    cleaned = []
    for match in matches:
        if not match.startswith(('http://', 'https://')):
            cleaned.append(f"https://{match}")
        else:
            cleaned.append(match)
    return cleaned

async def get_user_sites(user_id: int) -> list:
    """Get user's custom URLs from database"""
    try:
        user_data = await get_user(user_id)
        if not user_data:
            return []
        return user_data.get('custom_urls', [])
    except Exception as e:
        print(f"❌ Error getting user sites: {e}")
        return []

async def save_user_sites(user_id: int, sites: list) -> bool:
    """Save user's custom URLs to database"""
    try:
        success = await update_user(user_id, custom_urls=sites)
        return success
    except Exception as e:
        print(f"❌ Error saving user sites: {e}")
        return False

# ------------------ COMMAND 1: /rm ------------------

async def rm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Remove specific site(s) from user's list
    Format: /rm site.com or /rm site1.com site2.com
    """
    user = update.effective_user
    user_id = user.id
    
    if not context.args:
        await update.message.reply_text(
            "𝙁𝙤𝙧𝙢𝙖𝙩: /rm site.com",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        rm_text = " ".join(context.args).strip()
        sites_to_remove = extract_urls_from_text(rm_text)
        
        if not sites_to_remove:
            await update.message.reply_text(
                "❌ 𝙉𝙤 𝙫𝙖𝙡𝙞𝙙 𝙪𝙧𝙡𝙨/𝙙𝙤𝙢𝙖𝙞𝙣𝙨 𝙛𝙤𝙪𝙣𝙙!",
                parse_mode=ParseMode.HTML
            )
            return
        
        user_sites = await get_user_sites(user_id)
        removed_sites = []
        not_found_sites = []
        
        for site in sites_to_remove:
            if site in user_sites:
                user_sites.remove(site)
                removed_sites.append(site)
            else:
                not_found_sites.append(site)
        
        if removed_sites:
            await save_user_sites(user_id, user_sites)
        
        response_parts = []
        if removed_sites:
            for site in removed_sites:
                display_site = site.replace("https://", "").replace("http://", "")
                response_parts.append(f"✅ 𝙍𝙚𝙢𝙤𝙫𝙚𝙙: {display_site}")
        
        if not_found_sites:
            for site in not_found_sites:
                display_site = site.replace("https://", "").replace("http://", "")
                response_parts.append(f"❌ 𝙉𝙤𝙩 𝙁𝙤𝙪𝙣𝙙: {display_site}")
        
        if response_parts:
            await update.message.reply_text(
                "\n\n".join(response_parts),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        else:
            await update.message.reply_text(
                "❌ 𝙉𝙤 𝙨𝙞𝙩𝙚𝙨 𝙬𝙚𝙧𝙚 𝙧𝙚𝙢𝙤𝙫𝙚𝙙!",
                parse_mode=ParseMode.HTML
            )
            
    except Exception as e:
        await update.message.reply_text(
            f"❌ 𝙀𝙧𝙧𝙤𝙧: {str(e)}",
            parse_mode=ParseMode.HTML
        )

# ------------------ COMMAND 2: /removeall ------------------

async def removeall_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Remove all sites from user's list
    Format: /removeall
    """
    user = update.effective_user
    user_id = user.id
    
    try:
        user_sites = await get_user_sites(user_id)
        
        if not user_sites:
            await update.message.reply_text(
                "❌ 𝙔𝙤𝙪 𝙙𝙤𝙣'𝙩 𝙝𝙖𝙫𝙚 𝙖𝙣𝙮 𝙨𝙞𝙩𝙚𝙨 𝙩𝙤 𝙧𝙚𝙢𝙤𝙫𝙚!",
                parse_mode=ParseMode.HTML
            )
            return
        
        site_count = len(user_sites)
        
        success = await save_user_sites(user_id, [])
        
        if success:
            await update.message.reply_text(
                f"✅ 𝘼𝙡𝙡 𝙨𝙞𝙩𝙚𝙨 𝙧𝙚𝙢𝙤𝙫𝙚𝙙!\n\n"
                f"🗑️ 𝙍𝙚𝙢𝙤𝙫𝙚𝙙 {site_count} 𝙨𝙞𝙩𝙚𝙨 𝙛𝙧𝙤𝙢 𝙮𝙤𝙪𝙧 𝙙𝙖𝙩𝙖𝙗𝙖𝙨𝙚.",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                "❌ 𝙁𝙖𝙞𝙡𝙚𝙙 𝙩𝙤 𝙧𝙚𝙢𝙤𝙫𝙚 𝙨𝙞𝙩𝙚𝙨. 𝙋𝙡𝙚𝙖𝙨𝙚 𝙩𝙧𝙮 𝙖𝙜𝙖𝙞𝙣.",
                parse_mode=ParseMode.HTML
            )
            
    except Exception as e:
        await update.message.reply_text(
            f"❌ 𝙀𝙧𝙧𝙤𝙧: {str(e)}",
            parse_mode=ParseMode.HTML
        )

# ------------------ COMMAND 3: /show ------------------

async def show_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show all saved sites with export as .txt file
    Format: /show
    """
    user = update.effective_user
    user_id = user.id
    timestamp = int(time.time())
    
    try:
        user_sites = await get_user_sites(user_id)
        
        if not user_sites:
            await update.message.reply_text(
                "❌ 𝙔𝙤𝙪 𝙝𝙖𝙫𝙚𝙣'𝙩 𝙖𝙙𝙙𝙚𝙙 𝙖𝙣𝙮 𝙨𝙞𝙩𝙚𝙨 𝙮𝙚𝙩!",
                parse_mode=ParseMode.HTML
            )
            return
        
        sites_text = "📋 𝙔𝙤𝙪𝙧 𝙎𝙖𝙫𝙚𝙙 𝙎𝙞𝙩𝙚𝙨:\n\n"
        for idx, site in enumerate(user_sites, 1):
            display_site = site.replace("https://", "").replace("http://", "")
            sites_text += f"{idx}. {display_site}\n"
        
        sites_text += f"\n📊 𝙏𝙤𝙩𝙖𝙡: {len(user_sites)} 𝙨𝙞𝙩𝙚𝙨"
        
        filename = f"sites_{user_id}_{timestamp}.txt"
        
        async with aiofiles.open(filename, "w", encoding="utf-8") as f:
            await f.write(sites_text)
        
        caption_text = (
            f"✅ 𝙎𝙞𝙩𝙚𝙨 𝙀𝙭𝙥𝙤𝙧𝙩𝙚𝙙!\n\n"
            f"📊 𝙏𝙤𝙩𝙖𝙡 𝙎𝙞𝙩𝙚𝙨: {len(user_sites)}\n"
            f"📁 𝘼𝙩𝙩𝙖𝙘𝙝𝙚𝙙 𝙛𝙞𝙡𝙚 𝙘𝙤𝙣𝙩𝙖𝙞𝙣𝙨 𝙖𝙡𝙡 𝙮𝙤𝙪𝙧 𝙨𝙞𝙩𝙚𝙨."
        )
        
        with open(filename, 'rb') as file:
            await update.message.reply_document(
                document=file,
                filename=f"sites_{user_id}.txt",
                caption=caption_text,
                parse_mode=ParseMode.HTML
            )
        
        try:
            os.remove(filename)
        except:
            pass
            
    except Exception as e:
        await update.message.reply_text(
            f"❌ 𝙀𝙧𝙧𝙤𝙧: {str(e)}",
            parse_mode=ParseMode.HTML
        )

# ------------------ REGISTRATION FUNCTION ------------------

def register_rm_handlers(application):
    """
    Register all site removal commands with the application
    Call this from main.py
    """
    application.add_handler(CommandHandler("rm", rm_command))
    application.add_handler(CommandHandler("removeall", removeall_command))
    application.add_handler(CommandHandler("show", show_command))
    
    print("✅ Site removal commands registered: /rm, /removeall, /show")