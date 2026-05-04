import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.environmental_factors.sweat_service import get_sweat_level, calculate_dew_point

def test_sweat_logic():
    print("--- Sweat Logic Service Test ---")
    
    test_cases = [
        # Temp, Humidity, in_ac, Expected Level, Description
        (35, 70, False, "HIGH", "Very humid and hot (Td > 22)"),
        (32, 20, False, "MEDIUM", "Hot but dry (T > 30, Td < 22)"),
        (25, 40, False, "LOW", "Comfortable (T < 30, Td < 22)"),
        (35, 70, True, "LOW", "AC Override (High outdoor but user is in AC)"),
    ]
    
    for temp, hum, ac, expected, desc in test_cases:
        td = calculate_dew_point(temp, hum)
        result = get_sweat_level(temp, hum, in_ac=ac)
        status = "PASS" if result == expected else "FAIL"
        print(f"Desc: {desc:40}")
        print(f"  T: {temp}°C | RH: {hum}% | Td: {td:.2f}°C | AC: {ac} | Result: {result} | Status: {status}")
        print("-" * 80)

if __name__ == "__main__":
    test_sweat_logic()
