from flask import Flask, jsonify
from database import SessionLocal, TargetAccount, ExecutionLog
from config import Config
import os

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Microsoft Device Manager</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>🔐 Microsoft Device Manager Bot</h1>
        <p>Bot is running. Use Telegram for control.</p>
        <p>Admin Chat ID: {}</p>
        <hr>
        <p><small>Deployed on Railway | Auto-scan every {} seconds</small></p>
    </body>
    </html>
    """.format(Config.ADMIN_CHAT_ID, Config.AUTO_SCAN_INTERVAL)

@app.route('/health')
def health():
    return jsonify({"status": "ok", "auto_scan_interval": Config.AUTO_SCAN_INTERVAL})

@app.route('/stats')
def stats():
    db = SessionLocal()
    try:
        total = db.query(TargetAccount).count()
        active = db.query(TargetAccount).filter_by(active=True).count()
        total_devices = db.query(TargetAccount).with_entities(TargetAccount.devices_removed).all()
        devices_sum = sum(d[0] for d in total_devices)
        
        return jsonify({
            "total_accounts": total,
            "active_accounts": active,
            "total_devices_removed": devices_sum
        })
    finally:
        db.close()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)