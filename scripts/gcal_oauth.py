"""One-off script to generate a Google Calendar refresh token."""
from __future__ import annotations

import json
import os
import pathlib

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _write_temp_credentials(client_id: str, client_secret: str, path: pathlib.Path) -> None:
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": client_id,
                    "project_id": "generated-by-script",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_secret": client_secret,
                    "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("GOOGLE_CLIENT_ID/SECRET must be set in the environment")

    temp_path = pathlib.Path("tmp_client_secret.json")
    _write_temp_credentials(client_id, client_secret, temp_path)

    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(temp_path), SCOPES)
        creds = flow.run_local_server(port=0)
        refresh_token = creds.refresh_token
        if not refresh_token:
            raise RuntimeError("Refresh token not returned. Ensure offline access is granted.")
        print("REFRESH TOKEN:", refresh_token)
    finally:
        if temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    main()
