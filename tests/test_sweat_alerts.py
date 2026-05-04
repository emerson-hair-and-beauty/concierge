import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.environmental_factors.sweat_alert_service import check_sweat_trigger

def test_sweat_alerts():
    print("--- Sweat Alert Service Test ---")
    
    test_cases = [
        # Temp, Humidity, Description
        (35, 70, "High Humidity (Td > 22)"),
        (32, 20, "High Heat (T > 30)"),
        (22, 30, "Normal conditions (AC prompt expected)"),
    ]
    
    for temp, hum, desc in test_cases:
        prompt = check_sweat_trigger(temp, hum)
        print(f"Desc: {desc}")
        print(f"  T: {temp}°C | RH: {hum}%")
        print(f"  Prompt: {prompt}")
        print("-" * 80)

if __name__ == "__main__":
    test_sweat_alerts()
