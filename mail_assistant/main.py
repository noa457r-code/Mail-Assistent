"""Entry point: fetch new Gmail messages, analyze each with Claude, label + log results.

Intended to run on a schedule (cron / systemd timer) — see README.md.
Never sends, forwards, or deletes mail; that always stays a human action.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from . import gmail_client
from .claude_client import analyze_email
from .parser import parse_analysis

LOG_PATH = Path(os.environ.get("MAIL_ASSISTANT_LOG", "logs/analysis_log.jsonl"))
MAX_EMAILS_PER_RUN = int(os.environ.get("MAX_EMAILS_PER_RUN", "20"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("mail_assistant")


def append_log(entry: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def process_message(service, message_meta: dict) -> None:
    message_id = message_meta["id"]
    message = gmail_client.get_message(service, message_id)
    fields = gmail_client.extract_email_fields(message)
    email_text = gmail_client.format_email_for_analysis(fields)

    logger.info("Analysiere Mail %s (Betreff: %r)", message_id, fields["subject"])
    raw_analysis = analyze_email(email_text)
    analysis = parse_analysis(raw_analysis)

    labels = gmail_client.labels_for_analysis(analysis)
    gmail_client.apply_labels(service, message_id, labels)

    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_id": message_id,
        "thread_id": fields["thread_id"],
        "from": fields["from"],
        "subject": fields["subject"],
        "date": fields["date"],
        "labels_applied": labels,
        "analysis": analysis,
    }
    append_log(log_entry)

    if analysis["is_security_risk"] or analysis["is_phishing"]:
        logger.warning(
            "SICHERHEITSHINWEIS: Mail %s (Betreff: %r) als Risiko markiert. "
            "Menschliche Prüfung erforderlich.",
            message_id,
            fields["subject"],
        )


def run() -> None:
    service = gmail_client.get_service()
    messages = gmail_client.list_new_messages(service, max_results=MAX_EMAILS_PER_RUN)

    if not messages:
        logger.info("Keine neuen E-Mails zu verarbeiten.")
        return

    logger.info("%d neue E-Mail(s) gefunden.", len(messages))
    for meta in messages:
        try:
            process_message(service, meta)
        except Exception:
            logger.exception("Fehler bei der Verarbeitung von Mail %s", meta.get("id"))


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logger.exception("Mail-Assistent-Lauf fehlgeschlagen")
        sys.exit(1)
