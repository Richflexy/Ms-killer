import os

class Config:
    # Telegram Configuration
    TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '8673909593:AAHfQzpUWGiJIqJG-p0e6zvbrPhAzKqQUQM')
    ADMIN_CHAT_ID = int(os.environ.get('ADMIN_CHAT_ID', '8260250818'))
    
    # Database
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///accounts.db')
    
    # Chrome/Selenium Configuration
    CHROME_OPTIONS = [
        '--headless=new',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--disable-blink-features=AutomationControlled',
        '--window-size=1920,1080',
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
    ]
    
    # Scheduling (in seconds)
    AUTO_SCAN_INTERVAL = int(os.environ.get('AUTO_SCAN_INTERVAL', 300))  # 5 minutes
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY', 'microsoft-device-killer-secret-key-2024')