# tools/fake_tools.py
from faker import Faker
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from db import get_user
from utils.decorators import enforce_cooldown
from utils.credits import consume_credit
from utils.helpers import escape_markdown_v2
from utils.bullet import get_bullet_link
from force_join import force_join

@force_join
async def fk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates fake identity info."""
    
    if not await enforce_cooldown(update.effective_user.id, update):
        return

    user_id = update.effective_user.id
    user_data = await get_user(user_id)

    if user_data['credits'] <= 0 or not await consume_credit(user_id):
        return await update.effective_message.reply_text(
            "❌ You have no credits left. Please get a subscription to use this command.",
            parse_mode=ParseMode.HTML
        )

    country_code = context.args[0] if context.args else 'en_US'
    try:
        fake = Faker(country_code)
    except:
        fake = Faker('en_US')

    name = fake.name()
    dob = fake.date_of_birth().strftime('%Y-%m-%d')
    ssn = fake.ssn()
    email = fake.email()
    username = fake.user_name()
    phone = fake.phone_number()
    job = fake.job()
    company = fake.company()
    street = fake.street_address()
    address2 = fake.secondary_address()
    city = fake.city()
    state = fake.state()
    zip_code = fake.zipcode()
    country = fake.country()
    ip = fake.ipv4_public()
    ua = fake.user_agent()

    bullet_link = get_bullet_link()

    output = (
        f"━━━[ 🧑‍💻 𝙁𝙖𝙠𝙚 𝙄𝙣𝙛𝙤 ]━\n"
        f"{bullet_link} 𝙉𝙖𝙢𝙚 ➳ <code>{escape_markdown_v2(name)}</code>\n"
        f"{bullet_link} 𝘿𝙤𝘽 ➳ <code>{escape_markdown_v2(dob)}</code>\n"
        f"{bullet_link} 𝙎𝙎𝙉 ➳ <code>{escape_markdown_v2(ssn)}</code>\n"
        f"{bullet_link} 𝙀𝙢𝙖𝙞𝙡 ➳ <code>{escape_markdown_v2(email)}</code>\n"
        f"{bullet_link} 𝙐𝙨𝙚𝙧𝙣𝙖𝙢𝙚 ➳ <code>{escape_markdown_v2(username)}</code>\n"
        f"{bullet_link} 𝙋𝙝𝙤𝙣𝙚 ➳ <code>{escape_markdown_v2(phone)}</code>\n"
        f"{bullet_link} 𝙅𝙤𝙗 ➳ <code>{escape_markdown_v2(job)}</code>\n"
        f"{bullet_link} 𝘾𝙤𝙢𝙥𝙖𝙣𝙮 ➳ <code>{escape_markdown_v2(company)}</code>\n"
        f"{bullet_link} 𝙎𝙩𝙧𝙚𝙚𝙩 ➳ <code>{escape_markdown_v2(street)}</code>\n"
        f"{bullet_link} 𝘼𝙙𝙙𝙧𝙚𝙨𝙨 2 ➳ <code>{escape_markdown_v2(address2)}</code>\n"
        f"{bullet_link} 𝘾𝙞𝙩𝙮 ➳ <code>{escape_markdown_v2(city)}</code>\n"
        f"{bullet_link} 𝙎𝙩𝙖𝙩𝙚 ➳ <code>{escape_markdown_v2(state)}</code>\n"
        f"{bullet_link} 𝙕𝙞𝙥 ➳ <code>{escape_markdown_v2(zip_code)}</code>\n"
        f"{bullet_link} 𝘾𝙤𝙪𝙣𝙩𝙧𝙮 ➳ <code>{escape_markdown_v2(country)}</code>\n"
        f"{bullet_link} 𝙄𝙋 ➳ <code>{escape_markdown_v2(ip)}</code>\n"
        f"{bullet_link} 𝙐𝘼 ➳ <code>{escape_markdown_v2(ua)}</code>\n"
        "━━━━━━━━━━━━━━━━━━"
    )

    await update.effective_message.reply_text(
        output,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )