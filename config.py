# config.py
"""
Central configuration for the bot.

Almost everything else in the codebase reads these values, so keep this file as
the single source of truth. You can also override the sensitive bits via env
vars (BOT_TOKEN, OWNER_ID, UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN).
"""

import os


# === BOT ===
TOKEN = os.getenv(
    "BOT_TOKEN",
    "9147083823:AAGVl85qv7gyr6CdsmHqE8cbo5vO4zyKNIo",
)
BOT_USERNAME = "mikeycc_bot"          # t.me/mikeycc_bot
BOT_LINK = f"https://t.me/{BOT_USERNAME}"

# === OWNER & ADMINS ===
OWNER_ID = int(os.getenv("OWNER_ID", "8855682217"))
OWNER_USERNAME = "mikeykunnx"          # @mikeykunnx
ADMIN_IDS = {OWNER_ID}

# === DEVELOPER LINKS ===
DEVELOPER_NAME = "mikeykunnx"
DEVELOPER_LINK = f"tg://resolve?domain={OWNER_USERNAME}"
AUTHORIZATION_CONTACT = f"@{OWNER_USERNAME}"

# === GROUPS / CHANNELS ===
OFFICIAL_GROUP_LINK = "https://t.me/TokoyoCC"
OFFICIAL_GROUP_USERNAME = "ＴＯＫＯＹＯ"           # https://t.me/mikeykun_x
OFFICIAL_GROUP_ID = -1003973127412

OFFICIAL_CHANNEL_LINK = "https://t.me/+CIrnLwRO_TRiYmQ1"
OFFICIAL_CHANNEL_USERNAME = "ＴＯＫＯＹＯ"         # invite link channel
OFFICIAL_CHANNEL_ID = -1003864452214

BULLET_GROUP_LINK = OFFICIAL_CHANNEL_LINK

# Where the bot posts hit broadcasts
PUBLIC_GROUP_ID = OFFICIAL_GROUP_ID

# Authorized chat ids (groups where the bot is allowed to run commands).
AUTHORIZED_CHATS = {OFFICIAL_GROUP_ID}
AUTHORIZED_PRIVATE_USERS = set()

# === FORCE-JOIN ===
FORCE_JOIN_GROUP_ID = OFFICIAL_GROUP_ID
FORCE_JOIN_GROUP_USERNAME = OFFICIAL_GROUP_LINK
FORCE_JOIN_CHANNEL_ID = OFFICIAL_CHANNEL_ID
FORCE_JOIN_CHANNEL_USERNAME = OFFICIAL_CHANNEL_USERNAME
FORCE_JOIN_IMAGE = "https://ibb.co/xqpnKmfF"

# === CREDITS ===
DEFAULT_FREE_CREDITS = 300

# === DATABASE — UPSTASH REDIS (REST) ===
UPSTASH_REDIS_REST_URL = os.getenv(
    "UPSTASH_REDIS_REST_URL",
    "https://welcome-sculpin-127987.upstash.io",
)
UPSTASH_REDIS_REST_TOKEN = os.getenv(
    "UPSTASH_REDIS_REST_TOKEN",
    "gQAAAAAAAfPzAAIgcDI1ZTIwMmJhYmM0NWQ0NjM2YTU1NDRjZTEwNzI0MDFmNg",
)

# === SCRAPER (Pyrogram / Telethon) ===
API_ID = int(os.getenv("API_ID", "38983764"))
API_HASH = os.getenv("API_HASH", "7f959da4bbc0da358f2bd8188fb5dbc6")
ADMIN_LIMIT = 50000
DEFAULT_LIMIT = 5000

# === PLANS ===
PLAN_SILVER = "Silver"
PLAN_GOLD = "Gold"
PLAN_PLATINUM = "Platinum"
PLAN_DIAMOND = "Diamond"

PLAN_DETAILS = {
    "Silver":   {"credits": 500,  "days": 7},
    "Gold":     {"credits": 1500, "days": 15},
    "Platinum": {"credits": 3000, "days": 30},
    "Diamond":  {"credits": 5000, "days": 60},
}

# === BOT COMMANDS LIST (used by some filters) ===
BOT_COMMANDS = [
    "/start", "/cmds", "/gen", "/bin", "/chk", "/mchk", "/mass",
    "/mtchk", "/fk", "/fl", "/open", "/status", "/credits", "/info",
    "/scr", "/sh", "/add", "/sp", "/scr", "/remove", "/b3", "/check",
    "/vbv", "/mvbv", "/site", "/cc", "/su", "/sk", "/st", "/st1",
    "/at", "/ad", "/pp", "/py", "/pc", "/hc", "/rz", "/mrz", "/rztxt",
    "/addrz", "/rzsite", "/rmrz", "/rmrzall",
    "/sh", "/msh", "/mtxt", "/oc", "/gate",
    "/mgate", "/hdgate", "/masspp", "/mb3", "/sktxt", "/chktxt",
    "/redeem", "/plan", "/gen_codes", "/au", "/rauth", "/give_trial", "/give_premium",
    "/give_plus", "/give_prime", "/take_plan", "/ban", "/unban", "/reset",
    "/close", "/restart", "/admin", "/broad",
]
