# utils/constants.py
import re

# ============================================================
# === PREMIUM EMOJI IDS =====================================
# Reuse these everywhere — they map to specific Telegram
# Premium emojis whose colours we know:
#
#   * EMOJI_APPROVED ✅ — bright GREEN check
#   * EMOJI_CHARGED  💎 — bright BLUE diamond
#   * EMOJI_DEAD / EMOJI_ERROR — RED ❌
#   * EMOJI_PAISE 💸  — green money (used inline next to prices)
#
# The button helpers in `gates/menu_handlers.py` use
# BUTTON_GREEN_ICON_ID / BUTTON_BLUE_ICON_ID to decorate every
# inline keyboard button with a green or blue premium-emoji icon.
# ============================================================

EMOJI_LOADING = '5195033767969839232'        # ⏳ hourglass
EMOJI_SUCCESS = '5323307196807653127'        # ✅ green check
EMOJI_ERROR   = '5210952531676504517'        # ❌ red cross
EMOJI_DEAD    = '5210952531676504517'        # ❌ red cross
EMOJI_DEV     = '5224450179368767019'        # 🥈 silver
EMOJI_CHECK   = '5332724926216428039'        # 💨 dash
EMOJI_CHARGED = '5197434882321567830'        # 💎 BLUE diamond
EMOJI_APPROVED = '5323307196807653127'       # ✅ GREEN check
EMOJI_PAISE   = '5852881749645728848'        # 💸 green money

# Button-icon ids used on every inline keyboard button so the
# user always sees a coloured premium-emoji icon. Picked so the
# two are visibly different colours (green vs blue).
BUTTON_GREEN_ICON_ID = '5325525390041105820'   # ✅ bright green check
BUTTON_BLUE_ICON_ID  = '5197434882321567830'   # 💎 bright blue diamond

# === CARD PATTERN ===
CARD_PATTERN = re.compile(
    r"\b(\d{12,19})[\|/: ]+(\d{1,2})[\|/: ]+(\d{2,4})[\|/: ]+(\d{3,4})\b"
)

# === CMS PATTERNS (for gate checker) ===
CMS_PATTERNS = {
    'Shopify': r'cdn\.shopify\.com|shopify\.js',
    'BigCommerce': r'cdn\.bigcommerce\.com|bigcommerce\.com',
    'Wix': r'static\.parastorage\.com|wix\.com',
    'Squarespace': r'static1\.squarespace\.com|squarespace-cdn\.com',
    'WooCommerce': r'wp-content/plugins/woocommerce/',
    'Magento': r'static/version\d+/frontend/|magento/',
    'WordPress': r'wp-content|wp-includes/',
}

# === PAYMENT GATEWAYS LIST ===
PAYMENT_GATEWAYS = [
    "PayPal", "Stripe", "Braintree", "Square", "Cybersource", "lemon-squeezy",
    "Authorize.Net", "2Checkout", "Adyen", "Worldpay", "SagePay",
    "Checkout.com", "Bolt", "Eway", "PayFlow", "Payeezy",
    "Paddle", "Mollie", "Viva Wallet", "Rocketgateway", "Rocketgate",
    "Rocket", "Auth.net", "Authnet", "rocketgate.com", "Recurly",
    "Shopify", "WooCommerce", "BigCommerce", "Magento", "Magento Payments",
    "OpenCart", "PrestaShop", "3DCart", "Ecwid", "Shift4Shop",
    "Shopware", "VirtueMart", "CS-Cart", "X-Cart", "LemonStand",
    "Convergepay", "PaySimple", "oceanpayments", "eProcessing",
    "hipay", "cybersourse", "payjunction", "usaepay", "creo",
    "SquareUp", "ebizcharge", "cpay", "Moneris", "cardknox",
    "matt sorra", "Chargify", "Paytrace", "hostedpayments", "securepay",
    "blackbaud", "LawPay", "clover", "cardconnect", "bluepay",
    "fluidpay", "Ebiz", "chasepaymentech", "Auruspay", "sagepayments",
    "paycomet", "geomerchant", "realexpayments", "Razorpay",
    "Apple Pay", "Google Pay", "Samsung Pay", "Cash App",
    "Revolut", "Zelle", "Alipay", "WeChat Pay", "PayPay", "Line Pay",
    "Skrill", "Neteller", "WebMoney", "Payoneer", "Paysafe",
    "Payeer", "GrabPay", "PayMaya", "MoMo", "TrueMoney",
    "Touch n Go", "GoPay", "JKOPay", "EasyPaisa",
    "Paytm", "UPI", "PayU", "PayUBiz", "PayUMoney", "CCAvenue",
    "Mercado Pago", "PagSeguro", "Yandex.Checkout", "PayFort", "MyFatoorah",
    "Kushki", "RuPay", "BharatPe", "Midtrans", "MOLPay",
    "iPay88", "KakaoPay", "Toss Payments", "NaverPay",
    "Bizum", "Culqi", "Pagar.me", "Rapyd", "PayKun", "Instamojo",
    "PhonePe", "BharatQR", "Freecharge", "Mobikwik", "BillDesk",
    "Citrus Pay", "RazorpayX", "Cashfree",
    "Klarna", "Affirm", "Afterpay",
    "Splitit", "Perpay", "Quadpay", "Laybuy", "Openpay",
    "Cashalo", "Hoolah", "Pine Labs", "ChargeAfter",
    "BitPay", "Coinbase Commerce", "CoinGate", "CoinPayments", "Crypto.com Pay",
    "BTCPay Server", "NOWPayments", "OpenNode", "Utrust", "MoonPay",
    "Binance Pay", "CoinsPaid", "BitGo", "Flexa",
    "ACI Worldwide", "Bank of America Merchant Services",
    "JP Morgan Payment Services", "Wells Fargo Payment Solutions",
    "Deutsche Bank Payments", "Barclaycard", "American Express Payment Gateway",
    "Discover Network", "UnionPay", "JCB Payment Gateway",
]