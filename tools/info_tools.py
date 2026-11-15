# tools/info_tools.py
import re
import time
import psutil
import platform
import socket
from datetime import datetime
from html import escape
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user, get_all_users
from config import OWNER_ID, ADMIN_IDS, BULLET_GROUP_LINK, DEVELOPER_NAME, DEVELOPER_LINK
from utils.credits import format_credits, is_unlimited
from utils.decorators import enforce_cooldown
from utils.helpers import escape_html, escape_markdown_v2
from utils.bullet import get_bullet_link, get_bullet2_link, get_developer_mention, get_user_mention, get_user_role
from force_join import force_join

# ===== /cmds COMMAND =====
ALL_COMMANDS = [
    ("Stripe 1$", "/st"),
    ("Stripe 5$", "/st1"),
    ("Single Stripe Auth", "/chk"),
    ("Mass x30 Stripe Auth 2", "/mass"),
    ("Authnet 2.5$ Charge", "/at"),
    ("Adyen 1.0$ Charge", "/ad"),
    ("Paypal 1$", "/pp"),    
    ("Paypal Payments 9$", "/py"),
    ("3DS Lookup", "/vbv"),
    ("Shopify Charge $0.98", "/sh"),
    ("Shopify Charge $10", "/hc"),
    ("Razorpay charge 1₹", "/rz"),
    ("Set your Shopify site", "/add"),
    ("Auto check on your site", "/sh"),
    ("Mass Shopify Charged", "/msp"),
    ("Check if Shopify site is live", "/check"),
    ("Mass Shopify site check", "/msite"),
    ("Check your added sites", "/mysites"),
    ("Remove all added sites", "/removeall"),
    ("Remove specific sites", "/rsite"),
    ("Generate cards from BIN", "/gen"),
    ("Payment Gateway Checker", "/gate"),
    ("BIN lookup", "/bin"),
    ("Fake identity generator", "/fk"),
    ("Extract CCs from dumps", "/fl"),
    ("Extract cards from file", "/open"),
    ("Redeem a bot code", "/redeem"),
    ("Welcome message", "/start"),
    ("Show all commands", "/cmds"),
    ("Bot system status", "/status"),
    ("Check your remaining credits", "/credits"),
    ("Show your user info", "/info")
]

PAGE_SIZE = 4
PAGES = [ALL_COMMANDS[i:i + PAGE_SIZE] for i in range(0, len(ALL_COMMANDS), PAGE_SIZE)]

def build_page_text(page_index: int) -> str:
    try:
        page_commands = PAGES[page_index]
        text = "━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"<i>◆ 𝐂𝐌𝐃𝐒 𝐏𝐀𝐆𝐄 {page_index + 1}/{len(PAGES)}</i>\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        for name, cmd in page_commands:
            text += f"<b><i>Name:</i></b> <i>{escape_html(name)}</i>\n"
            text += f"<b><i>Use:</i></b> <i>{escape_html(cmd)}</i>\n"
            text += f"<b><i>Status:</i></b> <i>Online ✅</i>\n"
            text += f"<b><i>Type:</i></b> <i>Free/Premium</i>\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━\n"
        return text.strip()
    except Exception as e:
        return "Error: Could not build page text."

def build_cmds_buttons(page_index: int) -> InlineKeyboardMarkup:
    buttons = []
    nav_buttons = []
    if page_index > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Back", callback_data=f"page_{page_index - 1}"))
    if page_index < len(PAGES) - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"page_{page_index + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close")])
    return InlineKeyboardMarkup(buttons)

@force_join
async def cmds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = build_page_text(0)
    buttons = build_cmds_buttons(0)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=buttons
    )

# ===== /info COMMAND =====
@force_join
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the user's detailed information."""
    user = update.effective_user
    user_data = await get_user(user.id)

    bullet_link = get_bullet_link()
    bullet2_link = get_bullet2_link()
    dev_mention = get_developer_mention()
    user_mention = get_user_mention(user)

    first_name = escape_html(user.first_name or 'N/A')
    user_id = str(user.id)
    username = escape_html(user.username or 'N/A')
    is_owner = user.id == OWNER_ID
    is_admin = user.id in ADMIN_IDS
    if is_owner:
        status = "Owner"
        plan = "Owner"
    elif is_admin:
        status = "Admin"
        plan = escape_html(user_data.get('plan', 'N/A'))
    else:
        status = escape_html(user_data.get('status', 'N/A'))
        plan = escape_html(user_data.get('plan', 'N/A'))
    credits = format_credits(user.id, user_data.get('credits', 0))
    plan_expiry = "∞" if is_unlimited(user.id) else escape_html(user_data.get('plan_expiry', 'N/A'))
    keys_redeemed = str(user_data.get('keys_redeemed', 0))
    registered_at = escape_html(user_data.get('registered_at', 'N/A'))

    info_message = (
        f"{bullet_link} 🔍 <b>Your Info on 𝑺𝒑𝒂𝒄𝒆 𝑪𝒉𝒌</b> ⚡\n"
        f"━━━━━━━━━━━━━━\n"
        f"{bullet_link}  𝙁𝙞𝙧𝙨𝙩 𝙉𝙖𝙢𝙚: <code>{first_name}</code>\n"
        f"{bullet_link}  𝙄𝘿: <code>{user_id}</code>\n"
        f"{bullet_link}  𝙐𝙨𝙚𝙧𝙣𝙖𝙢𝙚: {username}\n\n"
        f"{bullet_link}  𝙎𝙩𝙖𝙩𝙪𝙨: <code>{status}</code>\n"
        f"{bullet_link}  𝘾𝙧𝙚𝙙𝙞𝙩: <code>{credits}</code>\n"
        f"{bullet_link}  𝙋𝙡𝙖𝙣: <code>{plan}</code>\n"
        f"{bullet_link}  𝙋𝙡𝙖𝙣 𝙀𝙭𝙥𝙞𝙧𝙮: <code>{plan_expiry}</code>\n"
        f"{bullet_link}  𝙆𝙚𝙮𝙨 𝙍𝙚𝙙𝙚𝙚𝙢𝙚𝙙: <code>{keys_redeemed}</code>\n"
        f"{bullet_link}  𝙍𝙚𝙜𝙞𝙨𝙩𝙚𝙧𝙚𝙙 𝘼𝙩: <code>{registered_at}</code>\n\n"
        f"{bullet2_link} 𝘿𝙀𝙑 ↣ {dev_mention}"
    )

    await update.message.reply_text(
        info_message,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# ===== /credits COMMAND =====
@force_join
async def credits_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows user's credits."""
    user = update.effective_user
    user_data = await get_user(user.id)

    bullet_link = get_bullet_link()

    credits = format_credits(user.id, user_data.get('credits', 0))
    plan = user_data.get('plan', 'N/A')
    username = f"@{user.username}" if user.username else "N/A"

    credit_message = (
        f"{bullet_link} 💳 <b>Your Credit Info</b> 💳\n"
        f"✦━━━━━━━━━━━━━━✦\n"
        f"{bullet_link} Username: {escape_html(username)}\n"
        f"{bullet_link} User ID: <code>{user.id}</code>\n"
        f"{bullet_link} Plan: <code>{escape_html(plan)}</code>\n"
        f"{bullet_link} Credits: <code>{credits}</code>\n"
    )

    await update.effective_message.reply_text(
        credit_message,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )

# ===== /status COMMAND =====
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows bot and VPS status."""
    bullet_link = get_bullet_link()

    cpu_usage = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count(logical=True)
    
    memory = psutil.virtual_memory()
    total_memory = memory.total / (1024 ** 3)
    used_memory = memory.used / (1024 ** 3)
    available_memory = memory.available / (1024 ** 3)
    memory_percent = memory.percent

    disk = psutil.disk_usage("/")
    total_disk = disk.total / (1024 ** 3)
    used_disk = disk.used / (1024 ** 3)
    free_disk = disk.free / (1024 ** 3)
    disk_percent = disk.percent

    hostname = socket.gethostname()
    os_name = platform.system()
    architecture = platform.machine()

    boot_time = psutil.boot_time()
    uptime_seconds = int(time.time() - boot_time)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days}d {hours:02}:{minutes:02}:{seconds:02}"

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    users = await get_all_users()
    total_users = len(users)

    status_message = (
        f"━━━━━[ 𝘽𝙤𝙩 𝘼𝙣𝙙 𝙑𝙥𝙨 𝙎𝙩𝙖𝙩𝙪𝙨 ]━━━━━\n"
        f"{bullet_link} 𝘚𝘵𝘢𝘵𝘶𝘴 ↭ <code>Active ✅</code>\n"
        f"{bullet_link} 𝘚𝘺𝘴𝘵𝘦𝘮 ↭ <code>{os_name}</code>\n"
        f"{bullet_link} 𝘈𝘳𝘤𝘩𝘪𝘵𝘦𝘤𝘵𝘶𝘳𝘦 ↭ <code>{architecture}</code>\n"
        "――――――――――――――――\n"
        f"{bullet_link} 𝘊𝘗𝘜 ↭ <code>{cpu_usage:.1f}% ({cpu_count} cores)</code>\n"
        f"{bullet_link} 𝘙𝘈𝘔 ↭ <code>{used_memory:.2f}GB / {total_memory:.2f}GB ({memory_percent:.1f}%)</code>\n"
        f"{bullet_link} 𝘋𝘐𝘚𝘒 ↭ <code>{used_disk:.2f}GB / {total_disk:.2f}GB ({disk_percent:.1f}%)</code>\n"
        "――――――――――――――――\n"
        f"{bullet_link} 𝘛𝘰𝘵𝘢𝘭 𝘜𝘴𝘦𝘳𝘴 ↭ <code>{total_users}</code>\n"
        f"{bullet_link} 𝘜𝘱𝘵𝘪𝘮𝘦 ↭ <code>{uptime_str}</code>\n"
        f"{bullet_link} 𝘋𝘦𝘷𝘦𝘭𝘰𝘱𝘦𝘳 ↭ {get_developer_mention()}\n"
        "――――――――――――――――"
    )

    await update.effective_message.reply_text(
        status_message,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )
