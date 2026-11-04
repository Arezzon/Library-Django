import os
import unittest
from time import sleep

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class TestLoginLogoutSelenium(unittest.TestCase):
    BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")

    VALID_EMAIL = "reader@library.com"
    VALID_PASSWORD = "reader123password"

    INVALID_EMAIL = "wrong_user@library.com"
    INVALID_PASSWORD = "wrongpassword123"

    # "Log Out" is a link on older pages and a form button since KAN-96.
    LOG_OUT = (By.XPATH, "//*[self::a or self::button][normalize-space()='Log Out']")

    def setUp(self):
        """
        Launch before test - open browser
        """
        # 1. Open browser
        options = webdriver.ChromeOptions()
        headless = os.environ.get("SELENIUM_HEADLESS") == "1"
        if headless:
            # CI has no display; the window is wide enough for the desktop header.
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1366,900")
        self.driver = webdriver.Chrome(options=options)
        if not headless:
            self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, timeout=10)
        self.driver.get(self.BASE_URL)

    def tearDown(self):
        """
        Launch after test - close browser
        """
        self.driver.quit()

    def test_valid_login_and_logout(self):
        driver = self.driver

        # 2. Click to login
        self.wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Log In"))).click()

        # 3. Enter valid data
        email = self.wait.until(EC.presence_of_element_located((By.NAME, "email")))
        password = self.wait.until(
            EC.presence_of_element_located((By.NAME, "password"))
        )

        email.send_keys(self.VALID_EMAIL)
        password.send_keys(self.VALID_PASSWORD)

        # 4. Click Sign in
        self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        ).click()

        # 5. Verify that the user is successfully logged in to the website.
        logout_btn = self.wait.until(EC.presence_of_element_located(self.LOG_OUT))

        self.assertTrue(logout_btn.is_displayed())
        self.assertIn(self.VALID_EMAIL, driver.page_source)

        sleep(1)

        # 6. Click on the "Logout" button in the top right corner of the page.
        logout_btn.click()

        # 7. Verify that the user has successfully logged out of the account.
        login_btn = self.wait.until(
            EC.presence_of_element_located((By.LINK_TEXT, "Log In"))
        )
        self.assertTrue(login_btn.is_displayed())

    # 8. Enter invalid login credentials:
    def test_invalid_login(self):

        self.wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Log In"))).click()

        # 9. Enter invalid data
        email = self.wait.until(EC.presence_of_element_located((By.NAME, "email")))
        password = self.wait.until(
            EC.presence_of_element_located((By.NAME, "password"))
        )

        email.send_keys(self.INVALID_EMAIL)
        password.send_keys(self.INVALID_PASSWORD)

        self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        ).click()

        # 10. Verify that the user is not able to log in to the website and receives an appropriate error message.
        error_alert = self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".alert-error"))
        )

        self.assertTrue(error_alert.is_displayed())
        self.assertIn("The email or password is not right", error_alert.text)
        sleep(1)


if __name__ == "__main__":
    unittest.main()
