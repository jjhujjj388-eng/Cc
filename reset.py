# reset.py
"""
Reset Command Module for Black X Card Bot

Command: /reset <user_id>

Force-stops any stuck mass-check session for that user across every gate
(Shopify /msh, Shopify /check, Stripe /mass, Razorpay /mrz, PayPal /masspp)
so they can start a fresh check. Owner / admin only.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from config import OWNER_ID, ADMIN_IDS

logger = logging.getLogger(__name__)


def _reset_user_sessions(target_user_id: int) -> list[str]:
    """Clear every known per-user mass-check session. Returns labels cleared."""
    cleared: list[str] = []

    # ---- Shopify /msh ----
    try:
        from gates.shopify.msh import active_mass_checks as msh_sessions
        for sid, data in list(msh_sessions.items()):
            if data.get("user_id") == target_user_id:
                ev = data.get("stop_event")
                if ev is not None:
                    try:
                        ev.set()
                    except Exception:
                        pass
                msh_sessions.pop(sid, None)
                cleared.append("Shopify /msh")
    except Exception as e:
        logger.warning(f"reset: shopify /msh cleanup failed: {e}")

    # ---- Shopify /check (DB site checker) ----
    try:
        from gates.shopify import check as shopify_check_mod
        for attr in ("active_db_checks", "active_checks", "ACTIVE_CHECKS"):
            d = getattr(shopify_check_mod, attr, None)
            if isinstance(d, dict):
                for sid, data in list(d.items()):
                    if isinstance(data, dict) and data.get("user_id") == target_user_id:
                        ev = data.get("stop_event")
                        if ev is not None:
                            try:
                                ev.set()
                            except Exception:
                                pass
                        d.pop(sid, None)
                        cleared.append("Shopify /check")
    except Exception as e:
        logger.warning(f"reset: shopify /check cleanup failed: {e}")

    # ---- Stripe /mass ----
    try:
        from gates.stripe.mstripe import TASKS as stripe_tasks
        if target_user_id in stripe_tasks:
            stripe_tasks[target_user_id]["stop"] = True
            stripe_tasks.pop(target_user_id, None)
            cleared.append("Stripe /mass")
    except Exception as e:
        logger.warning(f"reset: stripe /mass cleanup failed: {e}")

    # ---- Razorpay /mrz ----
    try:
        from gates.razorpay.rz import ACTIVE_MASS_STOP as rz_stop
        ev = rz_stop.get(target_user_id)
        if ev is not None:
            try:
                ev.set()
            except Exception:
                pass
            rz_stop.pop(target_user_id, None)
            cleared.append("Razorpay /mrz")
    except Exception as e:
        logger.warning(f"reset: razorpay /mrz cleanup failed: {e}")

    # ---- PayPal /masspp ----
    try:
        from gates.paypal.masspp import active_mass_checks as pp_sessions
        if target_user_id in pp_sessions:
            pp_sessions[target_user_id]["stop"] = True
            pp_sessions.pop(target_user_id, None)
            cleared.append("PayPal /masspp")
    except Exception as e:
        logger.warning(f"reset: paypal /masspp cleanup failed: {e}")

    return cleared


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset <user_id> — owner/admin only. Stops any stuck mass check."""
    user_id = update.effective_user.id
    if user_id != OWNER_ID and user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "⚠️ Usage: <code>/reset &lt;user_id&gt;</code>\n"
            "Force-stops any stuck mass check for that user.",
            parse_mode="HTML",
        )
        return

    target_user_id = int(context.args[0])
    try:
        cleared = _reset_user_sessions(target_user_id)
        if cleared:
            await update.message.reply_text(
                f"✅ Reset done for <code>{target_user_id}</code>.\n"
                f"Stopped: <b>{', '.join(cleared)}</b>",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"ℹ️ No active mass check was running for <code>{target_user_id}</code>.\n"
                f"They can run a fresh check now.",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.exception("reset_command failed")
        await update.message.reply_text(f"❌ Error: {e}")


def register_reset_handlers(application):
    application.add_handler(CommandHandler("reset", reset_command))
    logger.info("✅ Reset command registered: /reset <user_id>")
