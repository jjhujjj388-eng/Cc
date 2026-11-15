# gates/sk.py
#!/usr/bin/env python3
"""
Stripe SK Checker Telegram Bot
For use with main.py bot
"""

import asyncio
import aiohttp
import json
import base64
import re
import time
import logging
from html import escape

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Cooldown system for sk.py ---
user_last_command_time = {}

async def enforce_cooldown(user_id, update_obj=None, cooldown_seconds=5):
    """Simple async cooldown check for sk.py"""
    current_time = time.time()
    last_time = user_last_command_time.get(user_id, 0)
    
    if current_time - last_time < cooldown_seconds:
        remaining = cooldown_seconds - (current_time - last_time)
        if update_obj:
            await update_obj.message.reply_text(f"⏳ Please wait {remaining:.1f}s before using /sk again.")
        return False
    
    user_last_command_time[user_id] = current_time
    return True

# --- Helper Functions ---
async def send_telegram_message(chat_id, text, parse_mode='HTML'):
    """Send message via Telegram Bot API"""
    pass

# --- Core SK Check Logic ---
## logic apna daal
# --- Main SK Command Function ---
async def sk_command(update, context):
    """SK Checker - Check Stripe Secret Key"""
    user = update.effective_user
    
    if not await enforce_cooldown(user.id, update):
        return
    
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>Stripe SK Checker</b>\n\n"
            "Usage: <code>/sk your_sk_key_here</code>\n\n"
            "Example: /sk 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",
            parse_mode='HTML'
        )
        return
    
    sk_key = " ".join(context.args).strip()
    
    if not sk_key.startswith("sk_"):
        await update.message.reply_text(
            "❌ <b>Invalid SK format!</b>\n\n"
            "SK key should start with <code>sk_</code>\n"
            "Example: <code>sk_live_...</code>",
            parse_mode='HTML'
        )
        return
    
    await process_sk_check(update, context, sk_key)

async def process_sk_check(update, context, sk_key: str):
    """Process SK key check"""
    start_time = time.time()
    processing_msg = None
    
    try:
        processing_text = (
            f"<b>🔍 Checking Stripe SK Key...</b>\n"
            f"<code>{escape(sk_key[:30])}...</code>"
        )
        
        processing_msg = await update.message.reply_text(
            processing_text,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        
        headers = {"Authorization": f"Bearer {sk_key}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.stripe.com/v1/account",
                headers=headers,
                timeout=20
            ) as resp:
                account_data = await resp.json()
        
        if 'error' in account_data:
            error_msg = account_data['error']['message']
            await processing_msg.edit_text(
                f"❌ <b>Invalid SK Key:</b>\n<code>{escape(error_msg)}</code>",
                parse_mode='HTML'
            )
            return
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.stripe.com/v1/balance",
                headers=headers,
                timeout=20
            ) as resp:
                balance_data = await resp.json()
        
        pk = await extract_pk_from_checkout(sk_key)
        
        integration = "Off"
        if 'capabilities' in account_data and 'card_payments' in account_data['capabilities']:
            integration = "On" if account_data['capabilities']['card_payments'] == 'active' else "Off"
        
        card_payment = "Inactive"
        if ('settings' in account_data and 'payments' in account_data['settings']) or \
           ('capabilities' in account_data and 'card_payments' in account_data['capabilities']):
            card_payment = "Active"
        
        avail_bal = 0
        pend_bal = 0
        currency = account_data.get('default_currency', 'USD').upper()
        
        if 'available' in balance_data:
            for b in balance_data['available']:
                avail_bal += b['amount']
        
        if 'pending' in balance_data:
            for b in balance_data['pending']:
                pend_bal += b['amount']
        
        business_profile = account_data.get('business_profile', {})
        business_name = business_profile.get('name', 'N/A')
        business_url = business_profile.get('url', 'N/A')
        support_phone = business_profile.get('support_phone', 'N/A')
        
        bullet_link = '<a href="https://t.me/chargegod">⊀</a>'
        developer_clickable = '<a href="tg://resolve?domain=DarkCarder05">𝘽𝙡𝙖𝙘𝙠𝙓𝘾𝙖𝙧𝙙™</a>'
        
        response = f"<b>✅ Stripe SK Key Details</b>\n\n"
        response += f"{bullet_link} <b>SK:</b> <code>{escape(sk_key)}</code>\n"
        response += f"{bullet_link} <b>PK:</b> <code>{escape(pk)}</code>\n\n"
        
        response += f"{bullet_link} <b>Integration:</b> <code>{integration}</code>\n"
        response += f"{bullet_link} <b>Card Payments:</b> <code>{card_payment}</code>\n\n"
        
        response += f"{bullet_link} <b>Business:</b> {escape(business_name)}\n"
        response += f"{bullet_link} <b>URL:</b> {escape(business_url)}\n"
        response += f"{bullet_link} <b>Email:</b> {escape(account_data.get('email', 'N/A'))}\n"
        response += f"{bullet_link} <b>Phone:</b> {escape(support_phone)}\n"
        response += f"{bullet_link} <b>Country:</b> {account_data.get('country', 'N/A')}\n"
        response += f"{bullet_link} <b>Currency:</b> {currency}\n\n"
        
        response += f"{bullet_link} <b>Available Balance:</b> {avail_bal / 100} {currency}\n"
        response += f"{bullet_link} <b>Pending Balance:</b> {pend_bal / 100} {currency}\n\n"
        
        elapsed_time = round(time.time() - start_time, 2)
        response += f"{bullet_link} <b>DEV:</b> {developer_clickable}\n"
        response += f"{bullet_link} <b>Time:</b> {elapsed_time}s"
        
        await processing_msg.edit_text(
            response,
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.exception(f"Error in SK check: {e}")
        try:
            if processing_msg:
                await processing_msg.edit_text(
                    f"❌ Error: <code>{escape(str(e))}</code>",
                    parse_mode='HTML'
                )
        except Exception:
            pass

# --- For standalone testing ---
if __name__ == "__main__":
    print("This file is meant to be imported by main.py")
    print("Run main.py instead")