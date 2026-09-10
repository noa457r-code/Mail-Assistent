"""Gmail API access: fetch new emails and apply classification labels.

Read/label operations only. Sending, forwarding, or deleting mail is
intentionally not implemented here — those actions require explicit human
approval per the assistant's security rules.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

CREDENTIALS_PATH = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json"))
TOKEN_PATH = Path(os.environ.get("GMAIL_TOKEN_PATH", "token.json"))

PROCESSED_LABEL = "MailAssistent/Verarbeitet"
LABEL_PREFIX = "MailAssistent"


def get_service():
    """Authenticate via OAuth (cached token, browser consent on first run)."""
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Gmail OAuth credentials not found at {CREDENTIALS_PATH}. "
                    "Download 'credentials.json' from Google Cloud Console "
                    "(OAuth client, Desktop app type) and set GMAIL_CREDENTIALS_PATH."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def list_new_messages(service, max_results: int = 20) -> list[dict]:
    """Return unprocessed inbox messages (not yet labeled by this assistant)."""
    query = f'in:inbox -label:"{PROCESSED_LABEL}"'
    resp = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=max_results)
        .execute()
    )
    return resp.get("messages", [])


def get_message(service, message_id: str) -> dict:
    return (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )


def _get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_plain_text(payload: dict) -> str:
    """Walk the MIME tree and return the first text/plain part found."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    for part in payload.get("parts", []) or []:
        text = _extract_plain_text(part)
        if text:
            return text

    if payload.get("mimeType") == "text/html":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    return ""


def extract_email_fields(message: dict) -> dict:
    headers = message.get("payload", {}).get("headers", [])
    body = _extract_plain_text(message.get("payload", {}))
    return {
        "id": message.get("id"),
        "thread_id": message.get("threadId"),
        "from": _get_header(headers, "From"),
        "to": _get_header(headers, "To"),
        "subject": _get_header(headers, "Subject"),
        "date": _get_header(headers, "Date"),
        "body": body,
        "snippet": message.get("snippet", ""),
    }


def format_email_for_analysis(fields: dict) -> str:
    return (
        f"Von: {fields['from']}\n"
        f"An: {fields['to']}\n"
        f"Betreff: {fields['subject']}\n"
        f"Datum: {fields['date']}\n\n"
        f"{fields['body'] or fields['snippet']}"
    )


_label_cache: dict[str, str] = {}


def get_or_create_label(service, label_name: str) -> str:
    """Return the Gmail label ID for label_name, creating it if needed."""
    if label_name in _label_cache:
        return _label_cache[label_name]

    resp = service.users().labels().list(userId="me").execute()
    for label in resp.get("labels", []):
        if label["name"] == label_name:
            _label_cache[label_name] = label["id"]
            return label["id"]

    created = (
        service.users()
        .labels()
        .create(
            userId="me",
            body={
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        .execute()
    )
    _label_cache[label_name] = created["id"]
    return created["id"]


def apply_labels(service, message_id: str, label_names: list[str]) -> None:
    label_ids = [get_or_create_label(service, name) for name in label_names]
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"addLabelIds": label_ids},
    ).execute()


def labels_for_analysis(analysis: dict) -> list[str]:
    """Map a parsed analysis dict to the set of Gmail labels to apply."""
    labels = [PROCESSED_LABEL]

    if analysis.get("kategorie"):
        labels.append(f"{LABEL_PREFIX}/Kategorie-{analysis['kategorie']}")
    if analysis.get("prioritaet"):
        labels.append(f"{LABEL_PREFIX}/Prioritaet-{analysis['prioritaet']}")
    if analysis.get("is_security_risk"):
        labels.append(f"{LABEL_PREFIX}/Sicherheitsrisiko")
    if analysis.get("is_phishing"):
        labels.append(f"{LABEL_PREFIX}/Phishing-Verdacht")
    if analysis.get("needs_approval"):
        labels.append(f"{LABEL_PREFIX}/Freigabe-erforderlich")

    return labels
