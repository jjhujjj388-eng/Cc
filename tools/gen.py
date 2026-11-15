# tools/gen.py
# /gen command - Using Dr.Lab API (Fixed JSON parsing)

import re
import io
import aiohttp
import asyncio
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user, update_user
from bin import get_bin_info
from utils.decorators import enforce_cooldown
from utils.credits import consume_credit
from force_join import force_join

API_URL = "https://drlabapis.onrender.com/api/ccgenerator"

@force_join
async def gen_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates cards from a given BIN using Dr.Lab API."""
    
    user = update.effective_user
    
    # Enforce cooldown
    if not await enforce_cooldown(user.id, update):
        return
    
    # Get user data and check credits
    user_data = await get_user(user.id)
    if not user_data or user_data.get('credits', 0) <= 0:
        return await update.effective_message.reply_text(
            "❌ You have no credits left. Please get a subscription to use this command.",
            parse_mode=ParseMode.HTML
        )
    
    # Get input
    if not context.args:
        return await update.effective_message.reply_text(
            "❌ Please provide BIN (at least 6 digits).\n"
            "Usage:\n<code>/gen 414740</code> - 10 cards\n<code>/gen 414740 20</code> - 20 cards",
            parse_mode=ParseMode.HTML
        )
    
    bin_number = context.args[0].strip()
    if not bin_number.isdigit() or len(bin_number) < 6:
        return await update.effective_message.reply_text(
            "❌ BIN must be at least 6 digits.",
            parse_mode=ParseMode.HTML
        )
    
    # Determine number of cards
    num_cards = 10  # default
    if len(context.args) > 1 and context.args[1].isdigit():
        num_cards = int(context.args[1])
        if num_cards > 100:  # Limit max cards
            num_cards = 100
    
    # Consume 1 credit
    if not await consume_credit(user.id):
        return await update.effective_message.reply_text(
            "❌ You have no credits left. Please get a subscription to use this command.",
            parse_mode=ParseMode.HTML
        )
    
    # Show processing message
    processing = await update.effective_message.reply_text(
        f"⏳ Generating {num_cards} cards for BIN {bin_number}...",
        parse_mode=ParseMode.HTML
    )
    
    # Call API
    try:
        async with aiohttp.ClientSession() as session:
            api_url = f"{API_URL}?bin={bin_number}&count={num_cards}"
            async with session.get(api_url, timeout=30) as response:
                if response.status != 200:
                    await processing.edit_text(
                        f"❌ API Error: Status {response.status}",
                        parse_mode=ParseMode.HTML
                    )
                    return
                
                # 🔥 FIX: Get text directly, not JSON
                text_response = await response.text()
                
    except asyncio.TimeoutError:
        await processing.edit_text(
            "❌ API request timed out.",
            parse_mode=ParseMode.HTML
        )
        return
    except Exception as e:
        await processing.edit_text(
            f"❌ Error: {str(e)}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # 🔥 Parse the text response (each line is a card)
    cards = [line.strip() for line in text_response.strip().split('\n') if line.strip()]
    
    if not cards:
        await processing.edit_text(
            "❌ No cards generated.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Delete processing message
    await processing.delete()
    
    # Fetch BIN info for display
    try:
        bin_details = await get_bin_info(bin_number[:6])
        brand = (bin_details.get("scheme") or "N/A").title()
        issuer = bin_details.get("bank") or "N/A"
        country_name = bin_details.get("country") or "N/A"
        card_type = bin_details.get("type", "N/A")
        card_level = bin_details.get("level", "N/A")
    except:
        brand = issuer = country_name = card_type = card_level = "N/A"
    
    # BIN info block
    bin_info = (
        f"<pre>"
        f"BIN       ➳ {bin_number}\n"
        f"Brand     ➳ {brand}\n"
        f"Type      ➳ {card_type} | {card_level}\n"
        f"Bank      ➳ {issuer}\n"
        f"Country   ➳ {country_name}\n"
        f"</pre>"
    )
    
    # Send output
    if len(cards) > 20:
        # Send as file
        file_content = "\n".join(cards)
        file = io.BytesIO(file_content.encode('utf-8'))
        file.name = f"generated_cards_{bin_number}_{len(cards)}.txt"
        await update.effective_message.reply_document(
            document=file,
            caption=f"<pre>Generated {len(cards)} cards 💳</pre>\n\n{bin_info}",
            parse_mode=ParseMode.HTML
        )
    else:
        # Show in message
        cards_list = "\n".join(f"<code>{c}</code>" for c in cards)
        final_message = (
            f"<pre>Generated {len(cards)} cards 💳</pre>\n\n"
            f"{cards_list}\n\n"
            f"{bin_info}"
        )
        await update.effective_message.reply_text(
            final_message,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )