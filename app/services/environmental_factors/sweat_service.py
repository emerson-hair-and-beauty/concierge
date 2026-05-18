import math

def calculate_dew_point(temp_c: float, humidity: float) -> float:
    """
    Calculate Dew Point (Td) from Celsius Temperature and Relative Humidity.
    Formula:
    gamma(T, RH) = ln(RH/100) + (17.625 * T) / (243.04 + T)
    Td = (243.04 * gamma) / (17.625 - gamma)
    """
    if humidity <= 0:
        return -50.0

    gamma = math.log(humidity / 100.0) + (17.625 * temp_c) / (243.04 + temp_c)
    td = (243.04 * gamma) / (17.625 - gamma)
    return td

def get_sweat_level(temp_c: float, humidity: float, in_ac: bool = False) -> str:
    """
    Determine Sweat Level (HIGH, MEDIUM, LOW, DRY) based on Temperature,
    Dew Point, AC context, and season.
    """
    if in_ac:
        # Winter scenario: AC + cold outside = dry air exposure
        if temp_c < 18:
            return "DRY"
        return "LOW"

    td = calculate_dew_point(temp_c, humidity)

    # Trigger on humidity OR heat — either alone is sufficient
    if td > 22 or humidity > 70:
        return "HIGH"
    elif temp_c > 28:
        return "MEDIUM"
    else:
        return "LOW"
