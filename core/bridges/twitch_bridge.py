"""
core/bridges/twitch_bridge.py
Twitch Live Streams Connector.

Check whether a streamer is live, search live channels, browse top streams
(optionally per game/category), and list recent VODs. Results include
https://www.twitch.tv/<channel> URLs which the chat UI renders as interactive
Twitch cards with an inline embedded player.

Uses the official Twitch Helix API when a Client ID + Client Secret are
configured in Library > Connectors (app access token via client credentials).
Without credentials, a limited live-status lookup via the public decapi.me
service is used for single channels.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

_HELIX = "https://api.twitch.tv/helix"
_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_UA = "AethvionSuite-TwitchConnector/1.0"

# Cached app access token: {"client_id": str, "token": str, "expires_at": float}
_token_cache: dict = {}


# Helpers

def _settings(args: dict) -> dict:
    s = args.get("settings") or {}
    return s if isinstance(s, dict) else {}


def _credentials(args: dict) -> tuple[str, str]:
    s = _settings(args)
    return (str(s.get("client_id") or "").strip(), str(s.get("client_secret") or "").strip())


def _clean_login(raw: str) -> str:
    """Normalise a channel name or twitch.tv URL to a login name."""
    raw = (raw or "").strip()
    m = re.search(r"twitch\.tv/([A-Za-z0-9_]{2,25})", raw, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    raw = raw.lstrip("@").strip()
    m = re.match(r"^([A-Za-z0-9_]{2,25})$", raw)
    return m.group(1).lower() if m else ""


def _get_app_token(client_id: str, client_secret: str) -> str:
    now = time.time()
    if (
        _token_cache.get("client_id") == client_id
        and _token_cache.get("token")
        and _token_cache.get("expires_at", 0) > now + 60
    ):
        return _token_cache["token"]

    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }).encode("utf-8")
    req = urllib.request.Request(_TOKEN_URL, data=body, method="POST", headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    token = data.get("access_token", "")
    if not token:
        raise RuntimeError("Twitch did not return an access token — check your Client ID / Client Secret.")
    _token_cache.update({
        "client_id": client_id,
        "token": token,
        "expires_at": now + int(data.get("expires_in", 3600)),
    })
    return token


def _helix(path: str, params: list[tuple[str, str]], client_id: str, client_secret: str) -> dict:
    token = _get_app_token(client_id, client_secret)
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{_HELIX}/{path}?{qs}",
        headers={"Client-Id": client_id, "Authorization": f"Bearer {token}", "User-Agent": _UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            _token_cache.clear()
        raise RuntimeError(f"Twitch API error {e.code}: {e.read()[:300].decode('utf-8', 'replace')}")


def _uptime(started_at: str) -> str:
    try:
        import datetime
        start = datetime.datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        delta = int((datetime.datetime.now(datetime.timezone.utc) - start).total_seconds())
        return f"{delta // 3600}h {(delta % 3600) // 60}m"
    except Exception:
        return ""


def _limit(args: dict, default: int = 5) -> int:
    try:
        return max(1, min(int(args.get("limit") or args.get("count") or default), 20))
    except Exception:
        return default


_EMBED_HINT = (
    "(Include the exact https://www.twitch.tv/<channel> URL in your reply to show an interactive "
    "Twitch card with an embedded live player right in the chat!)"
)

_NO_CREDS = (
    "Twitch Connector: This command needs Twitch API credentials. Ask the user to add a free "
    "Client ID and Client Secret (from https://dev.twitch.tv/console/apps) under "
    "Library > Connectors > Twitch Live Streams > Settings."
)


def _fmt_stream(idx: int, s: dict) -> str:
    login = s.get("user_login") or s.get("broadcaster_login") or ""
    name = s.get("user_name") or s.get("display_name") or login
    parts = []
    if s.get("game_name"):
        parts.append(s["game_name"])
    if s.get("viewer_count") is not None:
        parts.append(f"{int(s['viewer_count']):,} viewers")
    if s.get("started_at"):
        up = _uptime(s["started_at"])
        if up:
            parts.append(f"live for {up}")
    if s.get("language"):
        parts.append(s["language"])
    return (
        f"{idx}. {name} — {s.get('title', '').strip() or '(no title)'}\n"
        f"   Info: {' · '.join(parts) if parts else 'Live'}\n"
        f"   URL: https://www.twitch.tv/{login}"
    )


# No-credential fallback (single channel)

def _decapi(endpoint: str, login: str) -> str:
    req = urllib.request.Request(
        f"https://decapi.me/twitch/{endpoint}/{urllib.parse.quote(login)}",
        headers={"User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return resp.read(2000).decode("utf-8", errors="replace").strip()


def _channel_fallback(login: str) -> str:
    try:
        uptime = _decapi("uptime", login)
    except Exception as e:
        return (
            f"Twitch Connector Error: Could not look up '{login}' without API credentials ({e}).\n"
            f"Channel URL: https://www.twitch.tv/{login}\n{_NO_CREDS}"
        )
    low = uptime.lower()
    if "not found" in low or "no user" in low:
        return f"Twitch: No channel named '{login}' was found."
    lines = [f"Twitch Channel: {login}", f"URL: https://www.twitch.tv/{login}"]
    if "offline" in low:
        lines.insert(1, "Status: OFFLINE")
    else:
        lines.insert(1, f"Status: LIVE (uptime {uptime})")
        for label, ep in (("Title", "title"), ("Category", "game"), ("Viewers", "viewercount")):
            try:
                val = _decapi(ep, login)
                if val:
                    lines.append(f"{label}: {val}")
            except Exception:
                pass
    lines.append("")
    lines.append(_EMBED_HINT)
    return "\n".join(lines)


# Commands

def get_channel(args: dict = None) -> str:
    """Check if a Twitch streamer is live: title, category, viewers, uptime, plus recent VODs when offline."""
    args = args or {}
    s = _settings(args)
    login = _clean_login(str(args.get("channel") or args.get("query") or args.get("url") or s.get("default_channel") or ""))
    if not login:
        return "Twitch Connector Error: Provide a 'channel' name (e.g. 'shroud') or a twitch.tv URL."

    client_id, client_secret = _credentials(args)
    if not (client_id and client_secret):
        return _channel_fallback(login)

    try:
        users = _helix("users", [("login", login)], client_id, client_secret).get("data", [])
        if not users:
            return f"Twitch: No channel named '{login}' was found."
        user = users[0]
        lines = [
            f"Twitch Channel: {user.get('display_name') or login}",
            f"URL: https://www.twitch.tv/{login}",
        ]
        if user.get("description"):
            lines.append(f"About: {user['description'][:300]}")

        streams = _helix("streams", [("user_login", login)], client_id, client_secret).get("data", [])
        if streams:
            st = streams[0]
            lines.insert(1, "Status: LIVE")
            lines.append(f"Title: {st.get('title', '').strip()}")
            if st.get("game_name"):
                lines.append(f"Category: {st['game_name']}")
            lines.append(f"Viewers: {int(st.get('viewer_count', 0)):,}")
            up = _uptime(st.get("started_at", ""))
            if up:
                lines.append(f"Live for: {up}")
        else:
            lines.insert(1, "Status: OFFLINE")
            vods = _helix(
                "videos", [("user_id", user["id"]), ("first", "3"), ("type", "archive")], client_id, client_secret
            ).get("data", [])
            if vods:
                lines.append("")
                lines.append("Recent broadcasts (VODs):")
                for i, v in enumerate(vods, 1):
                    lines.append(f"{i}. {v.get('title', '').strip()} ({v.get('duration', '')}) — {v.get('url', '')}")

        lines.append("")
        lines.append(_EMBED_HINT)
        return "\n".join(lines)
    except Exception as e:
        return f"Twitch Connector Error ({login}): {e}"


def search_streams(args: dict = None) -> str:
    """Search Twitch channels (live by default) by name, topic, or game."""
    args = args or {}
    query = str(args.get("query") or args.get("q") or args.get("channel") or "").strip()
    if not query:
        return "Twitch Connector Error: Provide a 'query' to search (e.g. 'vtuber karaoke' or 'Elden Ring')."
    client_id, client_secret = _credentials(args)
    if not (client_id and client_secret):
        login = _clean_login(query)
        if login:
            return _channel_fallback(login)
        return _NO_CREDS

    live_only = str(args.get("live_only", "true")).lower() not in ("false", "0", "no")
    try:
        data = _helix(
            "search/channels",
            [("query", query), ("first", str(_limit(args))), ("live_only", "true" if live_only else "false")],
            client_id, client_secret,
        ).get("data", [])
        if not data:
            return f"No {'live ' if live_only else ''}Twitch channels found for '{query}'."
        lines = [f"Twitch {'Live ' if live_only else ''}Channel Search for '{query}':", _EMBED_HINT, ""]
        for i, ch in enumerate(data, 1):
            login = ch.get("broadcaster_login", "")
            status = "LIVE" if ch.get("is_live") else "offline"
            meta = [status]
            if ch.get("game_name"):
                meta.append(ch["game_name"])
            if ch.get("is_live") and ch.get("started_at"):
                up = _uptime(ch["started_at"])
                if up:
                    meta.append(f"live for {up}")
            lines.append(
                f"{i}. {ch.get('display_name') or login} — {ch.get('title', '').strip() or '(no title)'}\n"
                f"   Info: {' · '.join(meta)}\n"
                f"   URL: https://www.twitch.tv/{login}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Twitch Connector Error (search '{query}'): {e}"


def get_top_streams(args: dict = None) -> str:
    """List the most-watched live streams right now, optionally filtered by game/category and language."""
    args = args or {}
    client_id, client_secret = _credentials(args)
    if not (client_id and client_secret):
        return _NO_CREDS

    game = str(args.get("game") or args.get("category") or args.get("query") or "").strip()
    language = str(args.get("language") or "").strip().lower()
    params: list[tuple[str, str]] = [("first", str(_limit(args)))]
    try:
        game_label = ""
        if game:
            games = _helix("games", [("name", game)], client_id, client_secret).get("data", [])
            if not games:
                # Fuzzy fallback via category search
                games = _helix("search/categories", [("query", game), ("first", "1")], client_id, client_secret).get("data", [])
            if not games:
                return f"Twitch: No game/category found matching '{game}'."
            params.append(("game_id", games[0]["id"]))
            game_label = games[0].get("name", game)
        if language:
            params.append(("language", language))

        streams = _helix("streams", params, client_id, client_secret).get("data", [])
        if not streams:
            return f"No live Twitch streams found{(' for ' + game_label) if game_label else ''}."
        header = f"Top Live Twitch Streams{(' — ' + game_label) if game_label else ''}:"
        lines = [header, _EMBED_HINT, ""]
        for i, st in enumerate(streams, 1):
            lines.append(_fmt_stream(i, st))
        return "\n".join(lines)
    except Exception as e:
        return f"Twitch Connector Error (top streams): {e}"
