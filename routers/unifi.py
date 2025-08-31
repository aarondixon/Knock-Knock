# routers/unifi.py

import os
import requests
import jwt
from requests.models import Response
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class UnifiConfig:
    """
    Configuration class for the router.
    Should load required environment variables and validate them.
    """
    def __init__(self):
        self.base_url = os.environ.get("UNIFI_BASE_URL") # base URL of Unifi controller
        self.username = os.environ.get("UNIFI_USERNAME")
        self.password = os.environ.get("UNIFI_PASSWORD")
        self.site = os.environ.get("UNIFI_SITE", "default") # Site name (not friendly name); default if not specified
        self.group_id = os.environ.get("UNIFI_GROUP_ID") # ID (not friendly name) of firewall group

    def validate(self):
        """
        Validates that all required configuration values are present.
        Raises ValueError if any are missing.
        """        
        missing = []
        for attr in ["base_url", "username", "password", "group_id"]:
            if getattr(self, attr) is None:
                missing.append(attr)
        if missing:
            raise ValueError(f"Missing required Unifi config: {', '.join(missing)}")

class UnifiClient:
    """
    Router client interface. Implementations should define how to authenticate and manage IPs
    """    
    def __init__(self, config: UnifiConfig):
        self.config = config
        self.session = requests.Session() # persistent session for API requests
        self.csrf_token = None # csrf token extracted from JWT
        self.token_expiry = None # expiry timestamp of JWT token

    def login(self):
        """
        Authenticates with the router API, likely using base_url, username, password.
        Should store any required tokens or session info (auth_token and token_expiry).
        """           
        login_url = f"{self.config.base_url}/api/auth/login"
        payload = {
            "username": self.config.username,
            "password": self.config.password,
            "remember": True
        }


        logger.info("Login URL: %s", login_url)
        try:
            response = self.session.post(login_url, json=payload, verify=False)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error("Failed to login to router")
            return

        # extract JWT token from cookies and decode it
        token_cookie = self.session.cookies.get("TOKEN")
        decoded_jwt = jwt.decode(token_cookie, options={"verify_signature": False})
        self.csrf_token = decoded_jwt.get("csrfToken") # store token for future calls
        self.token_expiry = decoded_jwt.get("exp") # store expiry for session management

        logger.info("CSRF Token: %s", self.csrf_token)
        logger.info("Token expiry: %s", self.token_expiry)
    
    def ensure_authenticated(self):
        """
        Ensures client is authenticated before making API calls.
        Should re-authenticate (call login()) if session is expired or missing.
        """        
        logger.info("Current time: %s", datetime.utcnow().timestamp())
        logger.info("Token expiry: %s", self.token_expiry)
        if not self.token_expiry or datetime.utcnow().timestamp() > self.token_expiry - 30:
            self.login()

    def add_ip(self, ip):
        """
        Adds an IP address to the routers access group, likely using group_id.
        Returns a tuple of (Response, was_added: bool)
        """        
        self.ensure_authenticated()
        headers = {
            "x-csrf-token": self.csrf_token,
            "Content-Type": "application/json"
        }

        #fetch current group data
        url = f"{self.config.base_url}/proxy/network/api/s/{self.config.site}/rest/firewallgroup/{self.config.group_id}"
        try:
            response = self.session.get(url, verify=False)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error("Failed to fetch group data: %s", e)
            return none, False

        group_data = response.json()['data'][0]

        # add IP if not already in the group
        if ip not in group_data['group_members']:
            group_data['group_members'].append(ip)
            payload = {
                "name": group_data["name"],
                "group_type": group_data["group_type"],
                "group_members": group_data["group_members"],
                "site_id": group_data["site_id"],
                "_id": group_data["_id"]
            }
            try:
                logger.info("Adding IP %s to group %s", ip, group_data["name"])
                response = self.session.put(url, json=payload, headers=headers, verify=False)
                response.raise_for_status()
            except requests.RequestException as e:
                logger.error("Failed to apply group membership change: %s", e)
                return none, False
            return response, True
        else:
            # IP already exists; return a mock success response
            response = Response()
            response.status_code = 200
            response._content = b'{"message": "IP already exists in group"}'
            return response, False

    def remove_ip(self, ip):
        """
        Removes an IP address from the routers access group, likely using group_id.
        Returns the Response object from the API call.
        """        
        self.ensure_authenticated()
        headers = {
            "x-csrf-token": self.csrf_token,
            "Content-Type": "application/json"
        }

        # fetch current group data
        url = f"{self.config.base_url}/proxy/network/api/s/{self.config.site}/rest/firewallgroup/{self.config.group_id}"        
        try:
            response = self.session.get(url, verify=False)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error("Failed to fetch group data: %s", e)

        # remove IP from group
        group_data = response.json()['data'][0]
        group_data['group_members'] = [i for i in group_data['group_members'] if i != ip]
        try:
            logger.info("Removing IP %s from group %s", ip, group_data["name"])
            response = self.session.put(url, json=group_data, headers=headers, verify=False)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error("Failed to remove IP from group: %s", e)