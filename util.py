"""Helper/utility functions"""
import json
import os
import re

from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import TokenExpiredError

class OCMClient:
    """
    Read-only OCM API client. Loads credentials from file specified by environmental
    variable OCM_CONFIG
    """

    def __init__(self):
        with open(os.getenv("OCM_CONFIG"), encoding="utf-8") as ocm_config_file:
            ocm_config = json.load(ocm_config_file)
        # Build initial (expired) token
        self._token = {
            "access_token": ocm_config["access_token"],
            "refresh_token": ocm_config["refresh_token"],
            "token_type": "Bearer",
            "expires_at": 10,
        }
        self._client_id = ocm_config["client_id"]
        self._refresh_url = ocm_config["token_url"]
        self._base_url = ocm_config["url"]

        # Build initial client
        self._session = OAuth2Session(
            client_id=self._client_id,
            token=self._token,
        )

    def _refresh_token(self):
        """Requests a new Bearer token and updates self._token"""
        self._token = self._session.refresh_token(
            token_url=self._refresh_url, client_id=self._client_id
        )
        self._session = OAuth2Session(client_id=self._client_id, token=self._token)

    def get(self, path, **kwargs):
        """Wrapper around requests module's get()"""
        try:
            return self._session.get(self._base_url + path, **kwargs)
        except TokenExpiredError:
            # Refresh token and try again
            self._refresh_token()
            return self._session.get(self._base_url + path, **kwargs)


def csv_bool_to_bool(csv_bool_str):
    """Converts an Excel/CSV-style Boolean string (TRUE/FALSE) into a Python bool"""
    if csv_bool_str.strip().lower() == "true":
        return True
    if csv_bool_str.strip().lower() == "false":
        return False
    return None


def is_nully_str(s):
    """
    Returns True if s is None, an empty or whitespace-filled string, or some variation of "NULL"
    """
    if s is None:
        return True
    s_strip = s.lower().strip()
    return s_strip in ["", "null"]


def is_valid_url(url):
    """Returns true if input is a valid HTTP(S) URL"""
    regex = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return bool(url is not None and regex.search(url))
