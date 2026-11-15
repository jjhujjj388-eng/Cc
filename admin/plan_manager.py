# admin/plan_manager.py
"""
New Plan Commands: Silver, Gold, Platinum, Diamond
Give commands: /give_silver, /give_gold, /give_platinum, /give_diamond
Gen commands:  /gen_silver, /gen_gold, /gen_platinum, /gen_diamond
Redeem command: /redeem (now uses MongoDB for persistence)
"""

import random
import string
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CommandHandler

from db import update_user, get_user, add_redeem_code, get_redeem_code, mark_code_used
from config import ADMIN_IDS, AUTHORIZED_PRIVATE_USERS

# Setup logger
logger = logging.getLogger(__name__)

# === PLAN DETAILS ===
PLANS = {
    "Silver":    {"credits": 500,  "days": 7},
    "Gold":      {"credits": 1500, "days": 15},
    "Platinum":  {"credits": 3000, "days": 30},
    "Diamond":   {"credits": 5000, "days": 60},
}

def generate_plan_code(plan_name: str) -> str:
    """Generate a redeem code: 𝘿𝘼𝙍𝙆𝙓-XXXXXX-YYYYYY-PLAN"""
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"DARKX-{part1}-{part2}-{plan_name.upper()}"

# ========== GIVE COMMANDS ==========
async def give_silver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 Admins only!")
    if not context.args or not context.args[0].isdigit():
        return await update.effective_message.reply_text("Usage: /give_silver <user_id>")
    user_id = int(context.args[0])
    expiry = datetime.now() + timedelta(days=7)
    await update_user(user_id, plan="Silver", status="Silver", credits=500, plan_expiry=expiry.strftime('%d-%m-%Y'))
    AUTHORIZED_PRIVATE_USERS.add(user_id)
    await update.effective_message.reply_text(f"✅ Silver plan given to {user_id} (500 credits, 7 days)")

async def give_gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 Admins only!")
    if not context.args or not context.args[0].isdigit():
        return await update.effective_message.reply_text("Usage: /give_gold <user_id>")
    user_id = int(context.args[0])
    expiry = datetime.now() + timedelta(days=15)
    await update_user(user_id, plan="Gold", status="Gold", credits=1500, plan_expiry=expiry.strftime('%d-%m-%Y'))
    AUTHORIZED_PRIVATE_USERS.add(user_id)
    await update.effective_message.reply_text(f"✅ Gold plan given to {user_id} (1500 credits, 15 days)")

async def give_platinum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 Admins only!")
    if not context.args or not context.args[0].isdigit():
        return await update.effective_message.reply_text("Usage: /give_platinum <user_id>")
    user_id = int(context.args[0])
    expiry = datetime.now() + timedelta(days=30)
    await update_user(user_id, plan="Platinum", status="Platinum", credits=3000, plan_expiry=expiry.strftime('%d-%m-%Y'))
    AUTHORIZED_PRIVATE_USERS.add(user_id)
    await update.effective_message.reply_text(f"✅ Platinum plan given to {user_id} (3000 credits, 30 days)")

async def give_diamond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 Admins only!")
    if not context.args or not context.args[0].isdigit():
        return await update.effective_message.reply_text("Usage: /give_diamond <user_id>")
    user_id = int(context.args[0])
    expiry = datetime.now() + timedelta(days=60)
    await update_user(user_id, plan="Diamond", status="Diamond", credits=5000, plan_expiry=expiry.strftime('%d-%m-%Y'))
    AUTHORIZED_PRIVATE_USERS.add(user_id)
    await update.effective_message.reply_text(f"✅ Diamond plan given to {user_id} (5000 credits, 60 days)")

# ========== GEN COMMANDS (NOW SAVE TO DB) ==========
async def gen_silver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 Admins only!")
    count = int(context.args[0]) if context.args else 1
    codes = []
    for _ in range(count):
        code = generate_plan_code("SILVER")
        await add_redeem_code(code, "Silver", 500, 7)
        codes.append(code)
    await update.effective_message.reply_text(
        f"<b><i>✅ Generated {count} Silver code(s):</i></b>\n" + "\n".join(f"<code>{c}</code>" for c in codes),
        parse_mode=ParseMode.HTML
    )

async def gen_gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 Admins only!")
    count = int(context.args[0]) if context.args else 1
    codes = []
    for _ in range(count):
        code = generate_plan_code("GOLD")
        await add_redeem_code(code, "Gold", 1500, 15)
        codes.append(code)
    await update.effective_message.reply_text(
        f"<b><i>✅ Generated {count} Gold code(s):</i></b>\n" + "\n".join(f"<code>{c}</code>" for c in codes),
        parse_mode=ParseMode.HTML
    )

async def gen_platinum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 Admins only!")
    count = int(context.args[0]) if context.args else 1
    codes = []
    for _ in range(count):
        code = generate_plan_code("PLATINUM")
        await add_redeem_code(code, "Platinum", 3000, 30)
        codes.append(code)
    await update.effective_message.reply_text(
        f"<b><i>✅ Generated {count} Platinum code(s):</i></b>\n" + "\n".join(f"<code>{c}</code>" for c in codes),
        parse_mode=ParseMode.HTML
    )

async def gen_diamond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 Admins only!")
    count = int(context.args[0]) if context.args else 1
    codes = []
    for _ in range(count):
        code = generate_plan_code("DIAMOND")
        await add_redeem_code(code, "Diamond", 5000, 60)
        codes.append(code)
    await update.effective_message.reply_text(
        f"<b><i>✅ Generated {count} Diamond code(s):</i></b>\n" + "\n".join(f"<code>{c}</code>" for c in codes),
        parse_mode=ParseMode.HTML
    )

async def gen_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate credits-only redeem codes. Usage: /gen_key <quantity> <credits>"""
    if update.effective_user.id not in ADMIN_IDS:
        return await update.effective_message.reply_text("🚫 Admins only!")
    if len(context.args) < 2 or not context.args[0].isdigit() or not context.args[1].isdigit():
        return await update.effective_message.reply_text(
            "<b><i>⚠️ Usage: /gen_key &lt;quantity&gt; &lt;credits&gt;</i></b>\nExample: <code>/gen_key 1 100</code>",
            parse_mode=ParseMode.HTML
        )
    count = int(context.args[0])
    credits_amount = int(context.args[1])
    if count <= 0 or count > 100 or credits_amount <= 0:
        return await update.effective_message.reply_text("⚠️ Invalid quantity (1-100) or credits (>0).")
    codes = []
    for _ in range(count):
        code = generate_plan_code(f"KEY{credits_amount}")
        await add_redeem_code(code, "Credits", credits_amount, 0)
        codes.append(code)
    await update.effective_message.reply_text(
        f"<b><i>✅ Generated {count} credit key(s) — {credits_amount} credits each:</i></b>\n"
        + "\n".join(f"<code>{c}</code>" for c in codes),
        parse_mode=ParseMode.HTML
    )

# ========== REDEEM COMMAND (USES DB) ==========
async def redeem_plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redeem a plan code from database."""
    user = update.effective_user
    user_id = user.id

    if not context.args:
        return await update.effective_message.reply_text(
            "<b><i>❌ Invalid format. Usage: /redeem [code]</i></b>",
            parse_mode=ParseMode.HTML
        )

    raw_code = " ".join(context.args).strip().strip("`").strip()
    # Remove accidental command prefix
    if raw_code.upper().startswith("/REDEEM"):
        raw_code = raw_code.split(None, 1)[-1] if " " in raw_code else raw_code
    code_upper = raw_code.upper().replace(" ", "")
    
    # Check DB for unused code
    code_doc = await get_redeem_code(code_upper)
    
    logger.info(f"Redeem attempt: code='{code_upper}', found={code_doc is not None}")

    if not code_doc:
        return await update.effective_message.reply_text(
            "<b><i>❌ Invalid or already used code.</i></b>",
            parse_mode=ParseMode.HTML
        )

    user_data = await get_user(user_id)
    current_plan = user_data.get('plan', 'Free')

    plan_name = code_doc['plan']
    credits = code_doc['credits']
    days = code_doc['days']

    # Credits-only redeem (from /gen_key) — add credits to existing balance, don't touch plan
    if plan_name == "Credits":
        current_credits = int(user_data.get('credits', 0) or 0)
        new_credits = current_credits + int(credits)
        keys_redeemed = int(user_data.get('keys_redeemed', 0) or 0) + 1
        await update_user(user_id, credits=new_credits, keys_redeemed=keys_redeemed)
        await mark_code_used(code_upper, user_id)
        return await update.effective_message.reply_text(
            f"<b><i>🎉 Redeemed!\n💰 +{credits} credits added\n📊 New balance: {new_credits}</i></b>",
            parse_mode=ParseMode.HTML
        )

    # Plan code — block if user already has a plan
    if current_plan != 'Free':
        return await update.effective_message.reply_text(
            "<b><i>❌ You already have an active plan. Cannot redeem.</i></b>",
            parse_mode=ParseMode.HTML
        )

    expiry = datetime.now() + timedelta(days=days)
    keys_redeemed = int(user_data.get('keys_redeemed', 0) or 0) + 1
    await update_user(
        user_id,
        plan=plan_name,
        status=plan_name,
        credits=credits,
        plan_expiry=expiry.strftime('%d-%m-%Y'),
        keys_redeemed=keys_redeemed
    )
    AUTHORIZED_PRIVATE_USERS.add(user_id)
    await mark_code_used(code_upper, user_id)

    await update.effective_message.reply_text(
        f"<b><i>🎉 Congratulations! Your {plan_name} plan is now active.\n"
        f"💰 Credits: {credits}\n"
        f"📅 Valid for: {days} days</i></b>",
        parse_mode=ParseMode.HTML
    )

# ========== REGISTRATION ==========
def register_plan_handlers(application):
    """Register all new plan commands."""
    # Give commands
    application.add_handler(CommandHandler("give_silver", give_silver))
    application.add_handler(CommandHandler("give_gold", give_gold))
    application.add_handler(CommandHandler("give_platinum", give_platinum))
    application.add_handler(CommandHandler("give_diamond", give_diamond))
    
    # Gen commands
    application.add_handler(CommandHandler("gen_silver", gen_silver))
    application.add_handler(CommandHandler("gen_gold", gen_gold))
    application.add_handler(CommandHandler("gen_platinum", gen_platinum))
    application.add_handler(CommandHandler("gen_diamond", gen_diamond))
    application.add_handler(CommandHandler("gen_key", gen_key))
    
    # Redeem command
    application.add_handler(CommandHandler("redeem", redeem_plan_command))
    
    logger.info("✅ New plan commands registered (with DB persistence)")
