"""Send alerts via AgentMail (email) and ntfy.sh (push)."""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass


@dataclass
class NotifyResult:
    email_sent: bool
    email_error: str | None
    push_sent: bool
    push_error: str | None


def _post(url: str, headers: dict, body: bytes, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url=url, method="POST", headers=headers, data=body)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def send_email_agentmail(
    api_key: str, inbox_id: str, recipients: list[str], subject: str, text: str,
) -> tuple[bool, str | None]:
    if not (api_key and inbox_id and recipients):
        return False, "missing AgentMail config or recipients"
    url = f"https://api.agentmail.to/v0/inboxes/{inbox_id}/messages/send"
    body = json.dumps({"to": recipients, "subject": subject, "text": text}).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        _post(url, headers, body)
        return True, None
    except Exception as e:
        return False, str(e)


def send_push_ntfy(
    topic: str, title: str, text: str, priority: int = 4,
) -> tuple[bool, str | None]:
    if not topic:
        return False, "missing NTFY_TOPIC"
    # Use the JSON publish API (UTF-8 native; HTTP headers can't carry emoji
    # because urllib forces latin-1 on Request headers).
    body = json.dumps({
        "topic": topic,
        "title": title,
        "message": text,
        "priority": priority,
        "tags": ["ocean", "surfer"],
    }).encode("utf-8")
    try:
        _post("https://ntfy.sh/", {"Content-Type": "application/json"}, body)
        return True, None
    except Exception as e:
        return False, str(e)


def notify_all(subject: str, body: str, push_title: str | None = None) -> NotifyResult:
    api_key = os.environ.get("AGENTMAIL_API_KEY", "")
    inbox_id = os.environ.get("AGENTMAIL_INBOX_ID", "")
    recip_raw = os.environ.get("ALERT_TO", "")
    recipients = [r.strip() for r in recip_raw.split(",") if r.strip()]
    topic = os.environ.get("NTFY_TOPIC", "")

    dry = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    if dry:
        print(f"[dry-run] subject={subject!r}")
        print(f"[dry-run] body={body!r}")
        return NotifyResult(False, "dry-run", False, "dry-run")

    email_ok, email_err = send_email_agentmail(api_key, inbox_id, recipients, subject, body)
    push_ok, push_err = send_push_ntfy(topic, push_title or subject, body)
    return NotifyResult(email_ok, email_err, push_ok, push_err)
