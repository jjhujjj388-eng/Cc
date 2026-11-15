import sys
import subprocess

def _ensure_deps():
    need = []
    pkgs = [
        ("telegram", "python-telegram-bot"),
        ("aiohttp", "aiohttp"),
        ("aiofiles", "aiofiles"),
        ("bs4", "beautifulsoup4"),
        ("lxml", "lxml"),
        ("faker", "Faker"),
        ("fake_useragent", "fake-useragent"),
        ("names", "names"),
        ("phonenumbers", "phonenumbers"),
        ("PIL", "pillow"),
        ("requests", "requests"),
        ("pyrogram", "pyrogram"),
        ("telethon", "telethon"),
    ]
    # optional: skip psutil if fails on some hosts
    for mod, pkg in pkgs:
        try:
            __import__(mod)
        except ImportError:
            need.append(pkg)
    if not need:
        return
    print("[deps] installing:", ", ".join(need), flush=True)
    cmd = [sys.executable, "-m", "pip", "install", "--prefer-binary", "--upgrade"] + need
    rc = subprocess.call(cmd)
    if rc != 0:
        rc = subprocess.call([sys.executable, "-m", "pip", "install", "--upgrade"] + need)
    if rc != 0:
        print("[deps] FAILED — install manually:", " ".join(need), flush=True)
        raise SystemExit(1)
    import importlib
    importlib.invalidate_caches()

_ensure_deps()

# main.py
import logging
import asyncio
import html
import re
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ApplicationHandlerStop,
    PrefixHandler
)
from telegram.error import BadRequest, NetworkError, TelegramError
from config import TOKEN, OWNER_ID
from db import init_db

from group import register_welcome_handler

from admin.plan_manager import register_plan_handlers

# === GATES FOLDER SE IMPORTS ===
from gates.braintree import b3_command, bc_command
from gates.paypal import pp_command, pc_command, masspp_command, register_masspp_handlers
from gates.shopify import (
    sh_command, register_sh_handlers,
    check_command, register_check_handlers,
    add, rm_command, removeall_command, show_command, register_rm_handlers,
    msh_command, register_msh_handlers,
)
from gates.stripe import (
    chk_command, sr_command,
    st_command, st1_command,
    cc_command,
    sk_command,
    mass_handler,
    chktxt_command, register_mstripe_callbacks
)
from gates.razorpay import (
    rz_command,
    mrz_command,
    rztxt_command,
    register_rz_handlers,
    register_razorpay_site_handlers,
    addrz_command,
    rzsite_command,
    rmrz_command,
    rmrzall_command,
)
from gates.shopify import register_mtxt_handlers, mtxt_command
from gates.menu_handlers import (
    admin_panel_ui_handler, admin_help_callback,
    gates_menu_handler, auth_sub_menu_handler, charge_gateway_menu_handler,
    stripe_auth_menu_handler, braintree_auth_menu_handler, auto_shopify_menu_handler,
    sk_based_menu_handler, stripe_charge_menu_handler,
    paypal1_menu_handler, paypal9_menu_handler, razorpay_menu_handler,
    mass_gateway_menu_handler, mass_stripe_menu_handler, mass_shopify_menu_handler,
    mass_paypal_menu_handler, mass_sk_stripe_menu_handler, mass_braintree_menu_handler,
    back_to_start_handler, tools_menu_handler, tools_page_2_handler
)

# === TOOLS FOLDER SE IMPORTS ===
from tools.start import start_command
from tools.gen import gen_command
from tools.scr import scr_command, mc_command, initialize_scraper
from tools.card_tools import bin_lookup, vbv_command
from tools.info_tools import info_command, credits_command, status_command
from tools.fake_tools import fk_command
from tools.gate_checker import gate_command, mgate_command, hdgate_command
from tools.cmds import cmds_command, cmds_pagination, handle_close
from tools.plan import plan_command, register_plan_command

# === CC_CLEAN MODULE (Clean, Split, Pick) ===
from cc_clean import register_cc_clean_handlers

# === ADMIN FOLDER SE IMPORTS ===
from admin.admin_commands import admin_command, take_plan
from admin.auth_commands import auth_group, remove_authorize_user
from admin.system_commands import ban, unban, close_command, restart_command
from admin.broadcast import broad_command, register_broadcast_handlers
from admin.addcr import register_addcr_handler
from admin.get_user_cmd import (
    get_user_command,
    register_get_user_handler,
)

# === PROXY MODULE IMPORTS ===
from proxy import register_proxy_handlers

# === RESET MODULE IMPORTS ===
from reset import register_reset_handlers

# === UTILS ===
from utils.decorators import enforce_cooldown
from utils.helpers import add_dual_command

# === FORCE JOIN ===
from force_join import global_force_join_filter

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main callback handler"""
    query = update.callback_query
    await query.answer()
    data = query.data

    logger.info(f"Callback received: {data} from user {query.from_user.id}")

    try:
        # 👇 FIRST: Check for broadcast callbacks
        if data and data.startswith("broadcast_"):
            from admin.broadcast import handle_broadcast_callback
            await handle_broadcast_callback(update, context)
            return

        # 👇 SECOND: Check for stop_msh callbacks
        if data and data.startswith("stop_msh_"):
            from gates.shopify.msh import handle_stop_msh_callback
            await handle_stop_msh_callback(update, context)
            return

        # 👇 FOURTH: Check for stop_masspp callbacks
        if data and data.startswith("stop_masspp:"):
            from gates.paypal.masspp import stop_masspp_handler
            await stop_masspp_handler(update, context)
            return

        # 👇 FIFTH: Check for stopchk callbacks
        if data and data.startswith("stopchk_"):
            from gates.stripe.mstripe import stopchk_callback
            await stopchk_callback(update, context)
            return

        # 👇 SIXTH: Check for stop_db_check callbacks
        if data and data.startswith("stop_db_check:"):
            from gates.shopify.check import stop_db_check_callback
            await stop_db_check_callback(update, context)
            return

        # 👇 SEVENTH: Check for add_working callbacks
        if data and data.startswith("add_working:"):
            from gates.shopify.check import add_working_sites_callback
            await add_working_sites_callback(update, context)
            return

        # 👇 EIGHTH: Check for check_db_sites
        if data == "check_db_sites":
            from gates.shopify.check import check_db_sites_callback
            await check_db_sites_callback(update, context)
            return

        # 👇 NINTH: Check for page navigation (from cmds)
        if data.startswith("page_"):
            await cmds_pagination(update, context)
            return

        if data == "close":
            await handle_close(update, context)
            return

        # 👇 TENTH: Menu handlers
        handlers = {
            "tools_menu": tools_menu_handler,
            "tools_page_1": tools_menu_handler,
            "tools_page_2": tools_page_2_handler,
            "gates_menu": gates_menu_handler,
            "auth_sub_menu": auth_sub_menu_handler,
            "charge_gateway_menu": charge_gateway_menu_handler,
            "stripe_auth_menu": stripe_auth_menu_handler,
            "braintree_auth_menu": braintree_auth_menu_handler,
            "auto_shopify_menu": auto_shopify_menu_handler,
            "sk_based_menu": sk_based_menu_handler,
            "stripe_charge_menu": stripe_charge_menu_handler,
            "paypal1_menu": paypal1_menu_handler,
            "paypal9_menu": paypal9_menu_handler,
            "razorpay_menu": razorpay_menu_handler,
            "back_to_start": back_to_start_handler,
            "mass_gateway_menu": mass_gateway_menu_handler,
            "mass_stripe_menu": mass_stripe_menu_handler,
            "mass_shopify_menu": mass_shopify_menu_handler,
            "mass_paypal_menu": mass_paypal_menu_handler,
            "mass_sk_stripe_menu": mass_sk_stripe_menu_handler,
            "mass_braintree_menu": mass_braintree_menu_handler,
        }

        handler = handlers.get(data)
        if handler:
            await handler(update, context)
        else:
            logger.warning(f"Unknown callback data: {data}")

    except Exception as e:
        logger.error(f"Error in handle_callback: {e}", exc_info=True)


async def main_async():
    """Main function"""
    logger.info("🚀 Starting Black X Card Bot...")

    await init_db()

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .defaults(Defaults(do_quote=True))
        .concurrent_updates(256)
        .connection_pool_size(128)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(15)
        .pool_timeout(30)
        .build()
    )

    # Set application for masspp
    from gates.paypal.masspp import set_application
    set_application(application)

    # Register force-join callback only here. wrap_all_commands(...) is
    # deferred until AFTER every CommandHandler is registered below (the
    # original call site fired before any commands existed, so it had
    # nothing to wrap).
    from telegram.ext import CallbackQueryHandler as _CQH
    from force_join import check_joined_callback as _check_joined_cb
    application.add_handler(
        _CQH(_check_joined_cb, pattern="^check_joined$")
    )

    # Global force join filter
    application.add_handler(
        MessageHandler(
            filters.TEXT & (filters.ChatType.PRIVATE | filters.ChatType.GROUP),
            global_force_join_filter
        ),
        group=-1
    )

    # Register menu handlers
    application.add_handler(CallbackQueryHandler(back_to_start_handler, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(tools_menu_handler, pattern="^tools_menu$"))
    application.add_handler(CallbackQueryHandler(tools_page_2_handler, pattern="^tools_page_2$"))
    application.add_handler(CallbackQueryHandler(gates_menu_handler, pattern="^gates_menu$"))
    application.add_handler(CallbackQueryHandler(auth_sub_menu_handler, pattern="^auth_sub_menu$"))
    application.add_handler(CallbackQueryHandler(charge_gateway_menu_handler, pattern="^charge_gateway_menu$"))
    application.add_handler(CallbackQueryHandler(stripe_auth_menu_handler, pattern="^stripe_auth_menu$"))
    application.add_handler(CallbackQueryHandler(braintree_auth_menu_handler, pattern="^braintree_auth_menu$"))
    application.add_handler(CallbackQueryHandler(auto_shopify_menu_handler, pattern="^auto_shopify_menu$"))
    application.add_handler(CallbackQueryHandler(sk_based_menu_handler, pattern="^sk_based_menu$"))
    application.add_handler(CallbackQueryHandler(stripe_charge_menu_handler, pattern="^stripe_charge_menu$"))
    application.add_handler(CallbackQueryHandler(paypal1_menu_handler, pattern="^paypal1_menu$"))
    application.add_handler(CallbackQueryHandler(paypal9_menu_handler, pattern="^paypal9_menu$"))
    application.add_handler(CallbackQueryHandler(razorpay_menu_handler, pattern="^razorpay_menu$"))
    application.add_handler(CallbackQueryHandler(mass_gateway_menu_handler, pattern="^mass_gateway_menu$"))
    application.add_handler(CallbackQueryHandler(mass_stripe_menu_handler, pattern="^mass_stripe_menu$"))
    application.add_handler(CallbackQueryHandler(admin_panel_ui_handler, pattern="^admin_panel_ui$"))
    application.add_handler(CallbackQueryHandler(admin_help_callback, pattern="^admin_help_"))
    application.add_handler(CallbackQueryHandler(mass_shopify_menu_handler, pattern="^mass_shopify_menu$"))
    application.add_handler(CallbackQueryHandler(mass_paypal_menu_handler, pattern="^mass_paypal_menu$"))
    application.add_handler(CallbackQueryHandler(mass_sk_stripe_menu_handler, pattern="^mass_sk_stripe_menu$"))
    application.add_handler(CallbackQueryHandler(mass_braintree_menu_handler, pattern="^mass_braintree_menu$"))

    # Register pagination handlers (from cmds.py)
    application.add_handler(CallbackQueryHandler(cmds_pagination, pattern="^page_"))
    application.add_handler(CallbackQueryHandler(handle_close, pattern="^close$"))

    # NOTE: catch-all CallbackQueryHandler(handle_callback) is registered at the
    # very end (after all register_*_handlers calls) so pattern-matched callbacks
    # like ^addrz_save: and ^stop_mrz: are not swallowed by the catch-all.

    # Register user commands
    user_commands = [
        ("start", start_command),
        ("info", info_command),
        ("cmds", cmds_command),
        ("credits", credits_command),
        ("status", status_command),
        ("gen", gen_command),
        ("bin", bin_lookup),
        ("add", add),
        ("vbv", vbv_command),
        ("fk", fk_command),
        ("gate", gate_command),
        ("mgate", mgate_command),
        ("hdgate", hdgate_command),
        ("chk", chk_command),
        ("sr", sr_command),
        ("b3", b3_command),
        ("st", st_command),
        ("st1", st1_command),
        ("rz", rz_command),
        ("mrz", mrz_command),
        # /rztxt removed — /mrz now handles pasted cards + replied .txt
        ("rzsite", rzsite_command),
        ("plan", plan_command),
        # /mtxt removed — /msh now handles pasted cards + replied .txt
        ("pp", pp_command),
        ("pc", pc_command),
        ("sh", sh_command),
        ("check", check_command),
        ("mass", mass_handler),
        ("masspp", masspp_command),
        ("msh", msh_command),
        ("chktxt", chktxt_command),
        ("cc", cc_command),
        ("sk", sk_command),
        ("bc", bc_command),
        ("scr", scr_command),
        ("mc", mc_command),
        ("rm", rm_command),
        ("removeall", removeall_command),
        ("show", show_command),
    ]

    # Premium-only mass gates (free users blocked everywhere)
    PREMIUM_ONLY = {"mass", "sktxt", "chktxt", "mrz", "masspp", "msh", "mgate"}
    # Single gates: free users blocked in private DMs (group still allowed)
    PRIVATE_PREMIUM = {"chk", "sr", "b3", "bc", "rz", "pp", "pc", "sh",
                       "cc", "st", "st1", "sk"}

    from utils.decorators import premium_only, private_premium_only

    for name, func in user_commands:
        wrapped = func
        if name in PREMIUM_ONLY:
            wrapped = premium_only(func)
        elif name in PRIVATE_PREMIUM:
            wrapped = private_premium_only(func)
        add_dual_command(application, name, wrapped)

    # Register owner commands (OLD PLAN COMMANDS REMOVED)
    owner_commands = [
        ("admin", admin_command),
        ("take_plan", take_plan),
        ("take", take_plan),
        ("au", auth_group),
        ("rauth", remove_authorize_user),
        ("ban", ban),
        ("unban", unban),
        ("close", close_command),
        ("restart", restart_command),
        ("broad", broad_command),
        # Razorpay site pool management (owner/admin only — checked inside the handler too)
        ("addrz", addrz_command),
        ("rmrz", rmrz_command),
        ("rmrzall", rmrzall_command),
        ("get_user", get_user_command),
    ]

    for name, func in owner_commands:
        add_dual_command(application, name, func, owner_only=True)

    # /get_user pagination callback
    register_get_user_handler(application)

    # Register module handlers
    register_masspp_handlers(application)
    register_msh_handlers(application)
    register_mstripe_callbacks(application)
    register_sh_handlers(application)
    register_mtxt_handlers(application)
    register_check_handlers(application)
    register_rm_handlers(application)
    register_broadcast_handlers(application)
    register_addcr_handler(application)
    register_rz_handlers(application)
    register_razorpay_site_handlers(application)
    register_plan_command(application)

    # Register welcome handler
    register_welcome_handler(application)

    # Register cc_clean module handlers (/clean, /split, /pick)
    register_cc_clean_handlers(application)

    # Register NEW PLAN handlers (Silver, Gold, Platinum, Diamond)
    register_plan_handlers(application)

    # Register proxy handlers
    register_proxy_handlers(application)
    logger.info("✅ Proxy commands registered: /addpxy, /rmpxy, /mypxy")

    # Register reset handlers
    register_reset_handlers(application)
    logger.info("✅ Reset command registered: /reset")

    # Wrap every registered CommandHandler with the force-join decorator
    # now that all commands have been added.
    from force_join import wrap_all_commands
    wrap_all_commands(application)

    # Register catch-all callback handler LAST so all pattern-specific
    # CallbackQueryHandlers (addrz_save, stop_mrz, stop_msh, etc.) get
    # priority and the catch-all only logs truly unknown callbacks.
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Initialize scraper
    try:
        await initialize_scraper()
        logger.info("✅ Scraper initialized successfully!")
    except Exception as e:
        logger.warning(f"⚠️ Scraper initialization failed: {e}")

    logger.info("🤖 Bot is running...")
    await application.initialize()
    await application.start()

    await application.updater.start_polling(
        poll_interval=0.0,
        timeout=10,
        drop_pending_updates=True,
        allowed_updates=[
            "message",
            "callback_query",
            "chat_member",
            "my_chat_member"
        ]
    )

    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await application.stop()


def main():
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
