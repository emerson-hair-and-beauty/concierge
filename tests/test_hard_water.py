import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.environmental_factors.hard_water_service import get_water_hardness

def test_hard_water():
    test_cases = [
        # (country, has_filtration, expected, description)
        ("UAE",          False, "hard", "GCC - no filtration -> hard"),
        ("Saudi Arabia", False, "hard", "GCC - no filtration -> hard"),
        ("Oman",         False, "hard", "GCC - no filtration -> hard"),
        ("Qatar",        False, "hard", "GCC - no filtration -> hard"),
        ("UAE",          True,  "soft", "GCC - filtration present -> soft"),
        ("Saudi Arabia", True,  "soft", "GCC - filtration present -> soft"),
        ("UK",           False, "hard", "Non-GCC -> hard"),
        ("Nigeria",      False, "hard", "Non-GCC -> hard"),
        ("Nigeria",      True,  "soft", "Non-GCC - filtration present -> soft"),
    ]

    print("--- Hard Water Service Test ---")
    all_pass = True
    for country, filtration, expected, desc in test_cases:
        result = get_water_hardness(country, has_filtration=filtration)
        status = "PASS" if result == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {status} | {desc}")
        print(f"         country={country}, filtration={filtration} -> got={result}, expected={expected}")

    print(f"\n{'All tests passed.' if all_pass else 'Some tests FAILED.'}")

if __name__ == "__main__":
    test_hard_water()
