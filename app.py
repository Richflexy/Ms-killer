"""
MICROSOFT DEVICE KILLER - ALL IN ONE
Deploy to Railway.com - One file, everything included
"""

import os
import time
import logging
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# ============ CONFIGURATION ============
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8673909593:AAHfQzpUWGiJIqJG-p0e6zvbrPhAzKqQUQM')
ADMIN_CHAT_ID = int(os.environ.get('ADMIN_CHAT_ID', '8260250818'))
PORT = int(os.environ.get('PORT', 5000))

# Database setup
DB_PATH = '/tmp/accounts.db'  # Use /tmp for Railway
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

# ============ TELEGRAM FUNCTIONS ============
def send_telegram(chat_id, text):
    """Send message via Telegram"""
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}, timeout=10)
    except:
        pass

def handle_telegram_command(text, chat_id):
    """Process Telegram commands"""
    if chat_id != ADMIN_CHAT_ID:
        send_telegram(chat_id, "⛔ Unauthorized")
        return
    
    parts = text.strip().split()
    cmd = parts[0].lower() if parts else ""
    
    # /start or /help
    if cmd in ['/start', '/help']:
        msg = """🔐 *MS DEVICE KILLER*
        
Commands:
/add email pass - Add account
/list - Show accounts
/activate id - Enable
/deactivate id - Disable
/run id - Process one
/runall - Process all active
/remove id - Delete
/stats - Show totals"""
        send_telegram(chat_id, msg)
        return
    
    # /add email password
    if cmd == '/add' and len(parts) >= 3:
        email = parts[1]
        password = ' '.join(parts[2:])
        try:
            cursor.execute("INSERT INTO accounts (email, password) VALUES (?, ?)", (email, password))
            conn.commit()
            send_telegram(chat_id, f"✅ Added {email}")
        except:
            send_telegram(chat_id, f"❌ Already exists")
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
        send_telegram(chat_id, msg[:4000])
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

# ============ WEBHOOK ENDPOINT ============
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    data = request.get_json()
    if data and 'message' in data:
        chat_id = data['message']['chat']['id']
        text = data['message'].get('text', '')
        handle_telegram_command(text, chat_id)
    return 'ok'

@app.route('/')
def home():
    return 'Microsoft Device Killer Bot Running'

@app.route('/cron', methods=['GET', 'POST'])
def cron():
    """Cron job endpoint - runs automatically every 5 minutes via Railway Cron"""
    import requests
    
    # Get all active accounts
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
        
        # Log to Telegram
        icon = "✅" if result['success'] else "❌"
        send_telegram(ADMIN_CHAT_ID, f"{icon} {row[1]}\n{result['msg']}")
        results.append(f"{row[1]}: {result['msg']}")
        time.sleep(2)
    
    return f'Processed {len(rows)} accounts\n' + '\n'.join(results)

# ============ MAIN ============
if __name__ == '__main__':
    # Set webhook
    import requests
    webhook_url = f"https://{os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'localhost')}/{TELEGRAM_TOKEN}"
    requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}")
    
    app.run(host='0.0.0.0', port=PORT)
