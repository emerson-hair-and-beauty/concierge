import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.environmental_factors.hard_water_service import get_water_hardness

def test_hard_water():
    test_cases = [
        ("UAE", "soft"),
        ("ae", "soft"),
        ("Saudi Arabia", "soft"),
        ("OMAN", "soft"),
        ("UK", "hard"),
        ("USA", "hard"),
        ("Nigeria", "hard")
    ]
    
    print("--- Hard Water Service Test ---")
    for country, expected in test_cases:
        result = get_water_hardness(country)
        status = "PASS" if result == expected else "FAIL"
        print(f"Country: {country:15} | Result: {result:5} | Status: {status}")

if __name__ == "__main__":
    test_hard_water()
