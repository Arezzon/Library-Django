import logging
from time import sleep
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Logger configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

BASE_URL = "http://127.0.0.1:8000"
VALID_EMAIL = "reader@library.com"
VALID_PASSWORD = "reader123password"
INVALID_EMAIL = "wrong_user@library.com"
INVALID_PASSWORD = "wrongpassword123"


@pytest.fixture
def driver():
    """Fixture to initialize and tear down the Chrome browser."""
    logger.info("Starting Chrome Browser...")
    chrome_driver = webdriver.Chrome()
    chrome_driver.maximize_window()
    chrome_driver.get(BASE_URL)

    yield chrome_driver  # Provide driver instance to the test

    logger.info("Closing Chrome Browser...")
    chrome_driver.quit()


def test_valid_login_and_logout(driver):
    """Test 1: Successful login with valid credentials and subsequent logout."""
    wait = WebDriverWait(driver, timeout=10)
    logger.info("--- START: test_valid_login_and_logout ---")

    # 1. Click on "Log In" link in the navbar
    logger.info("1. Navigating to Login page...")
    wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Log In"))).click()

    # 2. Enter valid credentials
    logger.info(f"2. Entering valid credentials (Email: {VALID_EMAIL})...")
    email = wait.until(EC.presence_of_element_located((By.NAME, "email")))
    password = wait.until(EC.presence_of_element_located((By.NAME, "password")))
    email.send_keys(VALID_EMAIL)
    password.send_keys(VALID_PASSWORD)

    # 3. Submit the login form
    logger.info("3. Submitting login form...")
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()

    # 4. Verify successful authentication
    logger.info("4. Verifying successful authentication...")
    logout_btn = wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Log Out")))
    assert logout_btn.is_displayed(), "Log Out button should be visible after login"
    assert VALID_EMAIL in driver.page_source, f"Email '{VALID_EMAIL}' should be present on page"
    logger.info("   -> Verification passed: User is logged in.")
    sleep(1)

    # 5. Click Logout button
    logger.info("5. Clicking 'Log Out' button...")
    logout_btn.click()

    # 6. Verify user is logged out
    logger.info("6. Verifying user logged out...")
    login_btn = wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Log In")))
    assert login_btn.is_displayed(), "Log In link should be visible after logout"
    logger.info("   -> Verification passed: User successfully logged out.")
    logger.info("--- PASSED: test_valid_login_and_logout ---\n")


def test_invalid_login(driver):
    """Test 2: Attempt to login with invalid credentials -> verify error alert."""
    wait = WebDriverWait(driver, timeout=10)
    logger.info("--- START: test_invalid_login ---")

    # 1. Click on "Log In" link in the navbar
    logger.info("1. Navigating to Login page...")
    wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Log In"))).click()

    # 2. Enter invalid credentials
    logger.info(f"2. Entering invalid credentials (Email: {INVALID_EMAIL})...")
    email = wait.until(EC.presence_of_element_located((By.NAME, "email")))
    password = wait.until(EC.presence_of_element_located((By.NAME, "password")))
    email.send_keys(INVALID_EMAIL)
    password.send_keys(INVALID_PASSWORD)

    # 3. Submit the login form
    logger.info("3. Submitting login form with invalid credentials...")
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()

    # 4. Verify error alert
    logger.info("4. Verifying error message alert...")
    error_alert = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".alert-error")))
    assert error_alert.is_displayed(), "Error message alert should be visible"
    assert "Invalid email or password" in error_alert.text, "Error message text is incorrect"
    logger.info(f"   -> Verification passed: Error displayed ('{error_alert.text}').")
    logger.info("--- PASSED: test_invalid_login ---\n")
    sleep(1)
