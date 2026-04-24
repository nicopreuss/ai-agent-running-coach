"""One-time helper: run Whoop OAuth flow and print access + refresh tokens."""

import os
import secrets
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

load_dotenv()

_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
_SCOPES = "read:recovery read:cycles read:sleep offline"


def main() -> None:
    client_id = os.environ["WHOOP_CLIENT_ID"]
    client_secret = os.environ["WHOOP_CLIENT_SECRET"]
    redirect_uri = os.environ["WHOOP_REDIRECT_URI"]

    state = secrets.token_urlsafe(16)
    auth_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _SCOPES,
        "state": state,
    }
    auth_url = f"{_AUTH_URL}?{urllib.parse.urlencode(auth_params)}"

    print("Opening browser for Whoop authorisation...")
    print(f"\nIf the browser doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("After authorising, Whoop will redirect your browser to your redirect URI.")
    print("The URL will contain '?code=...' — copy just the code value and paste it here.")
    auth_code = input("\nPaste the code here: ").strip()

    response = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10,
    )
    response.raise_for_status()
    tokens = response.json()

    print("\nAdd these to your .env:\n")
    print(f"WHOOP_ACCESS_TOKEN={tokens['access_token']}")
    print(f"WHOOP_REFRESH_TOKEN={tokens['refresh_token']}")
    print(f"\n(expires_in: {tokens.get('expires_in')} seconds)")


if __name__ == "__main__":
    main()
