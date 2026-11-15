# tools/cmds.py
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler

from utils.styled_buttons import styled_button

logger = logging.getLogger(__name__)

# ===== GATEWAY COMMANDS (name, command, type) =====
GATE_COMMANDS = [
    ("Single Stripe Auth", "/chk", "Free"),
    ("Stripe Auth V2", "/sr", "Free"),
    ("Braintree Auth", "/b3", "Free"),
    ("Braintree Charge", "/bc", "Free"),
    ("Mass Stripe Auth", "/mass", "Free"),
    ("Mass Stripe SK", "/sktxt", "Premium"),
    ("Mass Stripe (chktxt)", "/chktxt", "Free"),
    ("Razorpay Charge", "/rz", "Free"),
    ("Razorpay Mass", "/mrz", "Free"),
    ("Razorpay Sites List", "/rzsite", "Admin"),
    ("Razorpay Add Sites (Owner)", "/addrz", "Owner"),
    ("Razorpay Remove Site (Owner)", "/rmrz", "Owner"),
    ("Razorpay Wipe Sites (Owner)", "/rmrzall", "Owner"),
    ("PayPal 1$", "/pp", "Free"),
    ("PayPal 0.01$", "/pc", "Free"),
    ("Mass PayPal", "/masspp", "Premium"),
    ("Shopify Charge", "/sh", "Free"),
    ("Mass Shopify", "/msh", "Free"),
    ("SK-Based $1", "/cc", "Free"),
    ("SK-Based $5", "/su", "Free"),
    ("Stripe 1$", "/st", "Free"),
    ("Stripe 5$", "/st1", "Free"),    
    ("SK Key Check", "/sk", "Free"),
]

# ===== TOOLS COMMANDS (name, command, type) =====
TOOLS_COMMANDS = [
    ("Cc Clean", "/clean", "Free"),
    ("Fill Spliter", "/split", "Free"),  
    ("Random Card Pick", "/pick", "Free"),     
    ("Add Proxy", "/addpxy", "Free"),       
    ("Remove Proxy", "/rmpxy", "Free"),     
    ("Check Your Added Proxy", "/mypxy", "Free"),               
    ("BIN Lookup", "/bin", "Free"),
    ("Fake Identity", "/fk", "Free"),
    ("Generate Cards", "/gen", "Free"),
    ("Extract from Dump", "/fl", "Free"),
    ("Extract from File", "/open", "Free"),
    ("3DS Lookup", "/vbv", "Free"),
    ("Gateway Checker", "/gate", "Free"),
    ("Mass Gateway Check", "/mgate", "Free"),
    ("Scraper", "/scr", "Free"),
    ("Multi Scraper", "/mc", "Free"),
    ("Clean CCs", "/clean", "Free"),
    ("Add Shopify Site", "/add", "Free"),
    ("Check Sites", "/check", "Free"),
    ("My Sites", "/show", "Free"),
    ("Remove Site", "/rm", "Free"),
    ("Remove All Sites", "/removeall", "Free"),
    ("Show Sites", "/show", "Free"),
    ("Redeem Code", "/redeem", "Free"),
    ("Plan Details", "/plan", "Free"),
    ("User Info", "/info", "Free"),
    ("Credits", "/credits", "Free"),
    ("Bot Status", "/status", "Free"),
    ("All Commands", "/cmds", "Free"),
]

# Combined list
ALL_COMMANDS = GATE_COMMANDS + TOOLS_COMMANDS
PAGE_SIZE = 4

# Hidden from /cmds menu for non-admin users
ADMIN_ONLY_TYPES = {"Admin"}
# Always hidden from /cmds menu (even for owner/admin)
ALWAYS_HIDDEN_TYPES = {"Owner"}


def _filter_for_user(is_admin: bool):
    base = [c for c in ALL_COMMANDS if c[2] not in ALWAYS_HIDDEN_TYPES]
    if is_admin:
        return base
    return [c for c in base if c[2] not in ADMIN_ONLY_TYPES]


def _pages_for(is_admin: bool):
    cmds = _filter_for_user(is_admin)
    return [cmds[i:i + PAGE_SIZE] for i in range(0, len(cmds), PAGE_SIZE)]


# Default pages (non-admin view) for backwards compat
PAGES = _pages_for(False)


def build_page_text(page_index: int, is_admin: bool = False) -> str:
    """Build text for commands page with dynamic header and proper type display"""
    try:
        pages = _pages_for(is_admin)
        page_commands = pages[page_index]

        first_cmd_cmd = page_commands[0][1]
        is_gate = any(first_cmd_cmd == cmd for _, cmd, _ in GATE_COMMANDS)
        header = "🚪 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 𝘾𝙤𝙢𝙢𝙖𝙣𝙙𝙨" if is_gate else "🛠️ 𝙏𝙤𝙤𝙡𝙨 𝘾𝙤𝙢𝙢𝙖𝙣𝙙𝙨"

        text = "━━━━━━━━━━━━━━━━━━━━━━\n"
        text += f"{header} [{page_index + 1}/{len(pages)}]\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━\n"

        for name, cmd, cmd_type in page_commands:
            text += f"<b><i>Name:</i></b> <i>{html.escape(name)}</i>\n"
            text += f"<b><i>Use:</i></b> <i>{html.escape(cmd)}</i>\n"
            text += f"<b><i>Type:</i></b> <i>{cmd_type}</i>\n"
            text += "━━━━━━━━━━━━━━━━━━━━━━\n"

        return text.strip()
    except Exception as e:
        logger.error(f"Error building page text: {e}")
        return "Error: Could not build page text."


def build_cmds_buttons(page_index: int, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Build buttons for commands pagination — Back & Next stay green, the
    centre counter is always blue."""
    total_pages = len(_pages_for(is_admin))
    nav_row = []

    if page_index > 0:
        nav_row.append(
            styled_button(
                "⬅️ Back",
                callback_data=f"page_{page_index - 1}",
                color="green",
                icon="",
            )
        )

    nav_row.append(
        styled_button(
            f"[{page_index + 1}/{total_pages}]",
            callback_data="noop",
            color="blue",
        )
    )

    if page_index < total_pages - 1:
        nav_row.append(
            styled_button(
                "➡️ Next",
                callback_data=f"page_{page_index + 1}",
                color="green",
                icon="",
            )
        )

    return InlineKeyboardMarkup([nav_row])


async def cmds_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the first page of commands"""
    try:
        from config import OWNER_ID, ADMIN_IDS
        uid = update.effective_user.id
        is_admin = uid == OWNER_ID or uid in ADMIN_IDS
    except Exception:
        is_admin = False
    text = build_page_text(0, is_admin=is_admin)
    buttons = build_cmds_buttons(0, is_admin=is_admin)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=buttons
    )


async def cmds_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pagination for /cmds command"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("page_"):
        try:
            page_index = int(data.split("_")[1])
            try:
                from config import OWNER_ID, ADMIN_IDS
                uid = query.from_user.id
                is_admin = uid == OWNER_ID or uid in ADMIN_IDS
            except Exception:
                is_admin = False
            text = build_page_text(page_index, is_admin=is_admin)
            buttons = build_cmds_buttons(page_index, is_admin=is_admin)
            await query.message.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                reply_markup=buttons
            )
        except Exception as e:
            logger.error(f"Error in pagination: {e}")
    
    elif data == "noop":
        # Do nothing – middle button just shows page number
        pass


async def handle_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close button handler – not used but kept for compatibility"""
    query = update.callback_query
    await query.answer()
    await query.message.delete()
