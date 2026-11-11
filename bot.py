import os
import sys
import re
import json
import time
import base64
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CommandHandler

# ========== الثوابت والآيدي المسموح له فقط ==========
TOKEN = "9140037494:AAErM5OM4hCIoXhk2AGeO-j0jnkeWwVTn14"
ALLOWED_USER_ID = 1506200738

CLIENT_ID_APP = "ana-vodafone-app"
CLIENT_SECRET_APP = "95fd95fb-7489-4958-8ae6-d31a525cd20a"
DEVICE_ID_APP = "498565e1edaea1ab"
DIGITAL_ID_APP = "2BAU6O130VH0O"

CLIENT_ID_VF = "AnaVF"
CLIENT_SECRET_VF = "dca0pbLUWXVhXR266Gw1iT5rqwvvJQoN"
DEVICE_ID_VF = "9b3fff03783b9ed1"
DIGITAL_ID_VF = "2EWNS11ATIXC0"

TOKEN_URL = "https://mobile.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/token"

# ========== دوال مساعدة ==========
def fix_phone_number(number):
    if not number:
        return ""
    number = re.sub(r'\D', '', str(number))
    if number.startswith('2010') and len(number) >= 12:
        return '010' + number[4:13]
    elif number.startswith('201') and len(number) >= 12:
        return '0' + number[2:12]
    elif number.startswith('1') and len(number) == 10:
        return '0' + number
    elif not number.startswith('0') and len(number) > 0:
        number = '0' + number
    return number[:11] if len(number) >= 11 else number

def is_phone_line(text):
    cleaned = fix_phone_number(text)
    has_letters = bool(re.search(r'[a-zA-Z]', text))
    return len(cleaned) == 11 and cleaned.startswith("010") and not has_letters

def parse_accounts_input(text_content):
    accounts = []
    clean_lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    i = 0
    while i < len(clean_lines):
        line = clean_lines[i]
        sep_match = re.split(r'[,،:\t]+|\s+', line, maxsplit=1)
        if len(sep_match) == 2 and is_phone_line(sep_match[0]):
            phone = fix_phone_number(sep_match[0])
            pwd = sep_match[1].strip()
            if pwd:
                accounts.append((phone, pwd))
                i += 1
                continue

        if is_phone_line(line) and (i + 1) < len(clean_lines):
            phone = fix_phone_number(line)
            pwd = clean_lines[i + 1].strip()
            accounts.append((phone, pwd))
            i += 2
            continue
        i += 1
    return accounts

def decode_jwt(token):
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1].replace('-', '+').replace('_', '/')
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.b64decode(payload).decode('utf-8'))
        if isinstance(data.get("userInfo"), str):
            try:
                data["userInfo"] = json.loads(data["userInfo"])
            except Exception:
                pass
        return data
    except Exception:
        return {}

def format_arabic_time_with_period(dt):
    if not dt:
        return 'غير معروف'
    try:
        hour = dt.hour
        period = 'صباحاً' if hour < 12 else 'مساءً'
        h12 = hour % 12 or 12
        return f"{dt.strftime('%Y-%m-%d')} {h12:02d}:{dt.minute:02d}:{dt.second:02d} {period}"
    except Exception:
        return str(dt)

def friendly_plan_name(technical_name):
    if not technical_name:
        return "-"
    name = str(technical_name).strip()
    name_lower = name.lower()
    if "raya7" in name_lower or "14pt" in name_lower:
        return "ريح بالك كله ب 14 قرش"
    match = re.search(r'flex[_\s-]*(\d+)', name_lower)
    if match:
        number = match.group(1)
        if "business" in name_lower:
            return f"فلكس بيزنس{number}"
        return f"فلكس{number}"
    return name

def parse_iso_datetime(date_str):
    if not date_str:
        return None
    try:
        s = str(date_str).replace("Z", "").split("+")[0].split(".")[0]
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    except Exception:
        try:
            s = str(date_str).split("T")[0]
            return datetime.strptime(s, "%Y-%m-%d")
        except Exception:
            return None

# ========== تسجيل الدخول ==========
def login_app_client(msisdn, password):
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Connection': 'keep-alive',
        'silentLogin': 'true',
        'x-agent-operatingsystem': '10',
        'clientId': 'AnaVodafoneAndroid',
        'Accept-Language': 'ar',
        'x-agent-device': 'HUAWEI PCT-L29',
        'x-agent-version': '2025.10.3',
        'x-agent-build': '1050',
        'digitalId': DIGITAL_ID_APP,
        'device-id': DEVICE_ID_APP,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'mobile.vodafone.com.eg',
        'User-Agent': 'okhttp/4.12.0',
    }
    data = {
        'grant_type': 'password',
        'username': msisdn,
        'password': password,
        'client_secret': CLIENT_SECRET_APP,
        'client_id': CLIENT_ID_APP,
    }
    try:
        r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)
        if r.status_code == 200:
            return r.json().get('access_token'), None
        return None, f"كود {r.status_code}"
    except Exception as e:
        return None, str(e)

def login_vf_client(msisdn, password):
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Connection': 'keep-alive',
        'silentLogin': 'true',
        'msisdn': msisdn,
        'x-agent-operatingsystem': '17',
        'clientId': 'AnaVodafoneAndroid',
        'Accept-Language': 'ar',
        'x-agent-device': 'Samsung SM-S928B',
        'x-agent-version': '2026.8.4',
        'x-agent-build': '1208',
        'digitalId': DIGITAL_ID_VF,
        'device-id': DEVICE_ID_VF,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': 'mobile.vodafone.com.eg',
        'User-Agent': 'okhttp/4.12.0',
    }
    data = {
        'grant_type': 'password',
        'username': msisdn,
        'password': password,
        'client_secret': CLIENT_SECRET_VF,
        'client_id': CLIENT_ID_VF,
    }
    try:
        r = requests.post(TOKEN_URL, headers=headers, data=data, timeout=30)
        if r.status_code == 200:
            return r.json().get('access_token'), None
        return None, f"كود {r.status_code}"
    except Exception as e:
        return None, str(e)

# ========== 1. تفاصيل الخط ==========
def fetch_line_inspector(msisdn, token):
    payload = decode_jwt(token)
    ui = payload.get('userInfo', {}) if isinstance(payload.get('userInfo'), dict) else {}
    
    full_name = f"{ui.get('firstName','')} {ui.get('lastName','')}".strip() or "-"
    sim_raw = str(ui.get('sim', ''))
    sim_masked = f"***{sim_raw[-5:]}" if len(sim_raw) >= 5 else "***-----"

    lines = [
        "🔍 1 تقرير معرفة نظام الخط:",
        f"   • الاسم: {full_name}",
        f"   • الرقم: {ui.get('msisdn', msisdn)}",
        f"   • اسم النظام: {friendly_plan_name(ui.get('serviceClassName', '-'))}",
        f"   • سريال الشريحة SIM: {sim_masked}"
    ]
    return "\n".join(lines)

# ========== 2. الاستعلام الشامل ==========
def fetch_full_inquiry(msisdn, token):
    url = "https://mobile.vodafone.com.eg/services/dxl/usage/usageConsumptionReport"
    headers = {
        'api-host': 'usageConsumptionHost', 'useCase': 'aggregated',
        'Authorization': f'Bearer {token}', 'api-version': 'v2',
        'device-id': DEVICE_ID_APP, 'x-agent-operatingsystem': '10',
        'clientId': 'AnaVodafoneAndroid', 'x-agent-device': 'HUAWEI PCT-L29',
        'x-agent-version': '2025.10.3', 'x-agent-build': '1050',
        'msisdn': msisdn, 'Content-Type': 'application/json',
        'Accept': 'application/json', 'Accept-Language': 'ar',
        'Host': 'mobile.vodafone.com.eg', 'Connection': 'Keep-Alive',
        'User-Agent': 'okhttp/4.12.0',
    }
    params = {'@type': 'aggregated', 'bucket.product.publicIdentifier': msisdn}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code != 200:
            return "   • ❌ تعذر جلب الاستهلاك"
        consumption_data = r.json()
    except Exception:
        return "   • ❌ خطأ في الاتصال"

    if not isinstance(consumption_data, list):
        return "   • ⚠️ لا توجد بيانات"

    flex_expiry = "منتهية ❌"
    for item in consumption_data:
        if item.get('@type') == 'FLEX':
            for bucket in item.get('bucket', []):
                for bal in bucket.get('bucketBalance', []):
                    if bal.get('@type') == 'Remaining':
                        end_str = bal.get('validFor', {}).get('endDateTime')
                        if end_str:
                            expiry = end_str.split('T')[0]
                            try:
                                if datetime.strptime(expiry, '%Y-%m-%d').date() >= datetime.now().date():
                                    flex_expiry = f"تنتهي في {expiry} 🟢"
                            except Exception:
                                pass

    balance_amount, balance_units = "0.00", "LE"
    for item in consumption_data:
        if item.get('id') == '523' and 'bucket' in item:
            for b in item['bucket']:
                for bal in b.get('bucketBalance', []):
                    if bal.get('@type') == 'Remaining':
                        balance_amount = bal.get('remainingValue', {}).get('amount', 0)
                        balance_units = bal.get('remainingValue', {}).get('units', 'LE')
                        break

    target_keywords = ["acp/rx", "mike alnota", "esp eligibility", "stamp tax", "acp"]
    eligible_nota = False
    for service in consumption_data:
        if service.get('@type') == 'OTHERS':
            for bucket in service.get('bucket', []):
                products = bucket.get('product', [])
                product_str = " + ".join([p.get('name', '') for p in products if p.get('name')]).lower()
                if all(k in product_str for k in target_keywords) and bucket.get('usageType') == 'monetary':
                    for bal in bucket.get('bucketBalance', []):
                        if bal.get('@type') == 'Remaining':
                            rem = bal.get('remainingValue', {}).get('amount')
                            if rem is not None and rem >= 110000:
                                eligible_nota = True

    nota_status = "✅ مؤهل للتجديد على النوتة" if eligible_nota else "❌ غير مؤهل للتجديد على النوتة"

    lines = [
        f"   • صلاحية الباقة: {flex_expiry}",
        f"   • الرصيد المتاح: {balance_amount} {balance_units}",
        f"   • أهلية النوتة: {nota_status}"
    ]
    return "\n".join(lines)

# ========== 3. الاشتراكات والمستحقات ==========
def fetch_subscriptions_and_dues(msisdn, token):
    headers = {
        "api-host": "ProductInventoryManagementHost", "useCase": "AllInOne",
        "Authorization": f"Bearer {token}", "api-version": "v2",
        "device-id": DEVICE_ID_VF, "x-agent-operatingsystem": "17",
        "clientId": "AnaVodafoneAndroid", "x-agent-device": "Samsung SM-S928B",
        "x-agent-version": "2026.8.4", "x-agent-build": "1208",
        "msisdn": msisdn, "Content-Type": "application/json",
        "Accept": "application/json", "Accept-Language": "ar",
        "Host": "mobile.vodafone.com.eg", "User-Agent": "okhttp/4.12.0",
    }
    params = {"relatedParty.id": msisdn, "@type": "AllInOne", "relatedParty.name": "SubscriptionManagement"}
    try:
        r = requests.get("https://mobile.vodafone.com.eg/services/dxl/pim/product", headers=headers, params=params, timeout=30)
        data = r.json() if r.status_code == 200 else []
    except Exception:
        return "📋 3 الاشتراكات والمستحقات:\n   • ❌ خطأ في جلب البيانات"

    pay_on_recharge = []
    monthly_subs = []

    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id", "")
            if item_id == "Credit_RestOfSalefny":
                continue
            name = item_id
            if item.get("productPrice") and item["productPrice"][0].get("description"):
                name = item["productPrice"][0]["description"].strip()
            elif item_id == "Credit_StampTax":
                name = "ضريبة الدمغة"
            elif item_id == "Credit_ACPFees":
                name = "رسوم إدارية (ACP)"

            price = 0.0
            if item.get("productPrice"):
                try:
                    price = int(item["productPrice"][0]["price"]["taxIncludedAmount"]["value"]) / 100
                except Exception:
                    pass

            renewal_date = None
            for c in item.get("characteristic") or []:
                if c.get("name") == "RenewalDate" and c.get("value") and c.get("value") != "null":
                    renewal_date = c.get("value")

            if renewal_date:
                monthly_subs.append({"name": name, "price": price, "date": renewal_date})
            elif price > 0:
                pay_on_recharge.append({"name": name, "price": price})

    total_recharge = sum(i["price"] for i in pay_on_recharge)

    lines = ["📋 3 الاشتراكات والمستحقات:"]
    if pay_on_recharge:
        details_list = [f"{i['name']} ({i['price']:g}ج)" for i in pay_on_recharge]
        details_str = "\n\n ".join(details_list)
        lines.append(f"   • تسدد عند الشحن: 🔴 {details_str}\n")
        lines.append(f"   • إجمالي الشحن المطلوب: 💰 {total_recharge:g} جنيه")
    else:
        lines.append("   • تسدد عند الشحن: 🟢 لا توجد رسوم مستحقة")

    if monthly_subs:
        subs_str = ", ".join([f"{s['name']} ({s['price']:g}ج)" for s in monthly_subs])
        lines.append(f"   • الاشتراكات الشهرية: {subs_str}")
    else:
        lines.append("   • الاشتراكات الشهرية: ℹ️ لا توجد اشتراكات")

    return "\n".join(lines)

# ========== 4. حالة الماني باك ==========
def fetch_renewal_date(msisdn, token):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=32)
    headers = {
        'api-host': 'UsageManagementHost', 'Authorization': f'Bearer {token}',
        'api-version': 'v2', 'device-id': DEVICE_ID_APP,
        'x-agent-operatingsystem': '10', 'clientId': 'AnaVodafoneAndroid',
        'x-agent-device': 'HUAWEI PCT-L29', 'x-agent-version': '2025.10.3',
        'x-agent-build': '1050', 'msisdn': msisdn,
        'Content-Type': 'application/json', 'Accept': 'application/json',
        'Accept-Language': 'ar', 'Host': 'mobile.vodafone.com.eg',
        'Connection': 'Keep-Alive', 'User-Agent': 'okhttp/4.12.0',
    }
    params = {
        'relatedParty.id': msisdn,
        'validFor.startDateTime': str(int(start_date.timestamp() * 1000)),
        '@type': 'BalanceDetails',
        'validFor.endDateTime': str(int(end_date.timestamp() * 1000)),
    }
    try:
        r = requests.get('https://mobile.vodafone.com.eg/services/dxl/usagemng/usage', params=params, headers=headers, timeout=30)
        if r.status_code != 200:
            return "حالة الماني باك :\n   • الحالة: ❌ تعذر الفحص"
        data = r.json()
    except Exception:
        return "حالة الماني باك :\n   • الحالة: ❌ خطأ في الاتصال"

    items = data if isinstance(data, list) else (data.get('usage') or data.get('balanceDetails') or data.get('data') or [])
    bundle_keywords = ['باقة', 'فليكس', 'flex', 'ميجا', 'كارت', 'عرض', 'باقه']
    refunded_packages = []
    for item in items:
        if not isinstance(item, dict):
            continue
        description = item.get('description', '')
        date_str = item.get('date', '')
        amount = 0
        rated_usage = item.get('ratedProductUsage', [])
        if isinstance(rated_usage, list) and rated_usage and isinstance(rated_usage[0], dict):
            amount = rated_usage[0].get('taxIncludedRatingAmount', 0)
        item_date = parse_iso_datetime(date_str)
        if any(k in description.lower() for k in bundle_keywords) and amount > 0:
            refunded_packages.append({'date': item_date, 'description': description, 'amount': amount})

    refunded_packages.sort(key=lambda x: x['date'] if x['date'] else datetime.min, reverse=True)
    
    if not refunded_packages:
        return "حالة الماني باك :\n   • الحالة:  مؤهل للتجديد الآن (لا يوجد استرداد خلال 32 يوماً)✅✅"
    else:
        latest = refunded_packages[0]
        dt_str = format_arabic_time_with_period(latest['date']) if latest['date'] else "غير معروف"
        return f"حالة الماني باك :\n   • الحالة: غير مؤهل (تم الاسترداد في {dt_str})❌"

def process_single_account(phone, pwd, index=None, total=None):
    msisdn = fix_phone_number(phone)
    if len(msisdn) != 11:
        return f"❌ الرقم ({phone}) غير صحيح!"

    token_app, err_app = login_app_client(msisdn, pwd)
    token_vf, err_vf = login_vf_client(msisdn, pwd)
    token_app = token_app or token_vf
    token_vf = token_vf or token_app

    if not token_app and not token_vf:
        return f"❌ فشل تسجيل الدخول للرقم: {msisdn}\n⚠️ تأكد من الرقم وكلمة المرور."

    p1 = fetch_line_inspector(msisdn, token_vf)
    p2 = fetch_full_inquiry(msisdn, token_app)
    p3 = fetch_subscriptions_and_dues(msisdn, token_vf)
    p4 = fetch_renewal_date(msisdn, token_app)

    card = (
        f"╔══════════════════════════════╗\n"
        f" 🚀 تقرير الرقم: {msisdn} {f'({index}/{total})' if index else ''}\n"
        f"╚══════════════════════════════╝\n\n"
        f"{p1}\n──────────────────\n"
        f"{p2}\n──────────────────────────────\n"
        f"{p3}\n──────────────────────────────\n"
        f"{p4}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    return card

# ========== استقبال رسائل التيليجرام ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ عذراً، هذا البوت مخصص للاستخدام الشخصي فقط.")
        return

    text = update.message.text
    if not text:
        return

    accounts = parse_accounts_input(text)
    if not accounts:
        await update.message.reply_text("⚠️ لم يتم التعرف على أي أرقام وباسووردات بالرسالة.")
        return

    total = len(accounts)
    await update.message.reply_text(f"✅ تم استلام {total} رقم. جاري الفحص... ⏳")

    for idx, (phone, pwd) in enumerate(accounts, 1):
        try:
            report = process_single_account(phone, pwd, index=idx, total=total)
            await update.message.reply_text(report)
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ أثناء فحص الرقم {phone}: {e}")

    await update.message.reply_text(f"🎉 اكتمل فحص جميع الأرقام بنجاح! ({total} رقم) ✨")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    await update.message.reply_text("🤖 أهلاً بك! أرسل الأرقام والباسووردات دفعة واحدة وسأقوم بفحصها فوراً.")

# ========== سيرفر وهمي لإبقاء الاستضافة المجانية نشطة ==========
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")
    def log_message(self, format, *args):
        return

def keep_alive():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

def main():
    threading.Thread(target=keep_alive, daemon=True).start()
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🤖 البوت يعمل الآن...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
