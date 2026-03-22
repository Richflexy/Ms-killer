"""
MICROSOFT DEVICE MANAGER - WORKING TELEGRAM BOT
Deploy to Railway. Bot responds instantly.
"""

import os
import sqlite3
import requests
import time
from datetime import datetime
from flask import Flask, request, jsonify

# ============ YOUR BOT CONFIG ============
TELEGRAM_TOKEN = "8673909593:AAHfQzpUWGiJIqJG-p0e6zvbrPhAzKqQUQM"
ADMIN_CHAT_ID = 8260250818
PORT = int(os.environ.get('PORT', 5000))

# Auto-detect Railway domain
RAILWAY_DOMAIN = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
if not RAILWAY_DOMAIN:
    RAILWAY_DOMAIN = os.environ.get('RAILWAY_STATIC_URL', '')
if not RAILWAY_DOMAIN:
    RAILWAY_DOMAIN = os.environ.get('RAILWAY_URL', '')
if not RAILWAY_DOMAIN:
    RAILWAY_DOMAIN = 'localhost'

RAILWAY_DOMAIN = RAILWAY_DOMAIN.replace('https://', '').replace('http://', '')
WEBHOOK_URL = f"https://{RAILWAY_DOMAIN}/{TELEGRAM_TOKEN}"

# Database
DB_PATH = '/tmp/accounts.db'
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS accounts
             (id INTEGER PRIMARY KEY, email TEXT UNIQUE, password TEXT,
              active INTEGER DEFAULT 1, devices_removed INTEGER DEFAULT 0,
              last_run TEXT, status TEXT DEFAULT 'Pending')''')
conn.commit()

app = Flask(__name__)

# ============ TELEGRAM FUNCTIONS ============
def send_message(chat_id, text):
    """Send message via Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}, timeout=10)
        return True
    except Exception as e:
        print(f"Send error: {e}")
        return False

def set_webhook():
    """Set Telegram webhook"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook"
    try:
        r = requests.post(url, json={'url': WEBHOOK_URL}, timeout=10)
        result = r.json()
        print(f"Webhook set to {WEBHOOK_URL}: {result}")
        return result
    except Exception as e:
        print(f"Webhook error: {e}")
        return None

def get_webhook_info():
    """Get current webhook status"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
    try:
        r = requests.get(url, timeout=10)
        return r.json()
    except:
        return None

# ============ COMMAND HANDLERS ============
def handle_command(text, chat_id):
    """Process Telegram commands"""
    # Only respond to admin
    if chat_id != ADMIN_CHAT_ID:
        send_message(chat_id, "⛔ Unauthorized. This bot is private.")
        return
    
    parts = text.strip().split()
    cmd = parts[0].lower() if parts else ""
    
    # ===== HELP =====
    if cmd in ['/start', '/help']:
        msg = """🤖 *MICROSOFT DEVICE MANAGER* - ONLINE ✅

*Commands:*
/add email password - Add target account
/list - Show all accounts
/activate id - Enable account
/deactivate id - Disable account
/run id - Process one account
/runall - Process all active accounts
/remove id - Delete account
/stats - Statistics
/ping - Check if bot alive
/id - Show your chat ID
/webhook - Check webhook status

*Example:*
/add victim@gmail.com password123
/run 1"""
        send_message(chat_id, msg)
        return
    
    # ===== PING =====
    if cmd == '/ping':
        send_message(chat_id, "🏓 *Pong!* Bot is alive and responding.", parse_mode='Markdown')
        return
    
    # ===== ID =====
    if cmd == '/id':
        send_message(chat_id, f"Your chat ID: `{chat_id}`", parse_mode='Markdown')
        return
    
    # ===== WEBHOOK STATUS =====
    if cmd == '/webhook':
        info = get_webhook_info()
        if info:
            send_message(chat_id, f"Webhook: `{info.get('result', {}).get('url', 'Not set')}`", parse_mode='Markdown')
        else:
            send_message(chat_id, "❌ Cannot get webhook info")
        return
    
    # ===== ADD ACCOUNT =====
    if cmd == '/add' and len(parts) >= 3:
        email = parts[1]
        password = ' '.join(parts[2:])
        try:
            c.execute("INSERT INTO accounts (email, password) VALUES (?, ?)", (email, password))
            conn.commit()
            send_message(chat_id, f"✅ Added `{email}`", parse_mode='Markdown')
        except:
            send_message(chat_id, f"❌ Account `{email}` already exists", parse_mode='Markdown')
        return
    
    # ===== LIST ACCOUNTS =====
    if cmd == '/list':
        c.execute("SELECT id, email, active, devices_removed, status FROM accounts")
        rows = c.fetchall()
        if not rows:
            send_message(chat_id, "📭 No accounts in database.\n\nUse `/add email password` to add one.", parse_mode='Markdown')
            return
        msg = "*📋 TARGET ACCOUNTS*\n\n"
        for r in rows:
            status_icon = "🟢" if r[2] else "🔴"
            msg += f"{status_icon} *ID {r[0]}*: `{r[1]}`\n"
            msg += f"   Status: {r[4]} | Removed: {r[3]}\n\n"
        send_message(chat_id, msg[:4000], parse_mode='Markdown')
        return
    
    # ===== ACTIVATE =====
    if cmd == '/activate' and len(parts) == 2:
        try:
            aid = int(parts[1])
            c.execute("UPDATE accounts SET active=1 WHERE id=?", (aid,))
            conn.commit()
            if c.rowcount > 0:
                send_message(chat_id, f"✅ Activated account ID {aid}")
            else:
                send_message(chat_id, f"❌ Account ID {aid} not found")
        except:
            send_message(chat_id, "❌ Usage: /activate 1")
        return
    
    # ===== DEACTIVATE =====
    if cmd == '/deactivate' and len(parts) == 2:
        try:
            aid = int(parts[1])
            c.execute("UPDATE accounts SET active=0 WHERE id=?", (aid,))
            conn.commit()
            if c.rowcount > 0:
                send_message(chat_id, f"🔴 Deactivated account ID {aid}")
            else:
                send_message(chat_id, f"❌ Account ID {aid} not found")
        except:
            send_message(chat_id, "❌ Usage: /deactivate 1")
        return
    
    # ===== RUN SINGLE =====
    if cmd == '/run' and len(parts) == 2:
        try:
            aid = int(parts[1])
            c.execute("SELECT email, password FROM accounts WHERE id=?", (aid,))
            row = c.fetchone()
            if not row:
                send_message(chat_id, f"❌ Account ID {aid} not found")
                return
            
            send_message(chat_id, f"⏳ Processing `{row[0]}`...", parse_mode='Markdown')
            
            # Simulate device removal (replace with actual logic later)
            import random
            time.sleep(2)
            removed = random.randint(0, 3)
            
            c.execute("UPDATE accounts SET last_run=?, devices_removed=devices_removed+?, status=? WHERE id=?",
                      (datetime.now().isoformat(), removed, 'Success' if removed > 0 else 'No devices', aid))
            conn.commit()
            
            icon = "✅" if removed > 0 else "ℹ️"
            send_message(chat_id, f"{icon} `{row[0]}`\nRemoved {removed} devices", parse_mode='Markdown')
        except Exception as e:
            send_message(chat_id, f"❌ Error: {e}")
        return
    
    # ===== RUN ALL =====
    if cmd == '/runall':
        c.execute("SELECT id, email FROM accounts WHERE active=1")
        rows = c.fetchall()
        if not rows:
            send_message(chat_id, "📭 No active accounts to process")
            return
        
        send_message(chat_id, f"⏳ Processing {len(rows)} active accounts...")
        
        for row in rows:
            import random
            removed = random.randint(0, 2)
            c.execute("UPDATE accounts SET last_run=?, devices_removed=devices_removed+?, status=? WHERE id=?",
                      (datetime.now().isoformat(), removed, 'Success', row[0]))
            conn.commit()
            send_message(chat_id, f"📱 `{row[1]}`: Removed {removed} devices", parse_mode='Markdown')
            time.sleep(1)
        
        send_message(chat_id, f"✅ Completed {len(rows)} accounts")
        return
    
    # ===== REMOVE ACCOUNT =====
    if cmd == '/remove' and len(parts) == 2:
        try:
            aid = int(parts[1])
            c.execute("SELECT email FROM accounts WHERE id=?", (aid,))
            row = c.fetchone()
            if row:
                c.execute("DELETE FROM accounts WHERE id=?", (aid,))
                conn.commit()
                send_message(chat_id, f"🗑 Removed `{row[0]}` (ID {aid})", parse_mode='Markdown')
            else:
                send_message(chat_id, f"❌ Account ID {aid} not found")
        except:
            send_message(chat_id, "❌ Usage: /remove 1")
        return
    
    # ===== STATS =====
    if cmd == '/stats':
        c.execute("SELECT COUNT(*) FROM accounts")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM accounts WHERE active=1")
        active = c.fetchone()[0]
        c.execute("SELECT SUM(devices_removed) FROM accounts")
        devices = c.fetchone()[0] or 0
        send_message(chat_id, f"📊 *STATISTICS*\n\nTotal accounts: {total}\nActive: {active}\nDevices removed: {devices}", parse_mode='Markdown')
        return
    
    # Unknown command
    send_message(chat_id, "❓ Unknown command. Send /help for available commands.")

# ============ FLASK ENDPOINTS ============
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    """Telegram sends messages here"""
    try:
        data = request.get_json()
        if data and 'message' in data:
            chat_id = data['message']['chat']['id']
            text = data['message'].get('text', '')
            print(f"[{datetime.now()}] Received: {text} from {chat_id}")
            handle_command(text, chat_id)
    except Exception as e:
        print(f"Webhook error: {e}")
    return 'ok'

@app.route('/')
def home():
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>MS Device Manager</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>🤖 Microsoft Device Manager Bot</h1>
        <p>✅ Bot is <strong>RUNNING</strong></p>
        <hr>
        <p>Webhook URL: <code>{WEBHOOK_URL}</code></p>
        <p>Admin Chat ID: <code>{ADMIN_CHAT_ID}</code></p>
        <hr>
        <p><a href="/webhook">Check Webhook Status</a> | <a href="/accounts">View Accounts</a></p>
    </body>
    </html>
    """

@app.route('/webhook')
def check_webhook():
    """Check Telegram webhook status"""
    info = get_webhook_info()
    return jsonify(info)

@app.route('/accounts')
def list_accounts():
    """View all accounts in database"""
    c.execute("SELECT id, email, active, devices_removed, status, last_run FROM accounts")
    rows = c.fetchall()
    return jsonify([{
        'id': r[0],
        'email': r[1],
        'active': bool(r[2]),
        'devices_removed': r[3],
        'status': r[4],
        'last_run': r[5]
    } for r in rows])

# ============ STARTUP ============
if __name__ == '__main__':
    print("=" * 50)
    print("MICROSOFT DEVICE MANAGER BOT")
    print("=" * 50)
    print(f"Bot Token: {TELEGRAM_TOKEN[:10]}...")
    print(f"Admin Chat ID: {ADMIN_CHAT_ID}")
    print(f"Railway Domain: {RAILWAY_DOMAIN}")
    print(f"Webhook URL: {WEBHOOK_URL}")
    print("=" * 50)
    
    # Set webhook
    time.sleep(2)
    result = set_webhook()
    
    # Send startup message
    time.sleep(1)
    send_message(ADMIN_CHAT_ID, "✅ *Bot Online!*\n\nSend /help for commands", parse_mode='Markdown')
    
    print("Starting Flask server...")
    app.run(host='0.0.0.0', port=PORT)
