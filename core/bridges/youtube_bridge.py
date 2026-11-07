"""
core/bridges/youtube_bridge.py
YouTube Video Metadata & Transcript Connector.
Extracts video title, channel, description, and spoken transcript/captions
for any YouTube URL or video ID without requiring an API key.
"""

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def _extract_video_id(text: str) -> str:
    if not text:
        return ""
    s = text.strip()
    patterns = [
        r"(?:v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"^([A-Za-z0-9_-]{11})$",
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            return m.group(1)
    return ""


def _walk_video_renderers(node, out: list, max_items: int = 8) -> None:
    if len(out) >= max_items:
        return
    if isinstance(node, dict):
        if "videoRenderer" in node and isinstance(node["videoRenderer"], dict):
            vr = node["videoRenderer"]
            vid = vr.get("videoId", "")
            if vid and not any(x.get("video_id") == vid for x in out):
                title = ""
                t_obj = vr.get("title", {})
                if isinstance(t_obj.get("runs"), list) and t_obj["runs"]:
                    title = "".join(r.get("text", "") for r in t_obj["runs"])
                elif t_obj.get("simpleText"):
                    title = t_obj["simpleText"]

                channel = ""
                for ch_key in ("ownerText", "longBylineText", "shortBylineText"):
                    c_obj = vr.get(ch_key, {})
                    if isinstance(c_obj.get("runs"), list) and c_obj["runs"]:
                        channel = c_obj["runs"][0].get("text", "")
                        if channel:
                            break

                duration = (
                    vr.get("lengthText", {}).get("simpleText")
                    or "Live / Short"
                )
                views = (
                    vr.get("shortViewCountText", {}).get("simpleText")
                    or vr.get("viewCountText", {}).get("simpleText")
                    or ""
                )
                out.append({
                    "video_id": vid,
                    "title": title or vid,
                    "channel": channel or "Unknown Channel",
                    "duration": duration,
                    "views": views,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                })
            return
        for v in node.values():
            _walk_video_renderers(v, out, max_items)
    elif isinstance(node, list):
        for item in node:
            _walk_video_renderers(item, out, max_items)


def search_videos(args: dict = None) -> str:
    """Search YouTube for videos/music and return real watch URLs, titles, channels, and durations."""
    if args is None:
        args = {}
    query = str(args.get("query") or args.get("q") or args.get("url") or args.get("video") or "").strip()
    if not query:
        return "YouTube Search Error: Provide a 'query' to search on YouTube (e.g. 'Hoshimachi Suisei Stellar Stellar')."

    try:
        limit = max(1, min(int(args.get("limit") or args.get("count") or 5), 10))
    except Exception:
        limit = 5

    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.youtube.com/results?search_query={encoded}"
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
            page_html = resp.read(1_200_000).decode("utf-8", errors="replace")

        results: list[dict] = []
        m = re.search(r"ytInitialData\s*=\s*(\{.*?\});\s*</script>", page_html, re.DOTALL)
        if not m:
            m = re.search(r"ytInitialData\s*=\s*(\{.*?\});", page_html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                _walk_video_renderers(data, results, max_items=limit)
            except Exception:
                pass

        # Regex fallback if JSON structure changed
        if not results:
            for rm in re.finditer(
                r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})".*?"title":\{"runs":\[\{"text":"((?:\\.|[^"\\])*)"',
                page_html,
            ):
                vid = rm.group(1)
                if any(r["video_id"] == vid for r in results):
                    continue
                raw_title = rm.group(2).encode("utf-8").decode("unicode_escape", errors="replace")
                results.append({
                    "video_id": vid,
                    "title": raw_title,
                    "channel": "YouTube",
                    "duration": "",
                    "views": "",
                    "url": f"https://www.youtube.com/watch?v={vid}",
                })
                if len(results) >= limit:
                    break

        if not results:
            return f"No YouTube videos found for query: '{query}'."

        lines = [
            f"YouTube Search Results for '{query}':",
            "(Include the exact https://www.youtube.com/watch?v=... URL in your response to embed the interactive video card & player right in the chat!)",
            "",
        ]
        for idx, item in enumerate(results, 1):
            meta_parts = [item["channel"]]
            if item.get("duration"):
                meta_parts.append(item["duration"])
            if item.get("views"):
                meta_parts.append(item["views"])
            lines.append(
                f"{idx}. {item['title']}\n"
                f"   Channel / Info: {' · '.join(meta_parts)}\n"
                f"   URL: {item['url']}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"YouTube Search Error ('{query}'): {e}"


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
        if raw:
            return search_videos({"query": raw, "limit": args.get("limit", 5)})
        return "YouTube Connector Error: Provide a YouTube URL (e.g. https://youtu.be/...) or a search 'query'."

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
