# utils/bullet.py
from config import OWNER_ID, BULLET_GROUP_LINK, DEVELOPER_NAME, DEVELOPER_LINK
import html

def get_bullet_link(user_id=None):
    """Return clickable bullet link"""
    if user_id:
        return f'<a href="tg://user?id={user_id}">⊀</a>'
    return f'<a href="{BULLET_GROUP_LINK}">⊀</a>'

def get_bullet2_link():
    """Second bullet style"""
    return f'<a href="{BULLET_GROUP_LINK}">⌬</a>'

def get_developer_mention():
    """Get developer mention with name"""
    return f'<a href="{DEVELOPER_LINK}">{DEVELOPER_NAME}</a>'

def get_user_mention(user):
    """Get user mention with name"""
    full_name = user.first_name or "User"
    if user.last_name:
        full_name += f" {user.last_name}"
    return f'<a href="tg://user?id={user.id}">{html.escape(full_name)}</a>'

def get_user_role(user_id: int, plan: str = "Free") -> str:
    """Get user role with emoji"""
    if user_id == OWNER_ID:
        return "OWNER 🦂"
    if user_id in ADMIN_IDS:
        return "ADMIN 🔥"
    
    plan_lower = plan.lower()
    if "trial" in plan_lower:
        return "Trial 🧪"
    elif "premium" in plan_lower:
        return "Premium 💎"
    elif "plus" in plan_lower:
        return "Plus 🌤️"
    elif "prime" in plan_lower:
        return "Prime 🏆"
    
    return "Free ⏳"

# Import ADMIN_IDS from config
from config import ADMIN_IDS