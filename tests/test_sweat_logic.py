import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.environmental_factors.sweat_service import get_sweat_level, calculate_dew_point

def test_sweat_logic():
    test_cases = [
        # (temp, humidity, in_ac, expected, description)
        (35, 70, False, "HIGH",   "Hot + high humidity (dew point > 22)"),
        (35, 75, False, "HIGH",   "Humidity > 70% alone triggers HIGH"),
        (32, 20, False, "MEDIUM", "Hot but dry (temp > 28, dew point < 22)"),
        (25, 40, False, "LOW",    "Comfortable conditions"),
        (35, 70, True,  "LOW",    "Summer AC override — hot outside but user in AC"),
        (15, 50, True,  "DRY",    "Winter AC — cold outside + AC = dry air"),
        (10, 60, True,  "DRY",    "Winter AC — very cold outside"),
    ]

    print("--- Sweat Logic Service Test ---")
    all_pass = True
    for temp, hum, ac, expected, desc in test_cases:
        td = calculate_dew_point(temp, hum)
        result = get_sweat_level(temp, hum, in_ac=ac)
        status = "PASS" if result == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {status} | {desc}")
        print(f"         T={temp}°C | RH={hum}% | Td={td:.1f}°C | AC={ac} -> got={result}, expected={expected}")

    print(f"\n{'All tests passed.' if all_pass else 'Some tests FAILED.'}")

if __name__ == "__main__":
    test_sweat_logic()
