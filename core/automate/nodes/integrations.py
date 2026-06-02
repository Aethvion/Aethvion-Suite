"""
core/automate/nodes/integrations.py
Handler functions for companion.ask, integration.discord,
integration.slack, and integration.email node types.
"""
from __future__ import annotations

import json
import smtplib
import ssl
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from ._utils import _to_str
from .ai import _simple_ai_call


# Companion

def companion_ask(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p            = node.get("properties", {})
    companion_id = str(p.get("companion_id", "")).strip()
    model_id     = _to_str(inputs.get("model") or p.get("model", "")).strip()
    prompt       = _to_str(inputs.get("in", ""))
    system_ovr   = _to_str(inputs.get("system", "") or p.get("system_prompt", "")).strip()
    temperature  = float(p.get("temperature", 0.7))

    if not companion_id:
        return {"out": "", "error": "companion.ask: No companion selected"}

    # Load companion config to get its system prompt and default model
    try:
        from core.companions.registry import CompanionRegistry  # noqa: PLC0415
        cfg = CompanionRegistry.get_companion(companion_id)
    except Exception as exc:
        return {"out": "", "error": f"companion.ask: Could not load registry — {exc}"}

    if cfg is None:
        return {"out": "", "error": f"companion.ask: Companion '{companion_id}' not found"}

    # Resolve model: port/property override → companion default
    if not model_id:
        model_id = cfg.default_model
    if not model_id:
        return {"out": "", "error": "companion.ask: No model configured for this companion"}

    # Resolve system prompt: explicit override → companion chat_system → empty
    if system_ovr:
        system_prompt = system_ovr
    else:
        raw_prompts = cfg._raw_config.get("prompts", {})
        chat_system = raw_prompts.get("chat_system", "")
        # Strip format placeholders that can't be filled in this context
        try:
            system_prompt = chat_system.format(
                name=cfg.name,
                mood="calm",
                date="",
                time="",
                memory_context="",
                workspace_context="",
                tools_context="",
            )
        except (KeyError, IndexError):
            system_prompt = chat_system

    resp = _simple_ai_call(model_id, system_prompt or None, prompt, temperature=temperature)
    if not resp.success:
        return {"out": "", "error": resp.error or "AI call failed"}
    return {"out": resp.content, "error": ""}


# Discord

def integration_discord(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p           = node.get("properties", {})
    webhook_url = str(inputs.get("webhook") or p.get("webhook_url", "")).strip()
    message     = _to_str(inputs.get("in", ""))
    username    = str(p.get("username", "Aethvion")).strip() or "Aethvion"
    avatar_url  = str(p.get("avatar_url", "")).strip()

    if not webhook_url:
        return {"out": message, "error": "integration.discord: No webhook URL configured"}

    # Build Discord payload — prefer embed if title is set, otherwise plain content
    title = _to_str(inputs.get("title") or p.get("title", "")).strip()

    if title:
        colour = int(p.get("colour", 0x5865F2))
        payload: dict = {
            "username": username,
            "embeds": [{"title": title, "description": message, "color": colour}],
        }
    else:
        payload = {"username": username, "content": message}

    if avatar_url:
        payload["avatar_url"] = avatar_url

    body = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        webhook_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            # Discord returns 204 No Content on success
            status = resp.status
        if status not in (200, 204):
            return {"out": message, "error": f"Discord returned HTTP {status}"}
        return {"out": message, "error": ""}
    except Exception as exc:
        return {"out": message, "error": str(exc)}


# Slack

def integration_slack(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p           = node.get("properties", {})
    webhook_url = str(inputs.get("webhook") or p.get("webhook_url", "")).strip()
    message     = _to_str(inputs.get("in", ""))
    title       = _to_str(inputs.get("title") or p.get("title", "")).strip()
    icon_emoji  = str(p.get("icon_emoji", ":robot_face:")).strip()

    if not webhook_url:
        return {"out": message, "error": "integration.slack: No webhook URL configured"}

    # Build Slack payload
    if title:
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": title}},
            {"type": "section", "text": {"type": "mrkdwn", "text": message}},
        ]
        payload: dict = {"blocks": blocks}
    else:
        payload = {"text": message}

    if icon_emoji:
        payload["icon_emoji"] = icon_emoji

    body = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        webhook_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        # Slack returns "ok" as the body on success
        if raw.strip() != "ok" and "ok" not in raw:
            return {"out": message, "error": f"Slack returned: {raw[:200]}"}
        return {"out": message, "error": ""}
    except Exception as exc:
        return {"out": message, "error": str(exc)}


# Email

def integration_email(node: dict, inputs: dict[str, Any], ctx) -> dict[str, Any]:
    p        = node.get("properties", {})
    body     = _to_str(inputs.get("in", ""))
    to_addr  = _to_str(inputs.get("to")      or p.get("to",      "")).strip()
    subject  = _to_str(inputs.get("subject") or p.get("subject", "Aethvion Notification")).strip()

    smtp_host = str(p.get("smtp_host", "")).strip()
    smtp_port = int(p.get("smtp_port", 587) or 587)
    smtp_user = str(p.get("smtp_user", "")).strip()
    smtp_pass = str(p.get("smtp_pass", "")).strip()
    from_addr = str(p.get("from_addr", smtp_user)).strip() or smtp_user
    fmt       = str(p.get("format", "plain"))  # "plain" or "html"

    if not smtp_host:
        return {"out": body, "error": "integration.email: No SMTP host configured"}
    if not to_addr:
        return {"out": body, "error": "integration.email: No recipient (To) configured"}

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    mime_type      = "html" if fmt == "html" else "plain"
    msg.attach(MIMEText(body, mime_type, "utf-8"))

    try:
        if smtp_port == 465:
            # SSL from the start
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context, timeout=20) as server:
                if smtp_user:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr, [to_addr], msg.as_string())
        else:
            # Plain then STARTTLS (port 587 / 25 / etc.)
            with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                if smtp_user:
                    server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr, [to_addr], msg.as_string())
        return {"out": body, "error": ""}
    except Exception as exc:
        return {"out": body, "error": str(exc)}
