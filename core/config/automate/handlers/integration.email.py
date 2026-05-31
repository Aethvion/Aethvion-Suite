def _h_integration_email(node, inputs, ctx):
    import smtplib
    from email.mime.text import MIMEText
    p = node.get("properties", {})
    to = _to_str(inputs.get("to") or p.get("to", "")).strip()
    subject = _to_str(inputs.get("subject") or p.get("subject", "Workflow Notification"))
    body = _to_str(inputs.get("in", ""))
    smtp_host = str(p.get("smtp_host", "")).strip()
    smtp_port = int(p.get("smtp_port", 587) or 587)
    smtp_user = str(p.get("smtp_user", "")).strip()
    smtp_pass = str(p.get("smtp_pass", "")).strip()
    if not all([to, smtp_host, smtp_user]): return {"out": body, "error": "Email not configured"}
    try:
        msg = MIMEText(body, "html" if str(p.get("format","plain"))=="html" else "plain")
        msg["Subject"] = subject; msg["From"] = smtp_user; msg["To"] = to
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(); server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to], msg.as_string())
        return {"out": body, "error": ""}
    except Exception as exc:
        return {"out": body, "error": str(exc)}
