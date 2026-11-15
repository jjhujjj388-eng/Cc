# group/welcome.py
"""
Welcome New Members with Random GIF/Video
Triggered when new members join a group.
"""

import random
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, MessageHandler, filters

logger = logging.getLogger(__name__)

# ===== WELCOME GIF LIST =====
welcome_gif = [
    "https://telegra.ph/file/a5a2bb456bf3eecdbbb99.mp4",
    "https://telegra.ph/file/03c6e49bea9ce6c908b87.mp4",
    "https://telegra.ph/file/9ebf412f09cd7d2ceaaef.mp4",
    "https://telegra.ph/file/293cc10710e57530404f8.mp4",
    "https://telegra.ph/file/506898de518534ff68ba0.mp4",
    "https://telegra.ph/file/dae0156e5f48573f016da.mp4",
    "https://telegra.ph/file/3e2871e714f435d173b9e.mp4",
    "https://telegra.ph/file/714982b9fedfa3b4d8d2b.mp4",
    "https://telegra.ph/file/876edfcec678b64eac480.mp4",
    "https://telegra.ph/file/6b1ab5aec5fa81cf40005.mp4",
    "https://telegra.ph/file/b4834b434888de522fa49.mp4",
]

# ===== WELCOME MESSAGE (SAME AS ORIGINAL) =====
MESSAGE = """👋 𝙃𝙚𝙮 {name}!
𝑾𝒆𝒍𝒄𝒐𝒎𝒆 𝑻𝒐 𝑶𝒖𝒓 𝑮𝒓𝒐𝒖𝒑 ❤️

📜 𝙋𝙡𝙚𝙖𝙨𝙚 𝙛𝙤𝙡𝙡𝙤𝙬 𝙨𝙤𝙢𝙚 𝙧𝙪𝙡𝙚𝙨:
1. 🚫 𝘋𝘰𝘯'𝘵 𝘴𝘦𝘯𝘥 𝘶𝘯𝘸𝘢𝘯𝘵𝘦𝘥 𝘭𝘪𝘯𝘬𝘴.
2. 🚫 𝘋𝘰𝘯'𝘵 𝘴𝘱𝘢𝘮.
3. 🚫 𝘗𝘳𝘰𝘮𝘰𝘵𝘪𝘰𝘯 𝘰𝘧 𝘺𝘰𝘶𝘳 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝘪𝘴 𝘱𝘳𝘰𝘩𝘪𝘣𝘪𝘵𝘦𝘥.

✅ 𝙅𝙪𝙨𝙩 𝙥𝙧𝙚𝙨𝙨 /start 𝙤𝙣𝙘𝙚 𝙩𝙤 𝙘𝙤𝙣𝙩𝙞𝙣𝙪𝙚 𝙪𝙨𝙞𝙣𝙜 𝙢𝙚 👀  
"""


async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends a random welcome video when new members join the group.
    """
    # Check if update has new chat members
    if not update.message or not update.message.new_chat_members:
        return

    try:
        # Get list of new members and create mention string
        new_members = update.message.new_chat_members
        names = ", ".join([u.mention_html() for u in new_members])

        # Format the welcome message
        text = MESSAGE.format(name=names)

        # Pick a random video
        video_url = random.choice(welcome_gif)

        # Send video as reply to the join message (v20+ compatible)
        await update.message.reply_video(
            video=video_url,
            caption=text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=update.message.message_id  # ✅ v20+ compatible
        )

        logger.info(f"Welcomed {len(new_members)} new member(s) in {update.effective_chat.id}")

    except Exception as e:
        logger.error(f"Error in welcome handler: {e}")


def register_welcome_handler(application):
    """
    Register the welcome handler for new chat members.
    """
    welcome_filter = filters.StatusUpdate.NEW_CHAT_MEMBERS
    application.add_handler(
        MessageHandler(welcome_filter, welcome_new_members)
    )
    logger.info("✅ Welcome handler registered for new members")