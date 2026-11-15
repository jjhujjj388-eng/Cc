# tools/gate_checker.py
import re
import aiohttp
import asyncio
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from utils.helpers import escape_html, escape_markdown_v2
from utils.bullet import get_bullet_link, get_user_mention, get_developer_mention
from utils.constants import CMS_PATTERNS, PAYMENT_GATEWAYS
from db import get_user, update_user
from force_join import force_join

# Shared session
session: aiohttp.ClientSession = None

async def init_session():
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession()

async def close_session():
    global session
    if session and not session.closed:
        await session.close()

async def consume_credits(user_id: int, required_credits: int) -> bool:
    user_data = await get_user(user_id)
    if user_data and user_data.get("credits", 0) >= required_credits:
        await update_user(user_id, credits=user_data["credits"] - required_credits)
        return True
    return False

async def fetch_site(url: str):
    await init_session()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    domain = urlparse(url).netloc

    headers = {
        "authority": domain,
        "scheme": "https",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/140.0.0.0 Mobile Safari/537.36",
    }

    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            text = await resp.text()
            return resp.status, text, resp.headers
    except Exception:
        return None, None, None

def detect_cms(html: str):
    for cms, pattern in CMS_PATTERNS.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            if cms == 'Custom CMS':
                return match.group(1) or "Custom CMS"
            return cms
    return "Unknown"

def detect_security(html: str):
    patterns_3ds = [
        r'3d\s*secure',
        r'verified\s*by\s*visa',
        r'mastercard\s*securecode',
        r'american\s*express\s*safekey',
        r'3ds',
        r'3ds2',
        r'acsurl',
        r'pareq',
        r'three-domain-secure',
        r'secure_redirect',
    ]
    for pattern in patterns_3ds:
        if re.search(pattern, html, re.IGNORECASE):
            return "3D Secure Detected ✅"
    return "2D (No 3D Secure Found ❌)"

def detect_gateways(html: str):
    detected = []
    for gateway in PAYMENT_GATEWAYS:
        pattern = r'\b' + re.escape(gateway) + r'\b'
        if re.search(pattern, html, re.IGNORECASE):
            detected.append(gateway)
    return ", ".join(detected) if detected else "None Detected"

def detect_captcha(html: str):
    html_lower = html.lower()
    if "hcaptcha" in html_lower:
        return "hCaptcha Detected ✅"
    elif "recaptcha" in html_lower or "g-recaptcha" in html_lower:
        return "reCAPTCHA Detected ✅"
    elif "captcha" in html_lower:
        return "Generic Captcha Detected ✅"
    return "No Captcha Detected"

def detect_cloudflare(html: str, headers=None, status=None):
    if headers is None:
        headers = {}
    lower_keys = [k.lower() for k in headers.keys()]
    server = headers.get('Server', '').lower()
    cloudflare_indicators = [
        r'cloudflare',
        r'cf-ray',
        r'cf-cache-status',
        r'cf-browser-verification',
        r'__cfduid',
        r'cf_chl_',
        r'checking your browser',
        r'enable javascript and cookies',
        r'ray id',
        r'ddos protection by cloudflare',
    ]
    if 'cf-ray' in lower_keys or 'cloudflare' in server or 'cf-cache-status' in lower_keys:
        soup = BeautifulSoup(html, 'html.parser')
        title = soup.title.string.strip().lower() if soup.title else ''
        challenge_indicators = [
            "just a moment",
            "attention required",
            "checking your browser",
            "enable javascript and cookies to continue",
            "ddos protection by cloudflare",
            "please wait while we verify",
        ]
        if any(indicator in title for indicator in challenge_indicators):
            return "Cloudflare Verification Detected ✅"
        if any(re.search(pattern, html, re.IGNORECASE) for pattern in cloudflare_indicators):
            return "Cloudflare Verification Detected ✅"
        if status in (403, 503) and 'cloudflare' in html.lower():
            return "Cloudflare Verification Detected ✅"
        return "Cloudflare Present (No Verification) 🔍"
    return "None"

def detect_graphql(html: str):
    if re.search(r'/graphql|graphqlendpoint|apollo-client|query\s*\{|mutation\s*\{', html, re.IGNORECASE):
        return "GraphQL Detected ✅"
    return "No GraphQL Detected ❌"

async def gate_worker(update: Update, url: str, msg, user_id: int):
    if not await consume_credits(user_id, 1):
        await msg.edit_text(
            "❌ You don't have enough credits to perform this scan.",
            parse_mode="HTML"
        )
        return

    await asyncio.sleep(0)
    status, html, headers = await fetch_site(url)
    await asyncio.sleep(0)

    if not html:
        await msg.edit_text(
            f"❌ Cannot access {escape_html(url)}",
            parse_mode="HTML"
        )
        return

    cms = detect_cms(html)
    await asyncio.sleep(0)
    security = detect_security(html)
    await asyncio.sleep(0)
    gateways = detect_gateways(html)
    await asyncio.sleep(0)
    captcha = detect_captcha(html)
    await asyncio.sleep(0)
    cloudflare = detect_cloudflare(html, headers=headers, status=status)
    await asyncio.sleep(0)
    graphql = detect_graphql(html)
    await asyncio.sleep(0)

    bullet_link = get_bullet_link()
    user_mention = get_user_mention(update.effective_user)
    dev_mention = get_developer_mention()

    results = (
        f"◇━━〔 𝑳𝒐𝒐𝒌𝒖𝒑 𝑹𝒆𝒔𝒖𝒍𝒕𝒔 〕━━◇\n"
        f"{bullet_link} 𝐒𝐢𝐭𝐞 ↣ <code>{escape_html(url)}</code>\n"
        f"{bullet_link} 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ↣ <i>{escape_html(gateways)}</i>\n"
        f"{bullet_link} 𝐂𝐌𝐒 ↣ <code>{escape_html(cms)}</code>\n"
        f"――――――――――――――――\n"
        f"{bullet_link} 𝐂𝐚𝐩𝐭𝐜𝐡𝐚 ↣ <code>{escape_html(captcha)}</code>\n"
        f"{bullet_link} 𝐂𝐥𝐨𝐮𝐝𝐟𝐥𝐚𝐫𝐞 ↣ <code>{escape_html(cloudflare)}</code>\n"
        f"{bullet_link} 𝐒𝐞𝐜𝐮𝐫𝐢𝐭𝐲 ↣ <code>{escape_html(security)}</code>\n"
        f"{bullet_link} 𝐆𝐫𝐚𝐩𝐡𝐐𝐋 ↣ <code>{escape_html(graphql)}</code>\n"
        f"――――――――――――――――\n"
        f"{bullet_link} 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ↣ {user_mention}\n"
        f"{bullet_link} 𝐃𝐞𝐯𝐞𝐥𝐨𝐩𝐞𝐫 ↣ {dev_mention}"
    )

    await msg.edit_text(results, parse_mode="HTML", disable_web_page_preview=True)

@force_join
async def gate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Single site gateway checker"""
    if not context.args:
        await update.message.reply_text("Usage: /gate <site_url>")
        return

    url = context.args[0]
    user_id = update.effective_user.id

    bullet_link = get_bullet_link()
    processing_text = f"<pre><code>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴⏳</code></pre>\n{bullet_link} 𝗦𝘁𝗮𝘁𝘂𝘀 ↣ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 🔎...\n"

    msg = await update.message.reply_text(
        processing_text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    asyncio.create_task(gate_worker(update, url, msg, user_id))

async def mgate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Multiple sites gateway checker"""
    if not context.args:
        await update.message.reply_text("Usage: /mgate <site1> <site2> <site3> <site4> <site5>")
        return

    user_id = update.effective_user.id
    urls = context.args[:5]
    required_credits = len(urls)

    user_data = await get_user(user_id)
    if not user_data or user_data.get("credits", 0) < required_credits:
        await update.message.reply_text(
            f"❌ You need {required_credits} credits to scan {required_credits} site(s).",
            parse_mode="HTML"
        )
        return

    bullet_link = get_bullet_link()
    processing_text = f"<pre><code>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴⏳</code></pre>\n{bullet_link} 𝗦𝘁𝗮𝘁𝘂𝘀 ↣ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(urls)} site(s) 🔎...\n"
    msg = await update.message.reply_text(
        processing_text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    if not await consume_credits(user_id, required_credits):
        await msg.edit_text(f"❌ Failed to consume {required_credits} credits.", parse_mode="HTML")
        return

    await init_session()
    tasks = [fetch_site(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output = [f"◇━━〔 𝑳𝒐𝒐𝒌𝒖𝒑 𝑹𝒆𝒔𝒖𝒍𝒕𝒔 〕━━◇"]
    for i, (url, result) in enumerate(zip(urls, results)):
        await asyncio.sleep(0)
        if isinstance(result, Exception) or result[0] is None:
            output.append(
                f"{bullet_link} 𝐒𝐢𝐭𝐞 {i+1}: <code>{escape_html(url)}</code>\n"
                f"{bullet_link} 𝐑𝐞𝐬𝐮𝐥𝐭 ↣ <code>Cannot access site</code>\n"
                f"――――――――――――――――"
            )
            continue

        status, html, headers = result
        cms = detect_cms(html)
        security = detect_security(html)
        gateways = detect_gateways(html)
        captcha = detect_captcha(html)
        cloudflare = detect_cloudflare(html, headers=headers, status=status)
        graphql = detect_graphql(html)

        output.append(
            f"{bullet_link} 𝐒𝐢𝐭𝐞 {i+1}: <code>{escape_html(url)}</code>\n"
            f"{bullet_link} 𝐆𝐚𝐭𝐞𝐰𝐚𝐲𝐬 ↣ <i>{escape_html(gateways)}</i>\n"
            f"{bullet_link} 𝐂𝐌𝐒 ↣ <code>{escape_html(cms)}</code>\n"
            f"{bullet_link} 𝐂𝐚𝐩𝐭𝐜𝐡𝐚 ↣ <code>{escape_html(captcha)}</code>\n"
            f"{bullet_link} 𝐂𝐥𝐨𝐮𝐝𝐟𝐥𝐚𝐫𝐞 ↣ <code>{escape_html(cloudflare)}</code>\n"
            f"{bullet_link} 𝐒𝐞𝐜𝐮𝐫𝐢𝐭𝐲 ↣ <code>{escape_html(security)}</code>\n"
            f"{bullet_link} 𝐆𝐫𝐚𝐩𝐡𝐐𝐋 ↣ <code>{escape_html(graphql)}</code>\n"
            f"――――――――――――――――"
        )

    user = update.effective_user
    user_mention = get_user_mention(user)
    dev_mention = get_developer_mention()
    output.append(
        f"{bullet_link} 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ↣ {user_mention}\n"
        f"{bullet_link} 𝐃𝐞𝐯𝐞𝐥𝐨𝐩𝐞𝐫 ↣ {dev_mention}"
    )

    final_output = "\n".join(output)
    await msg.edit_text(
        final_output,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

async def hdgate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Heavy duty multiple sites gateway checker"""
    if not context.args:
        await update.message.reply_text("Usage: /hdgate <site_url1> [site_url2] ... [site_url100]")
        return

    user_id = update.effective_user.id
    urls = [re.sub(r'^\d+\.\s*', '', url.strip()) for url in context.args[:100]]
    urls = [url for url in urls if url]
    
    if not urls:
        await update.message.reply_text("No valid URLs provided.")
        return
        
    required_credits = len(urls)

    user_data = await get_user(user_id)
    if not user_data or user_data.get("credits", 0) < required_credits:
        await update.message.reply_text(
            f"❌ You need {required_credits} credits to scan {required_credits} site(s).",
            parse_mode="HTML"
        )
        return

    if not await consume_credits(user_id, required_credits):
        await update.message.reply_text(
            f"❌ Failed to consume {required_credits} credits.",
            parse_mode="HTML"
        )
        return

    bullet_link = get_bullet_link()
    status_text = f"𝗦𝘁𝗮𝘁𝘂𝘀 ↣ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(urls)} site(s) 🔎..."
    processing_text = f"<pre><code>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴⏳</code></pre>\n{bullet_link} {escape_html(status_text)}\n"
    msg = await update.message.reply_text(
        processing_text,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

    asyncio.create_task(process_hdgate(update, context, msg, urls, user_id))

async def process_hdgate(update: Update, context: ContextTypes.DEFAULT_TYPE, msg, urls, user_id):
    """Background processing for hdgate"""
    bullet_link = get_bullet_link()
    
    await init_session()
    batch_size = 5
    
    for batch_start in range(0, len(urls), batch_size):
        batch_urls = urls[batch_start:batch_start + batch_size]
        tasks = [fetch_site(url) for url in batch_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = [f"◇━━〔 𝑳𝒐𝒐𝒌𝒖𝒑 𝑹𝒆𝒔𝒖𝒍𝒕𝒔 (Sites {batch_start + 1}-{min(batch_start + batch_size, len(urls))} )━━◇"]
        for i, (url, result) in enumerate(zip(batch_urls, results)):
            site_number = batch_start + i + 1
            await asyncio.sleep(0)
            if isinstance(result, Exception) or result[0] is None:
                output.append(
                    f"{bullet_link} 𝐒𝐢𝐭𝐞 <code>{site_number}: {escape_html(url)}</code>\n"
                    f"{bullet_link} 𝐑𝐞𝐬𝐮𝐥𝐭 ↣ <code>Cannot access site</code>\n"
                    f"――――――――――――――――"
                )
                continue

            status, html, headers = result
            cms = detect_cms(html)
            security = detect_security(html)
            gateways = detect_gateways(html)
            captcha = detect_captcha(html)
            cloudflare = detect_cloudflare(html, headers=headers, status=status)
            graphql = detect_graphql(html)

            output.append(
                f"{bullet_link} 𝐒𝐢𝐭𝐞 <code>{site_number}: {escape_html(url)}</code>\n"
                f"{bullet_link} 𝐆𝐚𝐭𝐞𝐰𝐚𝐲𝐬 ↣ <i>{escape_html(gateways)}</i>\n"
                f"{bullet_link} 𝐂𝐌𝐒 ↣ <code>{escape_html(cms)}</code>\n"
                f"{bullet_link} 𝐂𝐚𝐩𝐭𝐜𝐡𝐚 ↣ <code>{escape_html(captcha)}</code>\n"
                f"{bullet_link} 𝐂𝐥𝐨𝐮𝐝𝐟𝐥𝐚𝐫𝐞 ↣ <code>{escape_html(cloudflare)}</code>\n"
                f"{bullet_link} 𝐒𝐞𝐜𝐮𝐫𝐢𝐭𝐲 ↣ <code>{escape_html(security)}</code>\n"
                f"{bullet_link} 𝐆𝐫𝐚𝐩𝐡𝐐𝐋 ↣ <code>{escape_html(graphql)}</code>\n"
                f"――――――――――――――――"
            )

        user = update.effective_user
        user_mention = get_user_mention(user)
        dev_mention = get_developer_mention()
        output.append(
            f"{bullet_link} 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐁𝐲 ↣ {user_mention}\n"
            f"{bullet_link} 𝐃𝐞𝐯𝐞𝐥𝐨𝐩𝐞𝐫 ↣ {dev_mention}"
        )

        final_output = "\n".join(output)
        await update.message.reply_text(
            final_output,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        progress = min(batch_start + batch_size, len(urls))
        status_text = f"𝗦𝘁𝗮𝘁𝘂𝘀 ↣ 𝗖𝗵𝗲𝗰𝗸𝗶𝗻𝗴 {len(urls)} site(s) 🔎... ({progress}/{len(urls)} completed)"
        processing_text = f"<pre><code>𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴⏳</code></pre>\n{bullet_link} {escape_html(status_text)}\n"
        await msg.edit_text(
            processing_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        await asyncio.sleep(1)

    await msg.edit_text(f"✅ Completed scanning {len(urls)} site(s).", parse_mode="HTML")