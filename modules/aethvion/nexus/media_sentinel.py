import asyncio
import logging
import subprocess
import json
import re

# Setup logging
logger = logging.getLogger(__name__)

def _get_media_info_powershell() -> dict:
    """
    Tier 2 & 3 Fallback: Uses PowerShell to query SMTC first, 
    then falls back to scanning process window titles (Spotify, Chrome/YouTube).
    """
    script = """
    $OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    try {
        # Tier 2: SMTC via PowerShell
        $asyncOp = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]::RequestAsync()
        $timeout = 25
        while ($asyncOp.Status -eq 'Started' -and $timeout -gt 0) { Start-Sleep -Milliseconds 100; $timeout-- }
        
        if ($asyncOp.Status -eq 'Completed') {
            $mgr = $asyncOp.GetResults()
            $session = $mgr.GetCurrentSession()
            if ($session) {
                $propOp = $session.TryGetMediaPropertiesAsync()
                $timeout = 25
                while ($propOp.Status -eq 'Started' -and $timeout -gt 0) { Start-Sleep -Milliseconds 100; $timeout-- }
                if ($propOp.Status -eq 'Completed') {
                    $p = $propOp.GetResults()
                    if ($p.Title -or $p.Artist) {
                        return @{ title = $p.Title; artist = $p.Artist; source = $session.SourceAppUserModelId } | ConvertTo-Json -Compress
                    }
                }
            }
        }
    } catch {}

    # Tier 3: Window Title Fallback (Comprehensive Scan)
    try {
        $definition = @"
        using System;
        using System.Collections.Generic;
        using System.Runtime.InteropServices;
        using System.Text;

        public class WindowScanner {
            [DllImport("user32.dll")]
            private static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);
            private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

            [DllImport("user32.dll", CharSet = CharSet.Unicode)]
            private static extern int GetWindowText(IntPtr hWnd, StringBuilder strText, int maxCount);

            [DllImport("user32.dll")]
            private static extern bool IsWindowVisible(IntPtr hWnd);

            public static List<string> GetVisibleWindowTitles() {
                var titles = new List<string>();
                EnumWindows((hWnd, lParam) => {
                    if (IsWindowVisible(hWnd)) {
                        var sb = new StringBuilder(256);
                        GetWindowText(hWnd, sb, 256);
                        var title = sb.ToString();
                        if (!string.IsNullOrEmpty(title)) { titles.Add(title); }
                    }
                    return true;
                }, IntPtr.Zero);
                return titles;
            }
        }
"@
        Add-Type -TypeDefinition $definition -ErrorAction SilentlyContinue
        $titles = [WindowScanner]::GetVisibleWindowTitles()
        
        # 1. Spotify Check (Precise)
        $spotifyTitle = $titles | Where-Object { $_ -match "^Spotify$" -or $_ -match " - " } | Where-Object { 
            # If it's just "Spotify", it's not playing anything specific or is in a weird state
            # Usually Spotify titles are "Artist - Track" or just "Spotify"
            $_ -ne "Spotify" -and ($titles -contains "Spotify")
        } | Select-Object -First 1
        
        if ($spotifyTitle) {
             return @{ title = $spotifyTitle; artist = ""; source = "Spotify" } | ConvertTo-Json -Compress
        }
        # Backup Spotify check (if only one window exists)
        $spotifyProc = Get-Process -Name "Spotify" -ErrorAction SilentlyContinue
        if ($spotifyProc -and $spotifyProc.MainWindowTitle -ne "Spotify" -and $spotifyProc.MainWindowTitle -ne "") {
            return @{ title = $spotifyProc.MainWindowTitle; artist = ""; source = "Spotify" } | ConvertTo-Json -Compress
        }

        # 2. YouTube Check (Aggressive)
        $ytTitle = $titles | Where-Object { $_ -match "YouTube" } | Select-Object -First 1
        if ($ytTitle) {
            $cleanTitle = $ytTitle -replace " - YouTube.*$", ""
            $cleanTitle = $cleanTitle -replace "^\\(\\d+\\) ", "" # Remove (1) notification counts
            return @{ title = $cleanTitle; artist = "YouTube"; source = "Browser" } | ConvertTo-Json -Compress
        }

        # 3. Generic Media (SoundCloud, Netflix, etc.)
        $genericMedia = $titles | Where-Object { $_ -match "▶|Playing|Music|Netflix|SoundCloud" } | Select-Object -First 1
        if ($genericMedia) {
             return @{ title = $genericMedia; artist = ""; source = "Web Browser" } | ConvertTo-Json -Compress
        }
    } catch {}

    return "null"
    """
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True
        )
        output = result.stdout.strip()
        if output == "null" or not output:
            return None
        return json.loads(output)
    except Exception as e:
        logger.error(f"PowerShell fallback error: {e}")
        return None

async def _get_current_session_info():
    """Internal helper to get the current media session info using WinRT library."""
    try:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as SessionManager
        sessions = await SessionManager.request_async()
        current_session = sessions.get_current_session()
        if not current_session:
            return None
        
        info = await current_session.try_get_media_properties_async()
        if not info.title and not info.artist:
            return None

        return {
            "title": info.title,
            "artist": info.artist,
            "album": info.album_title,
            "source": current_session.source_app_user_model_id
        }
    except (ImportError, Exception) as e:
        # If library missing or error, use PowerShell which handles Tiers 2 & 3
        return _get_media_info_powershell()

# --- Standardized Command ---

def get_media_info(args: dict) -> str:
    """Read what's currently playing on Windows (YouTube, Spotify, etc.)."""
    try:
        # Attempt Tier 1 (WinRT Library) which also triggers fallbacks
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            info = loop.run_until_complete(_get_current_session_info())
            loop.close()
        except Exception:
            info = _get_media_info_powershell()

        if not info:
            return "No active media playback detected on the system."
        
        title = info.get("title", "Unknown Title")
        artist = info.get("artist", "")
        source = info.get("source", "System")
        
        # Clean up source app name
        if "Spotify" in source: source = "Spotify"
        elif "chrome" in source.lower() or "YouTube" in source: source = "Web Browser"
        elif "msedge" in source.lower(): source = "Edge Browser"
        elif "Microsoft.ZuneMusic" in source: source = "Media Player"

        # Handle "Artist - Title" splitting for window title fallbacks
        if not artist and " - " in title:
            # Most window titles are "Artist - Track" or "Track - Artist"
            # We'll just present it clearly
            return f"Currently playing: {title} (via {source})"
        
        if artist:
            return f"Currently playing: '{title}' by {artist} (via {source})"
        else:
            return f"Currently playing: '{title}' (via {source})"
        
    except Exception as e:
        logger.error(f"Media Sentinel Error: {e}")
        return f"Nexus Error: Could not read system media info. {str(e)}"
