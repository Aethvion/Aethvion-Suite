import os
import json
import logging
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from pathlib import Path
from core.utils.paths import APP_NEXUS

# Setup logging
logger = logging.getLogger(__name__)

# Constants for auth
TOKEN_CACHE_DIR = APP_NEXUS / "spotify"
TOKEN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = TOKEN_CACHE_DIR / ".cache"

def _get_auth_manager(settings: dict):
    """Internal helper to get the Spotify auth manager."""
    return SpotifyOAuth(
        client_id=settings.get("client_id"),
        client_secret=settings.get("client_secret"),
        redirect_uri=settings.get("redirect_uri", "http://localhost:8080/callback"),
        scope="user-read-currently-playing user-modify-playback-state user-read-playback-state",
        cache_path=str(CACHE_PATH)
    )

def get_auth_url(settings: dict) -> str:
    """Returns the authorization URL for the user to visit."""
    auth_manager = _get_auth_manager(settings)
    return auth_manager.get_authorize_url()

def handle_callback(settings: dict, code: str) -> bool:
    """Exchanges the auth code for a token."""
    auth_manager = _get_auth_manager(settings)
    token_info = auth_manager.get_access_token(code)
    return token_info is not None

def _get_spotify_client(settings: dict):
    """Returns an authorized spotipy client or raises an error."""
    auth_manager = _get_auth_manager(settings)
    if not auth_manager.validate_token(auth_manager.cache_handler.get_cached_token()):
        raise Exception("Spotify session expired or not authorized. Please reconnect in settings.")
    return spotipy.Spotify(auth_manager=auth_manager)

# --- Standardized Commands ---

def get_current(args: dict) -> str:
    """Get info about the currently playing track."""
    try:
        sp = _get_spotify_client(args.get("settings", {}))
        track = sp.current_user_playing_track()
        if not track or not track["item"]:
            return "No track is currently playing on Spotify."
        
        item = track["item"]
        name = item["name"]
        artist = item["artists"][0]["name"]
        album = item["album"]["name"]
        return f"Currently playing: '{name}' by {artist} (Album: {album})"
    except Exception as e:
        return f"Spotify Error: {str(e)}"

def play(args: dict) -> str:
    """Start or resume playback."""
    try:
        sp = _get_spotify_client(args.get("settings", {}))
        target = args.get("target")
        
        if target:
            # Simple search for track
            results = sp.search(q=target, limit=1, type="track")
            if results["tracks"]["items"]:
                track_uri = results["tracks"]["items"][0]["uri"]
                sp.start_playback(uris=[track_uri])
                return f"Started playing '{results['tracks']['items'][0]['name']}' on Spotify."
            return f"Could not find track '{target}' on Spotify."
        
        sp.start_playback()
        return "Resumed playback on Spotify."
    except Exception as e:
        return f"Spotify Error: {str(e)}"

def pause(args: dict) -> str:
    """Pause playback."""
    try:
        sp = _get_spotify_client(args.get("settings", {}))
        sp.pause_playback()
        return "Paused Spotify playback."
    except Exception as e:
        return f"Spotify Error: {str(e)}"

def skip(args: dict) -> str:
    """Skip to the next track."""
    try:
        sp = _get_spotify_client(args.get("settings", {}))
        sp.next_track()
        return "Skipped to next track on Spotify."
    except Exception as e:
        return f"Spotify Error: {str(e)}"
