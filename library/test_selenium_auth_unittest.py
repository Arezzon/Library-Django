from time import sleep
import unittest
from functools import wraps
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By

class TestLoginLogoutSelenium(unittest.TestCase):
    BASE_URL = "http://127.0.0.1:8000"

    VALID_EMAIL = "reader@library.com"
    VALID_PASSWORD = "reader123password"

    INVALID_EMAIL = "wrong_user@library.com"
    INVALID_PASSWORD = "wrongpassword123"

    def setUp(self):
        """
        Launch before test - open browser
        """
        # 1. Open browser
        self.driver = webdriver.Chrome()
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
        password = self.wait.until(EC.presence_of_element_located((By.NAME, "password")))

        email.send_keys(self.VALID_EMAIL)
        password.send_keys(self.VALID_PASSWORD)

        # 4. Click Sign in
        self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()

        # 5. Verify that the user is successfully logged in to the website.
        logout_btn = self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Log Out")))

        self.assertTrue(logout_btn.is_displayed())
        self.assertIn(self.VALID_EMAIL, driver.page_source)
        
        sleep(1)

        # 6. Click on the "Logout" button in the top right corner of the page.
        logout_btn.click()

        # 7. Verify that the user has successfully logged out of the account.
        login_btn = self.wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Log In")))
        self.assertTrue(login_btn.is_displayed())


    # 8. Enter invalid login credentials:
    def test_invalid_login(self):
        driver = self.driver

        self.wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Log In"))).click()

        # 9. Enter invalid data
        email = self.wait.until(EC.presence_of_element_located((By.NAME, "email")))
        password = self.wait.until(EC.presence_of_element_located((By.NAME, "password")))

        email.send_keys(self.INVALID_EMAIL)
        password.send_keys(self.INVALID_PASSWORD)

        self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))).click()

        # 10. Verify that the user is not able to log in to the website and receives an appropriate error message.
        error_alert = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".alert-error")))

        self.assertTrue(error_alert.is_displayed())
        self.assertIn("Invalid email or password", error_alert.text)
        sleep(1)

if __name__ == "__main__":
    unittest.main()


