"""
core/bridges/screen_ocr_bridge.py
Screen OCR & Visual Text Reader Connector.
Captures the screen and extracts all readable text using native Windows 10/11 OCR
(Windows.Media.Ocr) so even text-only local GGUF models can read what is on screen.
"""

import platform
import re
import subprocess
from pathlib import Path
from core.bridges.screen_capture import take_screenshot
from core.bridges.window_focus_bridge import get_active_window


_PS_OCR_SCRIPT = r"""
param([string]$ImagePath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Foundation.IAsyncOperation`1, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) {
    $lang = New-Object Windows.Globalization.Language("en-US")
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
}
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) {
    Write-Output $line.Text
}
$stream.Dispose()
"""


def _run_windows_ocr(image_path: str) -> str:
    res = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PS_OCR_SCRIPT, image_path],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    return ""


def extract_screen_text(args: dict = None) -> str:
    """Capture a screenshot of the monitor (default monitor=1) and extract all visible text via OCR."""
    if args is None:
        args = {}
    if "monitor" not in args:
        args = dict(args, monitor=1)

    shot_output = take_screenshot(args)
    match = re.search(r"Saved to:\s*(.+)", shot_output)
    img_path = match.group(1).strip() if match else ""

    ocr_text = ""
    if img_path and Path(img_path).exists() and platform.system() == "Windows":
        try:
            ocr_text = _run_windows_ocr(img_path)
        except Exception:
            ocr_text = ""

    win_info = get_active_window({"max_windows": 6})
    parts = [shot_output, "", win_info]
    if ocr_text:
        if len(ocr_text) > 10000:
            ocr_text = ocr_text[:10000] + "\n...[OCR truncated]"
        parts.append(f"\nExtracted Screen Text (OCR):\n{ocr_text}")
    else:
        parts.append("\n(OCR text extraction returned no text blocks; see attached screenshot and active window titles above.)")
    return "\n".join(parts)
