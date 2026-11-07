import os
import sys
import time
import json
import re
import urllib.parse
import subprocess
from core.utils.paths import APP_BRIDGES
from core.utils import get_logger

logger = get_logger(__name__)

# Constants for OAuth
TOKEN_CACHE_DIR = APP_BRIDGES / "spotify"
TOKEN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = TOKEN_CACHE_DIR / ".cache"

# Win32 Media Constants
WM_APPCOMMAND = 0x0319
APPCOMMAND_MEDIA_NEXTTRACK = 11
APPCOMMAND_MEDIA_PREVIOUSTRACK = 12
APPCOMMAND_MEDIA_STOP = 13
APPCOMMAND_MEDIA_PLAY_PAUSE = 14
APPCOMMAND_MEDIA_PLAY = 46
APPCOMMAND_MEDIA_PAUSE = 47

VK_RETURN = 0x0D
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3


def _resolve_spotify_track_uri(query: str) -> tuple[str, str]:
    """Resolve a plain search query to a specific spotify:track:<id> URI via fast web lookup."""
    try:
        import requests
        res = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": f"site:open.spotify.com/track {query}"},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=3.5
        )
        match = re.search(r"open\.spotify\.com/track/([a-zA-Z0-9]+)", res.text)
        if match:
            track_id = match.group(1)
            return f"spotify:track:{track_id}", track_id
    except Exception as e:
        logger.debug(f"Track URI resolution failed: {e}")
    return f"spotify:search:{urllib.parse.quote(query)}", None


class LocalSpotifyController:
    """Controls Spotify locally on Windows via SMTC, Win32 media messages, and URI protocols."""

    @staticmethod
    def _is_spotify_process_running() -> bool:
        """Check if Spotify.exe process is running."""
        try:
            import psutil
            return any("spotify" in p.info["name"].lower() for p in psutil.process_iter(["name"]))
        except Exception:
            return False

    @staticmethod
    def _find_spotify_hwnd():
        """Locate the top-level Spotify window handle using ctypes."""
        if sys.platform != "win32":
            return None
        import ctypes
        user32 = ctypes.windll.user32
        matches = []

        def enum_windows_proc(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value
                    class_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, class_buf, 256)
                    cls_name = class_buf.value
                    if cls_name == "Chrome_WidgetWin_0" and ("Spotify" in title or " - " in title):
                        matches.append(hwnd)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_windows_proc), 0)
        return matches[0] if matches else None

    @classmethod
    def _send_media_command(cls, app_cmd: int, vk_code: int = None):
        """Send a media command to Spotify or fallback to virtual media keys."""
        if sys.platform != "win32":
            return False
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = cls._find_spotify_hwnd()
        if hwnd:
            lparam = app_cmd << 16
            user32.SendMessageW(hwnd, WM_APPCOMMAND, hwnd, lparam)
            return True
        elif vk_code:
            user32.keybd_event(vk_code, 0, 0, 0)
            time.sleep(0.04)
            user32.keybd_event(vk_code, 0, 2, 0)
            return True
        return False

    @classmethod
    def get_current(cls) -> str:
        """Query currently playing track on Spotify via SMTC and window title scanner."""
        try:
            from core.bridges.media_sentinel import _get_media_info_powershell
            info = _get_media_info_powershell()
            if info:
                src = (info.get("source") or "").lower()
                title = info.get("title", "")
                artist = info.get("artist", "")
                if "spotify" in src or (title and title != "Spotify"):
                    if artist:
                        return f"Currently playing on Spotify (Local): '{title}' by {artist}"
                    return f"Currently playing on Spotify (Local): '{title}'"
        except Exception as e:
            logger.debug(f"Local SMTC scan failed: {e}")

        if cls._is_spotify_process_running():
            return "Spotify is open on your PC, but playback is currently paused."
        return "Spotify is not currently running on your PC. You can ask me to play a song or genre to launch it!"

    @classmethod
    def play(cls, target: str = None) -> str:
        """Resume playback or search & play a song/genre/URI on local Spotify."""
        if target:
            clean_target = target.strip()
            track_id = None
            if clean_target.startswith("spotify:track:"):
                uri = clean_target
                track_id = clean_target.split(":")[-1]
            elif clean_target.startswith("spotify:"):
                uri = clean_target
            else:
                uri, track_id = _resolve_spotify_track_uri(clean_target)

            try:
                os.startfile(uri)
            except Exception:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                subprocess.run(["cmd", "/c", "start", uri], shell=True, creationflags=flags)

            web_url = f"https://open.spotify.com/track/{track_id}" if track_id else ""
            embed_ref = f" {web_url}" if web_url else ""
            return (
                f"Opened '{clean_target}' in Spotify!{embed_ref} "
                f"(In Local Mode, Spotify navigates to the track on your screen. "
                f"For silent background playback switching and queueing without touching the app, connect Spotify Cloud OAuth in Connector Settings)."
            )
        else:
            if not cls._is_spotify_process_running():
                try:
                    os.startfile("spotify:")
                    time.sleep(0.6)
                except Exception:
                    pass
            cls._send_media_command(APPCOMMAND_MEDIA_PLAY_PAUSE, VK_MEDIA_PLAY_PAUSE)
            return "Resumed playback on Spotify (Local)."

    @classmethod
    def pause(cls) -> str:
        """Pause playback on local Spotify."""
        cls._send_media_command(APPCOMMAND_MEDIA_PAUSE, VK_MEDIA_PLAY_PAUSE)
        return "Paused Spotify playback (Local)."

    @classmethod
    def skip(cls) -> str:
        """Skip to next track on local Spotify."""
        cls._send_media_command(APPCOMMAND_MEDIA_NEXTTRACK, VK_MEDIA_NEXT_TRACK)
        return "Skipped to next track on Spotify (Local)."

    @classmethod
    def previous(cls) -> str:
        """Return to previous track on local Spotify."""
        cls._send_media_command(APPCOMMAND_MEDIA_PREVIOUSTRACK, VK_MEDIA_PREV_TRACK)
        return "Returned to previous track on Spotify (Local)."


class CloudSpotifyController:
    """Controls Spotify via official Spotipy OAuth Web API."""

    @staticmethod
    def _get_auth_manager(settings: dict):
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        return SpotifyOAuth(
            client_id=settings.get("client_id"),
            client_secret=settings.get("client_secret"),
            redirect_uri=settings.get("redirect_uri", "http://localhost:8080/callback"),
            scope="user-read-currently-playing user-modify-playback-state user-read-playback-state",
            cache_path=str(CACHE_PATH)
        )

    @classmethod
    def is_authorized(cls, settings: dict) -> bool:
        if not settings.get("client_id") or not settings.get("client_secret"):
            return False
        try:
            am = cls._get_auth_manager(settings)
            tok = am.cache_handler.get_cached_token()
            return bool(tok and am.validate_token(tok))
        except Exception:
            return False

    @classmethod
    def _get_client(cls, settings: dict):
        import spotipy
        am = cls._get_auth_manager(settings)
        if not am.validate_token(am.cache_handler.get_cached_token()):
            raise Exception("Spotify cloud session expired or not authorized. Please reconnect in settings.")
        return spotipy.Spotify(auth_manager=am)

    @classmethod
    def get_current(cls, settings: dict) -> str:
        sp = cls._get_client(settings)
        track = sp.current_user_playing_track()
        if not track or not track.get("item"):
            return "No track is currently playing on Spotify."
        item = track["item"]
        name = item.get("name", "Unknown")
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        album = item.get("album", {}).get("name", "")
        return f"Currently playing on Spotify (Cloud): '{name}' by {artists} (Album: {album})"

    @classmethod
    def play(cls, settings: dict, target: str = None) -> str:
        sp = cls._get_client(settings)
        if target:
            results = sp.search(q=target, limit=1, type="track")
            items = results.get("tracks", {}).get("items", [])
            if items:
                track = items[0]
                track_uri = track["uri"]
                sp.start_playback(uris=[track_uri])
                track_url = track.get("external_urls", {}).get("spotify", "")
                artist_name = track.get("artists", [{}])[0].get("name", "")
                artist_part = f" by {artist_name}" if artist_name else ""
                url_part = f" {track_url}" if track_url else ""
                return f"Started playing '{track['name']}'{artist_part} on Spotify (Cloud):{url_part}"
            return f"Could not find track '{target}' on Spotify Cloud."
        sp.start_playback()
        return "Resumed playback on Spotify (Cloud)."

    @classmethod
    def pause(cls, settings: dict) -> str:
        sp = cls._get_client(settings)
        sp.pause_playback()
        return "Paused Spotify playback (Cloud)."

    @classmethod
    def skip(cls, settings: dict) -> str:
        sp = cls._get_client(settings)
        sp.next_track()
        return "Skipped to next track on Spotify (Cloud)."

    @classmethod
    def previous(cls, settings: dict) -> str:
        sp = cls._get_client(settings)
        sp.previous_track()
        return "Returned to previous track on Spotify (Cloud)."

    @classmethod
    def queue(cls, settings: dict, target: str) -> str:
        sp = cls._get_client(settings)
        if target.startswith("spotify:track:"):
            track_uri = target
            track_name = target
        else:
            results = sp.search(q=target, limit=1, type="track")
            items = results.get("tracks", {}).get("items", [])
            if not items:
                return f"Could not find track '{target}' to add to queue."
            track_uri = items[0]["uri"]
            track_name = f"'{items[0]['name']}' by {items[0]['artists'][0]['name']}"

        sp.add_to_queue(uri=track_uri)
        return f"Added {track_name} to Spotify queue (Cloud)."


def _should_use_cloud(settings: dict) -> bool:
    mode = str(settings.get("mode", "auto")).lower()
    if mode == "local":
        return False
    if mode == "cloud":
        return True
    return CloudSpotifyController.is_authorized(settings)


# OAuth entry points for dashboard connector settings
def get_auth_url(settings: dict) -> str:
    """Returns the authorization URL for the user to visit."""
    auth_manager = CloudSpotifyController._get_auth_manager(settings)
    return auth_manager.get_authorize_url()


def handle_callback(settings: dict, code: str) -> bool:
    """Exchanges the auth code for a token."""
    auth_manager = CloudSpotifyController._get_auth_manager(settings)
    token_info = auth_manager.get_access_token(code)
    return token_info is not None


# Standardized Commands callable by bridge manager and companions

def get_current(args: dict) -> str:
    """Get info about the currently playing track."""
    settings = args.get("settings", {})
    if _should_use_cloud(settings):
        try:
            return CloudSpotifyController.get_current(settings)
        except Exception as e:
            logger.debug(f"Cloud get_current failed, falling back to local: {e}")
    return LocalSpotifyController.get_current()


def play(args: dict) -> str:
    """Start or resume playback (optional 'target' arg)."""
    settings = args.get("settings", {})
    target = args.get("target")
    if _should_use_cloud(settings):
        try:
            return CloudSpotifyController.play(settings, target)
        except Exception as e:
            logger.debug(f"Cloud play failed, falling back to local: {e}")
    return LocalSpotifyController.play(target)


def pause(args: dict) -> str:
    """Pause playback."""
    settings = args.get("settings", {})
    if _should_use_cloud(settings):
        try:
            return CloudSpotifyController.pause(settings)
        except Exception as e:
            logger.debug(f"Cloud pause failed, falling back to local: {e}")
    return LocalSpotifyController.pause()


def skip(args: dict) -> str:
    """Skip to next track."""
    settings = args.get("settings", {})
    if _should_use_cloud(settings):
        try:
            return CloudSpotifyController.skip(settings)
        except Exception as e:
            logger.debug(f"Cloud skip failed, falling back to local: {e}")
    return LocalSpotifyController.skip()


def previous(args: dict) -> str:
    """Return to previous track."""
    settings = args.get("settings", {})
    if _should_use_cloud(settings):
        try:
            return CloudSpotifyController.previous(settings)
        except Exception as e:
            logger.debug(f"Cloud previous failed, falling back to local: {e}")
    return LocalSpotifyController.previous()


def queue(args: dict) -> str:
    """Add a track to the Spotify playback queue."""
    settings = args.get("settings", {})
    target = args.get("target") or args.get("query")
    if not target:
        return "Please specify a song or artist to add to the queue."

    if _should_use_cloud(settings):
        try:
            return CloudSpotifyController.queue(settings, target)
        except Exception as e:
            logger.debug(f"Cloud queue failed: {e}")
            return f"Could not add to cloud queue: {e}. (Ensure Spotify is open and active on a device)."

    return (
        f"Queuing tracks silently in the background while your current music keeps playing requires the Spotify Cloud OAuth connection. "
        f"In Local Mode, I can play '{target}' right now for you instead!"
    )
