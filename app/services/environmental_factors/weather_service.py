import httpx
from typing import Any, Optional, Union
from app.config import WEATHER_API_KEY
from app.services.environmental_factors.sweat_service import get_sweat_level

async def get_city_environmental_data(city_name: str, attribute: str = "all", in_ac: bool = False) -> Any:
    """
    Unified function to get environmental data for a city from OpenWeather.
    
    Args:
        city_name: Name of the city.
        attribute: The specific data needed ('heat', 'humidity', 'coords', or 'all').
                   - 'heat': returns temperature in Celsius (float)
                   - 'humidity': returns humidity percentage (int)
                   - 'coords': returns (lat, lon) tuple
                   - 'sweat': returns sweat level (HIGH, MEDIUM, LOW)
                   - 'all': returns a dict with all fields
        in_ac: Boolean flag for contextual override (spending the day in AC).
    """
    if not WEATHER_API_KEY:
        print("[WeatherService] WEATHER_API_KEY not configured.")
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Geocoding Call (Always needed to get lat/lon)
            geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_name}&limit=1&appid={WEATHER_API_KEY}"
            geo_res = await client.get(geo_url)
            geo_res.raise_for_status()
            geo_data = geo_res.json()
            
            if not geo_data or len(geo_data) == 0:
                print(f"[WeatherService] No coordinates found for: {city_name}")
                return None
            
            lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
            
            # If the user only wanted coordinates, we can stop here
            if attribute == "coords":
                return lat, lon

            # 2. Weather Forecast Call (Needed for heat/humidity prediction)
            # Fetching 5-day/3-hour forecast
            forecast_url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric"
            forecast_res = await client.get(forecast_url)
            forecast_res.raise_for_status()
            forecast_data = forecast_res.json()
            
            # Identify Peak Conditions in the next 24 hours (first 8 intervals of 3 hours)
            forecast_list = forecast_data.get("list", [])[:8]
            
            if not forecast_list:
                print(f"[WeatherService] No forecast data available for {city_name}")
                return None
                
            max_temp = -100.0
            max_humidity = 0
            
            for item in forecast_list:
                main = item.get("main", {})
                temp = main.get("temp", -100.0)
                hum = main.get("humidity", 0)
                
                if temp > max_temp:
                    max_temp = temp
                if hum > max_humidity:
                    max_humidity = hum

            heat = max_temp
            humidity = max_humidity
            
            # Calculate Sweat Level based on predicted peaks
            sweat_level = None
            if heat != -100.0:
                sweat_level = get_sweat_level(heat, humidity, in_ac=in_ac)

            # 3. Return requested attribute
            if attribute == "heat":
                return heat
            elif attribute == "humidity":
                return humidity
            elif attribute == "sweat":
                return sweat_level
            elif attribute == "all":
                return {
                    "city": city_name,
                    "lat": lat,
                    "lon": lon,
                    "peak_heat": heat,
                    "peak_humidity": humidity,
                    "predicted_sweat_level": sweat_level
                }
            else:
                print(f"[WeatherService] Unknown attribute requested: {attribute}")
                return None

    except Exception as e:
        print(f"[WeatherService] Error fetching data for {city_name}: {e}")
        return None
