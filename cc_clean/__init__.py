# cc_clean/__init__.py
from .clean import register_clean_handler
from .split import register_split_pick_handlers

def register_cc_clean_handlers(application):
    """Register all cc_clean module commands."""
    register_clean_handler(application)
    register_split_pick_handlers(application)