"""
core/bridges/youtube_bridge.py
YouTube Video Metadata & Transcript Connector.
Extracts video title, channel, description, and spoken transcript/captions
for any YouTube URL or video ID without requiring an API key.
"""

import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET


def _extract_video_id(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"(?:v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"\b([A-Za-z0-9_-]{11})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return ""


def _fetch_transcript_via_pkg(video_id: str) -> str:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        items = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US", "en-GB", "nl", "de", "fr", "es"])
        return " ".join(seg.get("text", "").strip() for seg in items if seg.get("text"))
    except Exception:
        return ""


def _fetch_youtube_page_and_captions(video_id: str) -> tuple[dict, str]:
    url = f"https://www.youtube.com/watch?v={video_id}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        page_html = resp.read(900_000).decode("utf-8", errors="replace")

    meta = {"title": "", "author": "", "description": "", "length_sec": ""}
    m = re.search(r"ytInitialPlayerResponse\s*=\s*(\{.*?\});", page_html, re.DOTALL)
    caption_text = ""

    if m:
        try:
            player_data = json.loads(m.group(1))
            vd = player_data.get("videoDetails", {})
            meta["title"] = vd.get("title", "")
            meta["author"] = vd.get("author", "")
            meta["description"] = (vd.get("shortDescription") or "")[:1200]
            meta["length_sec"] = vd.get("lengthSeconds", "")

            tracks = (
                player_data.get("captions", {})
                .get("playerCaptionsTracklistRenderer", {})
                .get("captionTracks", [])
            )
            if tracks:
                # Prefer English track if available, otherwise first track
                chosen = next((t for t in tracks if str(t.get("languageCode", "")).startswith("en")), tracks[0])
                base_url = chosen.get("baseUrl")
                if base_url:
                    cap_req = urllib.request.Request(base_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(cap_req, timeout=8) as cap_resp:
                        xml_str = cap_resp.read(500_000).decode("utf-8", errors="replace")
                    root = ET.fromstring(xml_str)
                    phrases = []
                    for node in root.findall(".//text"):
                        if node.text:
                            phrases.append(html.unescape(node.text.replace("\n", " ")).strip())
                    caption_text = " ".join(phrases)
        except Exception:
            pass

    if not meta["title"]:
        tm = re.search(r"<title>(.*?)</title>", page_html, re.IGNORECASE)
        if tm:
            meta["title"] = html.unescape(tm.group(1)).replace("- YouTube", "").strip()

    return meta, caption_text


def get_video_context(args: dict = None) -> str:
    """Fetch title, channel, description, and spoken transcript for a YouTube URL or video ID."""
    if args is None:
        args = {}
    raw = str(args.get("url") or args.get("video") or args.get("query") or "").strip()
    vid = _extract_video_id(raw)
    if not vid:
        return "YouTube Connector Error: Provide a valid YouTube URL (e.g. https://youtu.be/...) or 11-character video ID."

    try:
        meta, caption_text = _fetch_youtube_page_and_captions(vid)
        if not caption_text:
            caption_text = _fetch_transcript_via_pkg(vid)

        lines = [
            f"YouTube Video: {meta.get('title') or vid}",
            f"Channel: {meta.get('author') or 'Unknown'}",
            f"URL: https://www.youtube.com/watch?v={vid}",
        ]
        if meta.get("length_sec"):
            sec = int(meta["length_sec"])
            lines.append(f"Duration: {sec // 60}m {sec % 60}s")
        if meta.get("description"):
            lines.extend(["", "Description:", meta["description"]])
        if caption_text:
            max_chars = 12000
            if len(caption_text) > max_chars:
                caption_text = caption_text[:max_chars] + f"\n...[transcript truncated at {max_chars} chars]"
            lines.extend(["", "Video Transcript / Captions:", caption_text])
        else:
            lines.extend(["", "(No closed captions available on this video; metadata and description provided above.)"])
        return "\n".join(lines)
    except Exception as e:
        return f"YouTube Connector Error ({vid}): {e}"
