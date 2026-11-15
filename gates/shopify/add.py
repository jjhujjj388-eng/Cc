# gates/add.py
# Shopify Site Add Command - /add
# Allows users to add custom Shopify sites to their database

import re
from html import escape
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user, update_user

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Telegram command: /add <site_url1> <site_url2> ..."""
    user = update.effective_user
    user_id = user.id

    if not context.args:
        await update.message.reply_text(
            "❌ <b>Format:</b> <code>/add site1.com site2.com</code>\n"
            "<i>Example: /add example.myshopify.com</i>",
            parse_mode=ParseMode.HTML
        )
        return

    # Get current sites from database
    user_data = await get_user(user_id)
    if not user_data:
        await update.message.reply_text("❌ User not found in database.")
        return
    
    current_sites = user_data.get("custom_urls", [])
    if current_sites is None:
        current_sites = []
    
    response_lines = []
    new_sites_added = []
    duplicate_sites = []
    
    for raw_site in context.args:
        site = raw_site.strip()
        
        if not site:
            continue
        
        # Skip numbers like 1., 2., etc.
        if site.replace(".", "").isdigit():
            continue
        
        # Skip if too short
        if len(site) < 4:
            continue
        
        # Clean site
        site = site.lower()
        
        # Fix common issues
        site = site.replace("https://https://", "https://")
        site = site.replace("http://https://", "https://")
        site = site.replace("https://http://", "http://")
        
        # Format site properly
        if site.startswith(("http://", "https://")):
            formatted_site = site
        elif site.startswith("www."):
            formatted_site = f"https://{site}"
        elif "." in site and not site.split(".")[0].isdigit():
            formatted_site = f"https://{site}"
        else:
            continue
        
        # Clean up trailing slash
        if formatted_site.endswith("/"):
            formatted_site = formatted_site[:-1]
        
        # Check if site already exists (case insensitive)
        formatted_lower = formatted_site.lower()
        site_exists = False
        
        for existing_site in current_sites:
            if existing_site.lower() == formatted_lower:
                site_exists = True
                break
        
        if site_exists:
            display_site = formatted_site.replace("https://", "").replace("http://", "")
            duplicate_sites.append(display_site)
        else:
            # Add to list
            current_sites.append(formatted_site)
            new_sites_added.append(formatted_site)
            display_site = formatted_site.replace("https://", "").replace("http://", "")
            response_lines.append(f"✅ 𝙎𝙞𝙩𝙚 𝙎𝙪𝙘𝙘𝙚𝙨𝙨𝙛𝙪𝙡𝙡𝙮 𝘼𝙙𝙙𝙚𝙙: {display_site}")
    
    # Update database if new sites were added
    if new_sites_added:
        try:
            # Update database
            success = await update_user(user_id, custom_urls=current_sites)
            if not success:
                await update.message.reply_text("❌ Database update failed.")
                return
        except Exception as e:
            await update.message.reply_text(f"❌ Database error: {escape(str(e))}")
            return
    
    # Add duplicate sites to response
    for dup_site in duplicate_sites:
        response_lines.append(f"⚠️ 𝙎𝙞𝙩𝙚 𝘼𝙡𝙧𝙚𝙖𝙙𝙮 𝙀𝙭𝙞𝙨𝙩: {dup_site}")
    
    # Add total count if any new sites were added
    if new_sites_added:
        response_lines.append(f"\n📊 𝙏𝙤𝙩𝙖𝙡 𝙎𝙞𝙩𝙚𝙨: {len(current_sites)}")
    
    # Send response — for many sites, send a compact summary instead of
    # one giant message (Telegram silently drops messages > 4096 chars,
    # which is why bulk /add looked like "nothing happened").
    added_count = len(new_sites_added)
    dup_count = len(duplicate_sites)

    if added_count + dup_count > 20 or len("\n".join(response_lines)) > 3500:
        summary_lines = [
            f"✅ <b>𝘼𝙙𝙙𝙚𝙙:</b> {added_count} site(s)",
        ]
        if dup_count:
            summary_lines.append(f"⚠️ <b>𝘿𝙪𝙥𝙡𝙞𝙘𝙖𝙩𝙚:</b> {dup_count} site(s)")
        if added_count:
            summary_lines.append(f"📊 <b>𝙏𝙤𝙩𝙖𝙡 𝙎𝙞𝙩𝙚𝙨:</b> {len(current_sites)}")
        await update.message.reply_text(
            "\n".join(summary_lines),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    if response_lines:
        final_message = "\n".join(response_lines)
        # Safety: chunk if still too long
        if len(final_message) > 4000:
            chunks = []
            cur = ""
            for line in response_lines:
                if len(cur) + len(line) + 1 > 4000:
                    chunks.append(cur)
                    cur = line
                else:
                    cur = (cur + "\n" + line) if cur else line
            if cur:
                chunks.append(cur)
            for chunk in chunks:
                await update.message.reply_text(
                    chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True
                )
        else:
            await update.message.reply_text(
                final_message, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )
    else:
        await update.message.reply_text("❌ No valid sites provided.")

# Alias for backward compatibility
add = add_command
