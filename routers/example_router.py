# routers/example_router.py

import os
import requests
from requests.models import Response

class ExampleRouterConfig:
    """
    Configuration class for the router.
    Should load required environment variables and validate them.
    """
    def __init__(self):
        self.base_url = os.environ.get("EXAMPLE_ROUTER_BASE_URL")
        self.username = os.environ.get("EXAMPLE_ROUTER_USERNAME")
        self.password = os.environ.get("EXAMPLE_ROUTER_PASSWORD")
        self.group_id = os.environ.get("EXAMPLE_ROUTER_GROUP_ID")

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
            raise ValueError(f"Missing required ExampleRouter config: {', '.join(missing)}")

class ExampleRouterClient:
    """
    Router client interface. Implementations should define how to authenticate and manage IPs
    """
    def __init__(self, config: ExampleRouterConfig):
        self.config = config
        self.session = requests.Session()
        self.auth_token = None # or csrf_token, depending on implementation
        self.token_expiry = None # holds expiration of token

    def login(self):
        """
        Authenticates with the router API, likely using base_url, username, password.
        Should store any required tokens or session info (auth_token and token_expiry).
        """      
        raise NotImplmentedError("ensure_authenticated() must be implemented")

    def ensure_authenticated(self):
        """
        Ensures client is authenticated before making API calls.
        Should re-authenticate (call login()) if session is expired or missing.
        """
        raise NotImplmentedError("ensure_authenticated() must be implemented.")

    def add_ip(self, ip):
        """
        Adds an IP address to the routers access group, likely using group_id.
        Returns a tuple of (Response, was_added: bool)
        """
        raise NotImplmentedError("add_ip() must be implemented.")

    def remove_ip(self, ip):
        """
        Removes an IP address from the routers access group, likely using group_id.
        Returns the Response object from the API call.
        """
        raise NotImplmentedError("remove_ip() must be implemented")
