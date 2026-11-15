# admin/broadcast.py
import asyncio
import time
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.error import Forbidden, BadRequest
from db import get_all_users
from config import OWNER_ID

logger = logging.getLogger(__name__)

# Store broadcast state for owner
broadcast_states = {}

async def broad_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start broadcast process"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ 𝙔𝙤𝙪 𝙖𝙧𝙚 𝙣𝙤𝙩 𝙖𝙪𝙩𝙝𝙤𝙧𝙞𝙯𝙚𝙙 𝙩𝙤 𝙪𝙨𝙚 𝙩𝙝𝙞𝙨 𝙘𝙤𝙢𝙢𝙖𝙣𝙙.")
        return
    
    user_id = update.effective_user.id
    broadcast_states[user_id] = {'step': 'waiting_for_message'}
    
    await update.message.reply_text(
        "📢 *BROADCAST SYSTEM*\n\n"
        "Send me the message you want to broadcast:\n"
        "(Text, photo, video, document, etc.)\n\n"
        "Type `/cancel` to stop",
        parse_mode="Markdown"
    )

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages when owner is in broadcast mode"""
    user_id = update.effective_user.id
    
    logger.info(f"broadcast_message_handler called for user {user_id}")
    
    if user_id not in broadcast_states:
        logger.info(f"User {user_id} not in broadcast mode")
        return
    
    current_state = broadcast_states[user_id]
    
    if update.message.text:
        text = update.message.text.strip().lower()
        if text == '/cancel' or text == 'cancel':
            del broadcast_states[user_id]
            await update.message.reply_text("❌ Broadcast cancelled.")
            return
    
    if current_state['step'] == 'waiting_for_message':
        message_to_broadcast = update.message
        broadcast_states[user_id] = {
            'step': 'confirmation',
            'message': message_to_broadcast,
            'message_id': update.message.message_id,
            'chat_id': update.effective_chat.id
        }
        
        logger.info(f"Message received, showing preview")
        
        preview = ""
        if message_to_broadcast.text:
            text = message_to_broadcast.text
            if len(text) > 200:
                text = text[:200] + "..."
            preview = f"📝 *Text Message:*\n\n{text}"
        elif message_to_broadcast.caption:
            caption = message_to_broadcast.caption
            if len(caption) > 200:
                caption = caption[:200] + "..."
            media_type = message_to_broadcast.content_type.upper()
            preview = f"📸 *{media_type} with Caption:*\n\n{caption}"
        else:
            media_type = message_to_broadcast.content_type.upper()
            preview = f"📁 *{media_type} File*"
        
        await update.message.reply_text(
            f"{preview}\n\n"
            "✅ *Send this to all users?*\n\n"
            "Click below to confirm:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ YES, SEND TO ALL", callback_data="broadcast_confirm")],
                [InlineKeyboardButton("❌ NO, CANCEL", callback_data="broadcast_cancel")]
            ])
        )
    else:
        logger.warning(f"Unexpected state: {current_state['step']}")

async def handle_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast callback buttons"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    logger.info(f"BROADCAST CALLBACK PROCESSING: {data} from {user_id}")
    
    if user_id != OWNER_ID:
        logger.warning(f"Non-owner tried to use broadcast: {user_id}")
        await query.answer("❌ Owner only.", show_alert=True)
        return
    
    if data == "broadcast_confirm":
        await query.answer("Starting broadcast...")
        await process_broadcast_confirmation(query, context)
    
    elif data == "broadcast_cancel":
        await query.answer("Broadcast cancelled")
        await query.edit_message_text("❌ Broadcast cancelled.")
        if user_id in broadcast_states:
            del broadcast_states[user_id]
    
    else:
        logger.warning(f"Unexpected broadcast callback: {data}")
        await query.answer("Unknown broadcast action", show_alert=False)

async def process_broadcast_confirmation(query, context):
    """Process broadcast confirmation"""
    user_id = query.from_user.id
    
    if user_id not in broadcast_states or broadcast_states[user_id]['step'] != 'confirmation':
        await query.edit_message_text("❌ Session expired. Start again with `/broad`")
        return
    
    message_info = broadcast_states[user_id]
    
    await query.edit_message_text("🚀 *Starting broadcast...*", parse_mode="Markdown")
    
    try:
        users = await get_all_users()
        total_users = len(users)
        logger.info(f"Starting broadcast to {total_users} users")
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        await query.edit_message_text(f"❌ Error getting users: {str(e)[:100]}")
        return
    
    if total_users == 0:
        await query.edit_message_text("❌ No users found.")
        return
    
    sent = 0
    blocked = 0
    failed = 0
    
    progress_msg = await query.edit_message_text(
        f"📤 *Broadcast Progress*\n"
        f"──────────────\n"
        f"👥 Total Users: `{total_users}`\n"
        f"✅ Sent: `0`\n"
        f"🚫 Blocked: `0`\n"
        f"❌ Failed: `0`\n"
        f"⏱️ Progress: `0%`",
        parse_mode="Markdown"
    )
    
    start_time = time.time()
    
    for i, user in enumerate(users, 1):
        user_id_to_send = user.get("id") or user.get("user_id")
        
        if not user_id_to_send:
            continue
        
        try:
            await context.bot.forward_message(
                chat_id=user_id_to_send,
                from_chat_id=message_info['chat_id'],
                message_id=message_info['message_id']
            )
            sent += 1
            
        except Forbidden:
            blocked += 1
        except Exception as e:
            failed += 1
            logger.debug(f"Failed to send to {user_id_to_send}: {e}")
        
        if i % 10 == 0 or i == total_users:
            progress = (i / total_users) * 100
            elapsed = time.time() - start_time
            
            try:
                await progress_msg.edit_text(
                    f"📤 *Broadcast Progress*\n"
                    f"──────────────\n"
                    f"👥 Total Users: `{total_users}`\n"
                    f"✅ Sent: `{sent}`\n"
                    f"🚫 Blocked: `{blocked}`\n"
                    f"❌ Failed: `{failed}`\n"
                    f"⏱️ Progress: `{progress:.1f}%`\n"
                    f"⏰ Time: `{elapsed:.1f}s`",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        await asyncio.sleep(0.05)
    
    elapsed = time.time() - start_time
    success_rate = (sent / total_users * 100) if total_users > 0 else 0
    
    await progress_msg.edit_text(
        f"✅ *BROADCAST COMPLETE!*\n"
        f"──────────────\n"
        f"📊 *Statistics:*\n"
        f"👥 Total Users: `{total_users}`\n"
        f"✅ Successfully Sent: `{sent}`\n"
        f"🚫 Blocked/Deleted: `{blocked}`\n"
        f"❌ Failed: `{failed}`\n"
        f"📈 Success Rate: `{success_rate:.1f}%`\n"
        f"⏰ Time Taken: `{elapsed:.1f} seconds`\n\n"
        f"🔄 Use `/broad` again to send another message",
        parse_mode="Markdown"
    )
    
    if user_id in broadcast_states:
        del broadcast_states[user_id]
    
    logger.info(f"Broadcast completed: {sent}/{total_users} users in {elapsed:.1f}s")

async def filter_owner_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Filter messages from owner for broadcast system"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
    
    if user_id in broadcast_states:
        logger.info(f"Owner {user_id} in broadcast mode, processing message")
        await broadcast_message_handler(update, context)

def register_broadcast_handlers(application):
    """Register all broadcast handlers"""
    logger.info("Registering broadcast handlers...")
    
    application.add_handler(CommandHandler("broad", broad_command))
    
    application.add_handler(
        MessageHandler(
            filters.ALL & filters.ChatType.PRIVATE & ~filters.COMMAND,
            filter_owner_messages
        ),
        group=2
    )
    
    logger.info("Broadcast handlers registered successfully")