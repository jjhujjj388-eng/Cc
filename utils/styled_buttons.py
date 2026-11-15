"""utils/styled_buttons.py

Bot API 9.4 (Feb 2026) added two new optional fields to ``InlineKeyboardButton``:

* ``style``                  — "primary" (blue), "success" (green), "danger" (red)
* ``icon_custom_emoji_id``   — a premium custom emoji rendered before the
                               button label (requires the bot owner to have
                               Telegram Premium).

python-telegram-bot may not yet expose these fields as native constructor
parameters depending on the installed version. Rather than rewriting every
menu handler in the bot to send raw HTTP via ``api.telegram.org``, we patch
``InlineKeyboardButton.to_dict`` once so any extras stashed on the instance
are injected straight into the JSON that PTB ultimately POSTs to
``api.telegram.org/bot<TOKEN>/<method>``.

The net effect is identical to writing the request by hand — Telegram
receives an inline keyboard with ``style`` and ``icon_custom_emoji_id`` on
every button — but every existing handler in the codebase keeps working
unchanged.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any, Dict, Optional

from telegram import InlineKeyboardButton

logger = logging.getLogger(__name__)

# Premium custom-emoji icon ids. These are the same green / blue premium
# emojis the original Black X Card build used so the look is preserved.
GREEN_ICON_ID = "5325525390041105820"   # ✅ bright green check
BLUE_ICON_ID = "5197434882321567830"    # 💎 bright blue diamond

_COLOR_TO_STYLE: Dict[str, str] = {
    "green": "success",
    "blue": "primary",
    "red": "danger",
}

# python-telegram-bot uses ``__slots__`` on TelegramObject which forbids
# ad-hoc attributes, and its objects don't support weakref, so the extras
# live in a bounded LRU side table keyed by ``id(button)``. The cap is
# generous; even very busy bots won't churn through millions of buttons
# between restarts, and the patched ``to_dict`` always falls back gracefully
# when an entry has been evicted.
_EXTRAS_TABLE_MAX = 50_000
_extras_table: "OrderedDict[int, Dict[str, Any]]" = OrderedDict()


def _store_extras(button: InlineKeyboardButton, extras: Dict[str, Any]) -> None:
    key = id(button)
    _extras_table[key] = extras
    _extras_table.move_to_end(key)
    while len(_extras_table) > _EXTRAS_TABLE_MAX:
        _extras_table.popitem(last=False)


_PATCHED = False


def _install_to_dict_patch() -> None:
    """Patch :py:meth:`InlineKeyboardButton.to_dict` exactly once."""
    global _PATCHED
    if _PATCHED:
        return

    original_to_dict = InlineKeyboardButton.to_dict

    def patched_to_dict(self, recursive: bool = True):
        data = original_to_dict(self, recursive=recursive)
        extras = _extras_table.get(id(self))
        if extras:
            for k, v in extras.items():
                if v is not None:
                    data[k] = v
        return data

    InlineKeyboardButton.to_dict = patched_to_dict  # type: ignore[assignment]
    _PATCHED = True
    logger.debug("Patched InlineKeyboardButton.to_dict for styled buttons")


_install_to_dict_patch()


def styled_button(
    text: str,
    *,
    callback_data: Optional[str] = None,
    url: Optional[str] = None,
    color: str = "blue",
    icon: Optional[str] = None,
) -> InlineKeyboardButton:
    """Return an :class:`InlineKeyboardButton` whose JSON carries ``style``
    and (optionally) ``icon_custom_emoji_id`` so the Telegram client renders
    it with the requested colour + premium icon.

    ``color`` accepts ``"green"`` (style=success), ``"blue"`` (style=primary)
    and ``"red"`` (style=danger). Anything else falls back to ``primary``.

    ``icon`` is a premium custom-emoji id. If omitted, a sensible default is
    chosen per colour (green check for green buttons, blue diamond for blue
    buttons). Pass ``icon=""`` to suppress the icon entirely.
    """
    style = _COLOR_TO_STYLE.get(color, "primary")

    if icon is None:
        icon = GREEN_ICON_ID if color == "green" else BLUE_ICON_ID
    elif icon == "":
        icon = None

    kwargs: Dict[str, Any] = {}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url

    btn = InlineKeyboardButton(text, **kwargs)
    _store_extras(btn, {"style": style, "icon_custom_emoji_id": icon})
    return btn
