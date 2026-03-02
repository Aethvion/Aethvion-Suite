import requests
import logging
from typing import Dict, Any

# Setup logging
logger = logging.getLogger(__name__)

def get_weather(args: Dict[str, Any]) -> str:
    """
    Get weather data for a specified location using wttr.in.
    Args:
        args: Dictionary containing 'location' (string) and 'settings' (dict).
    Returns:
        A concise string describing the current weather.
    """
    location = args.get("location", "").strip()
    if not location:
        # Fallback to auto-location if none provided
        location = ""

    try:
        # We use format=j1 for a full JSON response from wttr.in
        url = f"https://wttr.in/{location}?format=j1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        current = data.get("current_condition", [{}])[0]
        temp_c = current.get("temp_C", "N/A")
        temp_f = current.get("temp_F", "N/A")
        weather_desc = current.get("weatherDesc", [{}])[0].get("value", "Unknown")
        humidity = current.get("humidity", "N/A")
        wind_speed = current.get("windspeedKmph", "N/A")
        
        # Get nearest area info for context (especially if location was empty)
        area = data.get("nearest_area", [{}])[0]
        region = area.get("region", [{}])[0].get("value", "")
        country = area.get("country", [{}])[0].get("value", "")
        area_name = area.get("areaName", [{}])[0].get("value", "this region")
        
        full_location = f"{area_name}, {region}, {country}".strip(", ")
        
        result = (
            f"Weather in {full_location}: {weather_desc}, {temp_c}°C ({temp_f}°F). "
            f"Humidity: {humidity}%, Wind: {wind_speed} km/h."
        )
        return result

    except requests.exceptions.RequestException as re:
        logger.error(f"Weather Link Request Error: {re}")
        return f"Weather Error: Could not reach weather service. ({str(re)})"
    except Exception as e:
        logger.error(f"Weather Link Error: {e}")
        return f"Weather Error: Unexpected failure retrieving data. {str(e)}"
