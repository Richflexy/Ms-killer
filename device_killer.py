import time
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_driver():
    """Configure and return Chrome driver for headless operation"""
    options = Options()
    for opt in Config.CHROME_OPTIONS:
        options.add_argument(opt)
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def process_account(account):
    """
    Log into Microsoft account and remove all devices.
    Returns: dict with success, devices_removed, message
    """
    driver = None
    devices_removed = 0
    
    try:
        logger.info(f"[*] Processing account: {account.email}")
        driver = setup_driver()
        driver.set_page_load_timeout(30)
        
        # === LOGIN PHASE ===
        driver.get("https://login.live.com")
        wait = WebDriverWait(driver, 20)
        
        # Enter email
        email_input = wait.until(EC.presence_of_element_located((By.NAME, "loginfmt")))
        email_input.clear()
        email_input.send_keys(account.email)
        driver.find_element(By.ID, "idSIButton9").click()
        time.sleep(2)
        
        # Enter password
        password_input = wait.until(EC.presence_of_element_located((By.NAME, "passwd")))
        password_input.clear()
        password_input.send_keys(account.password)
        driver.find_element(By.ID, "idSIButton9").click()
        time.sleep(3)
        
        # Check current URL for MFA or error
        current_url = driver.current_url.lower()
        if "verify" in current_url or "mfa" in current_url or "auth" in current_url:
            return {
                'success': False, 
                'devices_removed': 0, 
                'message': 'MFA Required - Cannot bypass'
            }
        
        # Handle "Stay signed in?" prompt
        try:
            stay_btn = driver.find_element(By.ID, "idSIButton9")
            if stay_btn.is_displayed():
                stay_btn.click()
                time.sleep(1)
        except:
            pass
        
        # === DEVICES PAGE ===
        logger.info(f"[*] Navigating to devices page for {account.email}")
        driver.get("https://account.microsoft.com/devices")
        time.sleep(5)
        
        # Wait for page to load
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except:
            pass
        
        # === REMOVE DEVICES ===
        for attempt in range(4):  # Multiple attempts for dynamic content
            time.sleep(2)
            
            # Find all remove buttons and links
            remove_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Remove') or contains(text(), 'Unlink')]")
            remove_links = driver.find_elements(By.XPATH, "//a[contains(text(), 'Remove') or contains(text(), 'Unlink')]")
            remove_elements = remove_buttons + remove_links
            
            # Alternative selectors if none found
            if not remove_elements:
                remove_elements = driver.find_elements(By.CSS_SELECTOR, 
                    "[class*='remove'], [class*='Remove'], [aria-label*='remove'], [aria-label*='Remove']")
            
            if not remove_elements:
                logger.info(f"[*] No more devices found for {account.email}")
                break
            
            logger.info(f"[*] Found {len(remove_elements)} device(s) to remove for {account.email}")
            
            for btn in remove_elements:
                try:
                    # Click remove button
                    btn.click()
                    time.sleep(1)
                    
                    # Handle confirmation dialog
                    confirm_btns = driver.find_elements(By.XPATH, 
                        "//button[contains(text(), 'Yes') or contains(text(), 'Confirm') or contains(text(), 'Remove') or contains(text(), 'Unlink')]")
                    for confirm in confirm_btns:
                        if confirm.is_displayed():
                            confirm.click()
                            time.sleep(1)
                            break
                    
                    devices_removed += 1
                    logger.info(f"[+] Removed device #{devices_removed} for {account.email}")
                    time.sleep(1)
                    
                except Exception as e:
                    logger.warning(f"[!] Failed to remove device: {e}")
                    continue
            
            # Refresh to get updated list
            driver.refresh()
            time.sleep(3)
        
        # === RESULTS ===
        if devices_removed > 0:
            message = f"Successfully removed {devices_removed} device(s)"
        else:
            message = "No devices found to remove"
        
        logger.info(f"[✓] {account.email}: {message}")
        
        return {
            'success': True,
            'devices_removed': devices_removed,
            'message': message
        }
        
    except TimeoutException as e:
        logger.error(f"[!] Timeout for {account.email}: {e}")
        return {
            'success': False,
            'devices_removed': 0,
            'message': f"Timeout: {str(e)[:100]}"
        }
    except Exception as e:
        logger.error(f"[!] Error for {account.email}: {e}")
        return {
            'success': False,
            'devices_removed': 0,
            'message': f"Error: {str(e)[:100]}"
        }
    finally:
        if driver:
            driver.quit()