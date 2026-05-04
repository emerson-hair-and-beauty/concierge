import asyncio
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.environmental_factors.weather_service import get_city_environmental_data

async def main():
    city = "Dubai"
    print(f"--- Unified Weather Service Test ---")
    
    # Test 1: Get Everything
    print(f"\n[Test 1] Fetching all data for '{city}'...")
    all_data = await get_city_environmental_data(city, attribute="all")
    if all_data:
        print(f"Success! Result: {all_data}")
    
    # Test 2: Get Just Heat
    print(f"\n[Test 2] Fetching only 'heat' for '{city}'...")
    heat = await get_city_environmental_data(city, attribute="heat")
    if heat is not None:
        print(f"Success! Temperature: {heat}°C")
        
    # Test 3: Get Just Humidity
    print(f"\n[Test 3] Fetching only 'humidity' for '{city}'...")
    humidity = await get_city_environmental_data(city, attribute="humidity")
    if humidity is not None:
        print(f"Success! Humidity: {humidity}%")

if __name__ == "__main__":
    asyncio.run(main())
