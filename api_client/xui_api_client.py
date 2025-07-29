# api_client/xui_api_client.py

import requests
import urllib3
import json 
import logging 
import time 

from config import MAX_API_RETRIES # این ایمپورت باید از config بیاید

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__) 

class XuiAPIClient: 
    def __init__(self, panel_url, username, password, two_factor=None): 
        self.panel_url = panel_url.rstrip('/') 
        self.username = username
        self.password = password
        self.two_factor = two_factor
        self.session = requests.Session() # استفاده از requests.Session
        # session_token_value دیگر لازم نیست اگر کوکی 3x-ui به درستی مدیریت شود.
        logger.info(f"XuiAPIClient initialized for {self.panel_url}") 

    def _make_request(self, method, endpoint, data=None, retries=0):
        url = f"{self.panel_url}{endpoint}"
        headers = {"Content-Type": "application/json"} 
        # requests.Session() به طور خودکار کوکی‌ها را مدیریت می‌کند.
        # پس از لاگین، کوکی '3x-ui' به طور خودکار در درخواست‌های بعدی ارسال خواهد شد.

        try:
            response = self.session.request(method, url, json=data, headers=headers, verify=False, timeout=15) 
            response.raise_for_status() 

            response_json = response.json()
            if response_json.get('success', False):
                return response_json
            else:
                logger.warning(f"API request to {endpoint} failed: {response_json.get('msg', 'Unknown error')}. Full response: {response_json}")
                if response.status_code in [401, 403]: 
                    logger.warning(f"Authentication error ({response.status_code}) for {endpoint}. Attempting to re-login.")
                    self.session.cookies.clear() # Clear existing cookies
                    if self.login(): # تلاش برای لاگین مجدد
                        logger.info("Re-login successful. Retrying original request.")
                        return self._make_request(method, endpoint, data, retries) 
                    else:
                        logger.error("Re-login failed. Cannot proceed with request.")
                        return None
                return None

        except requests.exceptions.Timeout:
            logger.error(f"API request to {endpoint} timed out.")
            if retries < MAX_API_RETRIES:
                time.sleep(2 ** retries) 
                logger.info(f"Retrying {endpoint} ({retries + 1}/{MAX_API_RETRIES})...")
                return self._make_request(method, endpoint, data, retries + 1)
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"API connection error to {endpoint}: {e}")
            if retries < MAX_API_RETRIES:
                time.sleep(2 ** retries) 
                logger.info(f"Retrying {endpoint} ({retries + 1}/{MAX_API_RETRIES})...")
                return self._make_request(method, endpoint, data, retries + 1)
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"An unexpected API request error occurred for {endpoint}: {e}")
            if hasattr(response, 'text'):
                logger.error(f"Response text: {response.text}")
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response from {endpoint}. Response text: {response.text}")
            return None
    
    def login(self):
        """
        تلاش برای ورود به پنل X-UI/3X-UI.
        بررسی می‌کنیم که آیا کوکی سشن '3x-ui' ذخیره شده است.
        """
        endpoint = "/login"
        data = {
            "username": self.username,
            "password": self.password
        }
        if self.two_factor:
            data["twoFactor"] = self.two_factor
        
        logger.info(f"Attempting to login to X-UI panel at {self.panel_url}...")
        
        try:
            res = self.session.post(f"{self.panel_url}{endpoint}", json=data, verify=False, timeout=10) 
            res.raise_for_status() 

            response_json = res.json()
            
            if res.status_code == 200 and response_json.get("success"):
                # این مهم است: به دنبال کوکی '3x-ui' می‌گردیم
                if '3x-ui' in self.session.cookies: 
                    logger.info("Successfully logged in to X-UI panel. '3x-ui' cookie found.")
                    return True
                else:
                    logger.warning("Login successful (API returned success) but no '3x-ui' cookie found in response.")
                    # در این حالت، اگرچه API موفقیت را اعلام کرده، اما کوکی مورد نیاز برای احراز هویت را دریافت نکردیم.
                    # ممکن است نیاز به بررسی دستی نام کوکی‌های دیگر در headers.
                    return False
            else:
                logger.error(f"Failed to login to X-UI panel: API returned unsuccessful. Message: {response_json.get('msg', 'No message')}. Status Code: {res.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Login request error: {e}")
            return False
        except json.JSONDecodeError:
            logger.error(f"Failed to decode JSON response from login. Response text: {res.text}")
            return False

    def check_login(self):
        """
        بررسی می‌کند که آیا لاگین معتبر است یا خیر.
        اگر کوکی '3x-ui' در session موجود باشد، True برمی‌گرداند.
        """
        if '3x-ui' in self.session.cookies: # <--- اینجا هم به روز شد
            return True 
        else:
            return self.login()

    def list_inbounds(self):
        if not self.check_login(): 
            logger.error("Not logged in to X-UI. Cannot list inbounds.")
            return []
        
        endpoint = "/panel/api/inbounds/list"
        response = self._make_request("GET", endpoint) 
        
        if response and response.get('success'):
            logger.info("Successfully retrieved inbound list.")
            return response.get('obj', [])
        else:
            logger.error(f"Failed to get inbound list. Response: {response}")
            return []

    def get_inbound(self, inbound_id):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot get inbound details.")
            return None
        
        endpoint = f"/panel/api/inbounds/get/{inbound_id}"
        response = self._make_request("GET", endpoint) 
        
        if response and response.get('success'):
            logger.info(f"Successfully retrieved inbound details for ID {inbound_id}.")
            return response.get('obj')
        else:
            logger.error(f"Failed to get inbound details for ID {inbound_id}. Response: {response}")
            return None
            
    def add_inbound(self, data):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot add inbound.")
            return None
        
        endpoint = "/panel/api/inbounds/add"
        response = self._make_request("POST", endpoint, data=data) 
        
        if response and response.get('success'):
            logger.info(f"Inbound added: {response.get('obj')}")
            return response.get("obj")
        else:
            logger.warning(f"Failed to add inbound: {response}")
            return None

    def delete_inbound(self, inbound_id):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot delete inbound.")
            return False
        
        endpoint = f"/panel/api/inbounds/del/{inbound_id}"
        response = self._make_request("POST", endpoint) 
        
        if response and response.get('success'):
            logger.info(f"Inbound {inbound_id} deleted successfully.")
            return True
        else:
            logger.warning(f"Failed to delete inbound {inbound_id}: {response}")
            return False

    def update_inbound(self, inbound_id, data):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot update inbound.")
            return False
        
        endpoint = f"/panel/api/inbounds/update/{inbound_id}"
        response = self._make_request("POST", endpoint, data=data) 
        
        if response and response.get('success'):
            logger.info(f"Inbound {inbound_id} updated successfully.")
            return True
        else:
            logger.warning(f"Failed to update inbound {inbound_id}: {response}")
            return False

    def add_client(self, data):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot add client.")
            return False
        
        endpoint = "/panel/api/inbounds/addClient"
        response = self._make_request("POST", endpoint, data=data) 
        
        if response and response.get('success'):
            logger.info(f"Client added successfully to inbound {data.get('id', 'N/A')}.")
            return True
        else:
            logger.warning(f"Failed to add client to inbound {data.get('id', 'N/A')}: {response}")
            return False

    def delete_client(self, inbound_id, client_id):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot delete client.")
            return False
        
        endpoint = f"/panel/api/inbounds/{inbound_id}/delClient/{client_id}"
        response = self._make_request("POST", endpoint) 
        
        if response and response.get('success'):
            logger.info(f"Client {client_id} deleted from inbound ID {inbound_id}.")
            return True
        else:
            logger.warning(f"Failed to delete client {client_id} from inbound ID {inbound_id}: {response}")
            return False

    def update_client(self, client_id, data):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot update client.")
            return False
        
        endpoint = f"/panel/api/inbounds/updateClient/{client_id}"
        response = self._make_request("POST", endpoint, data=data) 
        
        if response and response.get('success'):
            logger.info(f"Client {client_id} updated successfully.")
            return True
        else:
            logger.warning(f"Failed to update client {client_id}: {response}")
            return False

    def reset_client_traffic(self, id, email):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot reset client traffic.")
            return False
        url = f"{self.panel_url}/panel/api/inbounds/{id}/resetClientTraffic/{email}"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info(f"Client traffic reset for {email} in inbound {id}.")
                return True
            else:
                logger.warning(f"Failed to reset client traffic for {email} in inbound {id}: {response_json.get('msg', res.text)}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error resetting client traffic for {email} from {url}: {e}")
            return False

    def reset_all_traffics(self):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot reset all traffics.")
            return False
        url = f"{self.panel_url}/panel/api/inbounds/resetAllTraffics"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info("All traffics reset successfully.")
                return True
            else:
                logger.warning(f"Failed to reset all traffics: {response_json.get('msg', res.text)}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error resetting all traffics from {url}: {e}")
            return False

    def reset_all_client_traffics(self, id):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot reset all client traffics.")
            return False
        url = f"{self.panel_url}/panel/api/inbounds/resetAllClientTraffics/{id}"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info(f"All client traffics reset for inbound {id}.")
                return True
            else:
                logger.warning(f"Failed to reset all client traffics for inbound {id}: {response_json.get('msg', res.text)}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error resetting all client traffics for {id} from {url}: {e}")
            return False

    def del_depleted_clients(self, id):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot delete depleted clients.")
            return False
        url = f"{self.panel_url}/panel/api/inbounds/delDepletedClients/{id}"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info(f"Depleted clients deleted for inbound {id}.")
                return True
            else:
                logger.warning(f"Failed to delete depleted clients for inbound {id}: {response_json.get('msg', res.text)}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error deleting depleted clients for {id} from {url}: {e}")
            return False

    def client_ips(self, email):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot get client IPs.")
            return None
        url = f"{self.panel_url}/panel/api/inbounds/clientIps/{email}"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info(f"Client IPs retrieved for {email}.")
                return response_json.get("obj")
            else:
                logger.warning(f"Failed to get client IPs for {email}: {response_json.get('msg', res.text)}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting client IPs for {email} from {url}: {e}")
            return None

    def clear_client_ips(self, email):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot clear client IPs.")
            return False
        url = f"{self.panel_url}/panel/api/inbounds/clearClientIps/{email}"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info(f"Client IPs cleared for {email}.")
                return True
            else:
                logger.warning(f"Failed to clear client IPs for {email}: {response_json.get('msg', res.text)}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error clearing client IPs for {email} from {url}: {e}")
            return False

    def get_online_users(self):
        if not self.check_login():
            logger.error("Not logged in to X-UI. Cannot get online users.")
            return None
        url = f"{self.panel_url}/panel/api/inbounds/onlines"
        try:
            res = self.session.post(url, verify=False, timeout=10)
            res.raise_for_status()
            response_json = res.json()
            if response_json.get('success'):
                logger.info("Successfully retrieved online users.")
                return response_json.get("obj")
            else:
                logger.warning(f"Failed to get online users: {response_json.get('msg', res.text)}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting online users from {url}: {e}")
            return None
        
        
        
        
        
        
# api_client/xui_api_client.py
# ... (کل کد کلاس XuiAPIClient و بقیه توابع) ...

if __name__ == "__main__":
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from config import XUI_PANEL_URL, XUI_USERNAME, XUI_PASSWORD

    print("\n--- Testing XuiAPIClient Login ---")
    test_client = XuiAPIClient(
        panel_url=XUI_PANEL_URL,
        username=XUI_USERNAME,
        password=XUI_PASSWORD
    )

    try:
        # ارسال درخواست لاگین به صورت دستی و چاپ جزئیات پاسخ
        login_url = f"{test_client.panel_url}/login"
        login_data = {"username": test_client.username, "password": test_client.password}
        print(f"Attempting POST request to: {login_url}")
        print(f"Payload: {login_data}")

        response = test_client.session.post(login_url, json=login_data, verify=False, timeout=10)
        response.raise_for_status() # برای برانگیختن خطا در صورت کد وضعیت 4xx/5xx

        print("\n--- Raw Response Details ---")
        print(f"Status Code: {response.status_code}")
        print(f"Response URL: {response.url}")
        print(f"Response Headers:")
        for k, v in response.headers.items():
            print(f"  {k}: {v}")
        print(f"Response Cookies:")
        for k, v in response.cookies.items():
            print(f"  {k}: {v}")
        print(f"Response Body (JSON):")
        try:
            response_json = response.json()
            print(json.dumps(response_json, indent=2))
        except json.JSONDecodeError:
            print("  (Not a valid JSON response)")
            print(response.text)

        print("\n--- Login Attempt Result ---")
        if response.status_code == 200 and response_json.get("success"):
            session_cookie_found = 'session' in test_client.session.cookies
            obj_token_found = response_json.get('obj') is not None

            print(f"API success field: {response_json.get('success')}")
            print(f"Is 'session' cookie found in session.cookies? {session_cookie_found}")
            print(f"Is 'obj' token found in response JSON? {obj_token_found}")

            if session_cookie_found or obj_token_found:
                print("Login successful! Session cookie or obj token detected.")
            else:
                print("Login successful (API returned success) but no expected 'session' cookie or 'obj' token found.")
                print("Please inspect the 'Response Headers' and 'Response Body (JSON)' above for the actual session/token key.")
        else:
            print(f"Login failed. API returned unsuccessful. Message: {response_json.get('msg', response.text)}")

    except requests.exceptions.RequestException as e:
        print(f"\n--- Login Request Error ---")
        print(f"An error occurred during login request: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Error Response Status: {e.response.status_code}")
            print(f"Error Response Text: {e.response.text}")
    except Exception as e:
        print(f"\n--- Unexpected Error ---")
        print(f"An unexpected error occurred: {e}")