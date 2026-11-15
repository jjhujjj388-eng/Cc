# utils/credits.py
"""Credit-management helpers.

The bot owner and any user listed in ``ADMIN_IDS`` always run with unlimited
credits — :func:`consume_credit` becomes a no-op for them and
:func:`format_credits` renders their balance as ``∞`` everywhere in the UI.
"""

from __future__ import annotations

from config import ADMIN_IDS, OWNER_ID
from db import get_user, update_user


# ---------------------------------------------------------------------
# Unlimited / display helpers
# ---------------------------------------------------------------------
def is_unlimited(user_id: int) -> bool:
    """Return True if this user pays no credits and shows ``∞`` in the UI."""
    return user_id == OWNER_ID or user_id in ADMIN_IDS


def format_credits(user_id: int, credits) -> str:
    """Render the credit value as a string, swapping in ``∞`` for owner/admins.

    ``credits`` may be ``None``, an int, or anything ``str``-able.
    """
    if is_unlimited(user_id):
        return "∞"
    try:
        return str(int(credits))
    except (TypeError, ValueError):
        return str(credits) if credits is not None else "0"


# ---------------------------------------------------------------------
# Credit mutation
# ---------------------------------------------------------------------
async def consume_credit(user_id: int, amount: int = 1) -> bool:
    """Consume credits from user. No-op (returns True) for owner / admins."""
    if is_unlimited(user_id):
        return True
    try:
        user_data = await get_user(user_id)
        if user_data and user_data.get("credits", 0) >= amount:
            new_credits = user_data["credits"] - amount
            await update_user(user_id, credits=new_credits)
            return True
    except Exception as e:
        print(f"Credit error: {e}")
    return False


async def add_credits(user_id: int, amount: int) -> bool:
    """Add credits to user"""
    try:
        user_data = await get_user(user_id)
        if user_data:
            new_credits = user_data.get("credits", 0) + amount
            await update_user(user_id, credits=new_credits)
            return True
    except Exception as e:
        print(f"Add credit error: {e}")
    return False


async def get_user_plan(user_id: int) -> str:
    """Get user plan"""
    try:
        user_data = await get_user(user_id)
        if user_data:
            return user_data.get("plan", "Free")
    except Exception:
        pass
    return "Free"


async def is_premium(user_id: int) -> bool:
    """Check if user has any paid plan (anything other than Free)."""
    if user_id == OWNER_ID or user_id in ADMIN_IDS:
        return True

    plan = (await get_user_plan(user_id) or "").strip().lower()
    if plan in ("", "free", "n/a", "none"):
        return False
    return True
