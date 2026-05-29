# ── Aethvion Suite — headless / server-only Docker image ─────────────────────
#
# This image runs the FastAPI dashboard + REST API without a GUI.
# The desktop GUI (CustomTkinter launcher) and Windows-only integrations
# (winrt media control) are deliberately excluded.
#
# Build:
#   docker build -t aethvion-suite .
#
# Run:
#   docker run -p 8000:8000 \
#     -e GOOGLE_AI_API_KEY=your_key \
#     -e OPENAI_API_KEY=your_key \
#     -v $(pwd)/data:/app/data \
#     aethvion-suite
#
# The dashboard will be available at http://localhost:8000
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# System deps required by opencv-python (headless) and mediapipe
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1-mesa-glx \
        libgomp1 \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Install Python dependencies ───────────────────────────────────────────────
COPY pyproject.toml ./

# Install headless opencv (avoids pulling in X11 libs)
RUN pip install --no-cache-dir opencv-python-headless

# Install core deps without Windows-only or GUI extras
# We exclude: customtkinter, winrt-*, mediapipe (has binary wheels per platform)
# and install the rest from pyproject.toml core + [memory] group.
RUN pip install --no-cache-dir \
        "fastapi>=0.109.1" \
        "uvicorn[standard]>=0.24.0" \
        "pydantic>=2.0.0" \
        "pyyaml>=6.0" \
        "python-dotenv>=1.0.0" \
        "rich>=13.0.0" \
        "psutil>=5.9.0" \
        "mss>=10.0.0" \
        "spotipy>=2.23.0" \
        "python-multipart>=0.0.7" \
        "discord.py>=2.3.0" \
        "google-genai>=1.0.0" \
        "openai>=1.0.0" \
        "anthropic>=0.40.0" \
        "requests>=2.31.0" \
        "pytesseract" \
        "Pillow" \
        "chromadb>=0.4.0" \
        "sentence-transformers>=2.2.0" \
        "networkx>=3.0"

# ── Copy source ───────────────────────────────────────────────────────────────
COPY . .

# Install the package itself (editable) so `core.*` imports resolve
RUN pip install --no-cache-dir -e . --no-deps

# ── Runtime config ────────────────────────────────────────────────────────────
# Persist user data outside the container
VOLUME ["/app/data", "/app/assets"]

# Dashboard port
EXPOSE 8000

# Health check — hits the version API
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/system/version-info')" || exit 1

# ── Entrypoint ────────────────────────────────────────────────────────────────
# Start the web server. Browser auto-open is skipped in a headless environment
# (open_app_window fails silently). PORT env var sets the listen port.
ENV PORT=8000
CMD ["python", "-m", "core.main"]
