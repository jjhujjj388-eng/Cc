"""Shared plan-label helper used by all gates."""
from __future__ import annotations

from typing import Tuple

from config import OWNER_ID, ADMIN_IDS
from db import get_user


def _plan_badge(plan: str) -> str:
    p = (plan or "").lower()
    if "owner" in p:
        return "👑"
    if "admin" in p:
        return "🛡️"
    if "free" in p:
        return "🧪"
    if "prime" in p:
        return "🏆"
    if "premium" in p:
        return "✨"
    if "plus" in p:
        return "➕"
    return "🎟️"


async def user_plan_label(user_id: int) -> Tuple[str, str]:
    """Return (plan_name, plan_badge) for the given user id."""
    if user_id == OWNER_ID:
        return "Owner", _plan_badge("owner")
    if user_id in ADMIN_IDS:
        return "Admin", _plan_badge("admin")
    try:
        data = await get_user(user_id) or {}
        plan = str(data.get("plan", "Free")) or "Free"
        return plan, _plan_badge(plan)
    except Exception:
        return "Free", "🎟️"
