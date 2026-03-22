"""
MICROSOFT DEVICE MANAGER - NO SELENIUM
Pure API calls. Runs on Railway free tier with 50MB RAM.
Requires: One-time setup to get refresh token (instructions below)
"""

import os
import time
import sqlite3
import requests
import threading
from datetime import datetime

# ============ CONFIGURATION ============
TELEGRAM_TOKEN = "8673909593:AAHfQzpUWGiJIqJG-p0e6zvbrPhAzKqQUQM"
ADMIN_CHAT_ID = 8260250818

# Microsoft Graph API credentials
CLIENT_ID = "d3590ed6-52b3-4102-aeff-aad2292ab01c"  # Microsoft's official client ID for device management
REFRESH_TOKEN = None  # Will be stored in database after first setup

# Database
DB_PATH = "/tmp/accounts.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS accounts
             (id INTEGER PRIMARY KEY, email TEXT UNIQUE, refresh_token TEXT,
              access_token TEXT, token_expires TEXT, active INTEGER DEFAULT 1,
              devices_removed INTEGER DEFAULT 0, last_run TEXT, status TEXT DEFAULT 'Pending')''')
c.execute('''CREATE TABLE IF NOT EXISTS logs
             (id INTEGER PRIMARY KEY, account_email TEXT, action TEXT, 
              result TEXT, details TEXT, timestamp TEXT)''')
conn.commit()

# ============ TELEGRAM FUNCTIONS ============
def send_msg(chat_id, text):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                      json={'chat_id': chat_id, 'text': text, 'parse_mode': 'Markdown'}, timeout=10)
    except:
        pass

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {'timeout': 30}
    if offset:
        params['offset'] = offset
    try:
        r = requests.get(url, params=params, timeout=35)
        return r.json().get('result', [])
    except:
        return []

# ============ MICROSOFT GRAPH API ============
def refresh_access_token(refresh_token):
    """Exchange refresh token for new access token"""
    url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    data = {
        'client_id': CLIENT_ID,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
        'scope': 'https://graph.microsoft.com/Device.ReadWrite.All User.Read'
    }
    try:
        r = requests.post(url, data=data, timeout=15)
        if r.status_code == 200:
            token_data = r.json()
            return {
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token', refresh_token),
                'expires_in': token_data['expires_in']
            }
        return None
    except:
        return None

def get_devices(access_token):
    """Get list of devices linked to account"""
    url = "https://graph.microsoft.com/v1.0/devices"
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json().get('value', [])
        return None
    except:
        return None

def delete_device(access_token, device_id):
    """Delete/unlink a device"""
    url = f"https://graph.microsoft.com/v1.0/devices/{device_id}"
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        r = requests.delete(url, headers=headers, timeout=15)
        return r.status_code == 204
    except:
        return False

def process_account(email, refresh_token):
    """Process a single account - remove all devices via API"""
    try:
        # Get fresh access token
        token_data = refresh_access_token(refresh_token)
        if not token_data:
            return False, 0, "Failed to refresh token"
        
        access_token = token_data['access_token']
        new_refresh = token_data['refresh_token']
        
        # Get all devices
        devices = get_devices(access_token)
        if devices is None:
            return False, 0, "Failed to get devices"
        
        # Delete each device
        removed = 0
        for device in devices:
            device_id = device.get('id')
            if device_id and delete_device(access_token, device_id):
                removed += 1
            time.sleep(0.5)  # Rate limit
        
        # Update refresh token if changed
        if new_refresh != refresh_token:
            c.execute("UPDATE accounts SET refresh_token=? WHERE email=?", (new_refresh, email))
            conn.commit()
        
        return True, removed, f"Removed {removed} devices" if removed > 0 else "No devices found"
    
    except Exception as e:
        return False, 0, str(e)[:100]

# ============ GET REFRESH TOKEN (ONE TIME) ============
def get_refresh_token_url():
    """Generate URL for user to get refresh token (manual step)"""
    url = f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri=https://login.microsoftonline.com/common/oauth2/nativeclient&scope=https://graph.microsoft.com/Device.ReadWrite.All%20User.Read%20offline_access"
    return url

# ============ COMMAND HANDLERS ============
def handle_command(text, chat_id):
    if chat_id != ADMIN_CHAT_ID:
        send_msg(chat_id, "Unauthorized")
        return
    
    parts = text.strip().split()
    cmd = parts[0].lower() if parts else ""
    
    # HELP
    if cmd in ['/start', '/help']:
        msg = """🔐 *MS DEVICE MANAGER* - NO SELENIUM

*First-time setup:*
1. Go to: https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=d3590ed6-52b3-4102-aeff-aad2292ab01c&response_type=code&redirect_uri=https://login.microsoftonline.com/common/oauth2/nativeclient&scope=https://graph.microsoft.com/Device.ReadWrite.All%20User.Read%20offline_access
2. Login with the Microsoft account
3. Copy the URL after redirect, get the code
4. Send: /setup <code>

*Commands:*
/add email refresh_token - Add account (after setup)
/list - Show accounts
/activate id - Enable account
/deactivate id - Disable
/run id - Process one account
/runall - Process all active
/remove id - Delete
/stats - Statistics"""
        send_msg(chat_id, msg)
        return
    
    # SETUP - Exchange code for refresh token
    if cmd == '/setup' and len(parts) == 2:
        auth_code = parts[1]
        url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        data = {
            'client_id': CLIENT_ID,
            'code': auth_code,
            'redirect_uri': 'https://login.microsoftonline.com/common/oauth2/nativeclient',
            'grant_type': 'authorization_code',
            'scope': 'https://graph.microsoft.com/Device.ReadWrite.All User.Read offline_access'
        }
        try:
            r = requests.post(url, data=data, timeout=15)
            if r.status_code == 200:
                token_data = r.json()
                refresh_token = token_data.get('refresh_token')
                if refresh_token:
                    send_msg(chat_id, f"✅ Setup complete!\n\nYour refresh token:\n`{refresh_token}`\n\nUse: /add email@example.com {refresh_token}")
                else:
                    send_msg(chat_id, "❌ No refresh token received")
            else:
                send_msg(chat_id, f"❌ Error: {r.status_code}\n{r.text[:200]}")
        except Exception as e:
            send_msg(chat_id, f"❌ Error: {e}")
        return
    
    # ADD ACCOUNT
    if cmd == '/add' and len(parts) >= 3:
        email = parts[1]
        refresh_token = parts[2]
        try:
            c.execute("INSERT INTO accounts (email, refresh_token, active) VALUES (?, ?, 1)", (email, refresh_token))
            conn.commit()
            send_msg(chat_id, f"✅ Added {email}")
        except:
            send_msg(chat_id, "❌ Account exists or error")
        return
    
    # LIST
    if cmd == '/list':
        c.execute("SELECT id, email, active, devices_removed, status FROM accounts")
        rows = c.fetchall()
        if not rows:
            send_msg(chat_id, "No accounts")
            return
        msg = "*Accounts*\n"
        for r in rows:
            status = "🟢" if r[2] else "🔴"
            msg += f"{status} ID:{r[0]} {r[1]} | {r[4]} | {r[3]} removed\n"
        send_msg(chat_id, msg[:4000])
        return
    
    # ACTIVATE
    if cmd == '/activate' and len(parts) == 2:
        c.execute("UPDATE accounts SET active=1 WHERE id=?", (parts[1],))
        conn.commit()
        send_msg(chat_id, f"✅ Activated ID {parts[1]}")
        return
    
    # DEACTIVATE
    if cmd == '/deactivate' and len(parts) == 2:
        c.execute("UPDATE accounts SET active=0 WHERE id=?", (parts[1],))
        conn.commit()
        send_msg(chat_id, f"🔴 Deactivated ID {parts[1]}")
        return
    
    # RUN SINGLE
    if cmd == '/run' and len(parts) == 2:
        c.execute("SELECT email, refresh_token FROM accounts WHERE id=?", (parts[1],))
        row = c.fetchone()
        if not row:
            send_msg(chat_id, f"ID {parts[1]} not found")
            return
        
        send_msg(chat_id, f"⏳ Processing {row[0]}...")
        success, removed, msg = process_account(row[0], row[1])
        
        c.execute("UPDATE accounts SET last_run=?, devices_removed=devices_removed+?, status=? WHERE id=?",
                   (datetime.now().isoformat(), removed, 'Success' if success else 'Failed', parts[1]))
        conn.commit()
        
        icon = "✅" if success else "❌"
        send_msg(chat_id, f"{icon} {row[0]}\n{msg}")
        return
    
    # RUN ALL
    if cmd == '/runall':
        c.execute("SELECT id, email, refresh_token FROM accounts WHERE active=1")
        rows = c.fetchall()
        if not rows:
            send_msg(chat_id, "No active accounts")
            return
        
        send_msg(chat_id, f"⏳ Processing {len(rows)} accounts...")
        for row in rows:
            success, removed, msg = process_account(row[1], row[2])
            c.execute("UPDATE accounts SET last_run=?, devices_removed=devices_removed+?, status=? WHERE id=?",
                       (datetime.now().isoformat(), removed, 'Success' if success else 'Failed', row[0]))
            conn.commit()
            send_msg(chat_id, f"{row[1]}: {msg}")
            time.sleep(2)
        send_msg(chat_id, f"✅ Completed")
        return
    
    # REMOVE
    if cmd == '/remove' and len(parts) == 2:
        c.execute("DELETE FROM accounts WHERE id=?", (parts[1],))
        conn.commit()
        send_msg(chat_id, f"🗑 Removed ID {parts[1]}")
        return
    
    # STATS
    if cmd == '/stats':
        c.execute("SELECT COUNT(*), SUM(devices_removed) FROM accounts")
        total, devices = c.fetchone()
        c.execute("SELECT COUNT(*) FROM accounts WHERE active=1")
        active = c.fetchone()[0]
        send_msg(chat_id, f"📊 Stats\nTotal: {total}\nActive: {active}\nDevices removed: {devices or 0}")
        return
    
    send_msg(chat_id, "Unknown. /help")

# ============ MAIN LOOP ============
def main():
    send_msg(ADMIN_CHAT_ID, "✅ Bot started! (No Selenium)\n\nFirst, get a refresh token:\n/setup")
    
    last_id = 0
    while True:
        try:
            updates = get_updates(last_id + 1)
            for update in updates:
                if 'message' in update and 'text' in update['message']:
                    chat_id = update['message']['chat']['id']
                    text = update['message']['text']
                    handle_command(text, chat_id)
                last_id = update['update_id']
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
