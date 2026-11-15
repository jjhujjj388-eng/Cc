# utils/helpers.py
import re
import html
import time
from datetime import datetime
from telegram.ext import CommandHandler, PrefixHandler

def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    if text is None:
        return ""
    return html.escape(str(text), quote=False)

def escape_markdown_v2(text: str) -> str:
    """Escape for MarkdownV2"""
    if text is None:
        return ""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', str(text))

def luhn_checksum(card_number):
    """Luhn algorithm check"""
    digits = [int(d) for d in card_number if d.isdigit()]
    total = 0
    num_digits = len(digits)
    parity = num_digits % 2
    
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    
    return total % 10 == 0

def get_level_emoji(level):
    """Return emoji for card level"""
    level_lower = level.lower()
    if "gold" in level_lower:
        return "🥇"
    elif "platinum" in level_lower:
        return "💎"
    elif "premium" in level_lower:
        return "✨"
    elif "infinite" in level_lower:
        return "♾️"
    elif "business" in level_lower:
        return "📈"
    elif "classic" in level_lower:
        return "💳"
    return "💡"

def extract_cards_from_text(text: str) -> list:
    """Extract cards from text"""
    pattern = r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b"
    cards = []
    
    for match in re.finditer(pattern, text):
        card, mm, yy, cvv = match.groups()
        mm = mm.zfill(2)
        yy = yy[-2:] if len(yy) == 4 else yy
        cards.append(f"{card}|{mm}|{yy}|{cvv}")
    
    return cards

def format_time(seconds):
    """Format time nicely"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}m {seconds:.0f}s"

def normalize_card_format(card: str) -> str:
    """Normalize card to CC|MM|YY|CVV format"""
    parts = re.split(r'[\|/: ]+', card.strip())
    if len(parts) >= 4:
        cc = re.sub(r'\D', '', parts[0])
        mm = parts[1].zfill(2)
        yy = parts[2]
        if len(yy) == 4:
            yy = yy[2:]
        cvv = parts[3]
        return f"{cc}|{mm}|{yy}|{cvv}"
    return None

def add_dual_command(application, name, func, owner_only=False):
    """
    Register a command that works with both dot (.) and slash (/)
    Example: .start and /start both will work
    """
    # Register slash command (/command)
    application.add_handler(CommandHandler(name, func))
    
    # Register dot command (.command)
    application.add_handler(PrefixHandler(".", name, func))