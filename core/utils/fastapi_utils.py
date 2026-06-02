"""
core/utils/fastapi_utils.py
Common utilities for Aethvion Suite FastAPI applications.
"""

import os
from fastapi import FastAPI, Request

def add_dev_cache_control(app: FastAPI):
    """
    Adds a middleware to the FastAPI app that disables caching for all
    requests if the AETHVION_DEV environment variable is set to '1'.
    
    This is highly useful for local development to ensure that UI changes
    (HTML/JS/CSS) are reflected immediately on refresh.
    """
    
    @app.middleware("http")
    async def cache_control_middleware(request: Request, call_next):
        response = await call_next(request)
        
        # Only apply if dev mode is explicitly enabled
        if os.getenv("AETHVION_DEV") == "1":
            # Target common static/viewer paths or just apply globally for safety
            # For Aethvion internal apps, global no-cache in dev mode is preferred.
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            
        return response

    return app
