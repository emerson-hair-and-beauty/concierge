import math

def calculate_dew_point(temp_c: float, humidity: float) -> float:
    """
    Calculate Dew Point (Td) from Celsius Temperature and Relative Humidity.
    Formula:
    gamma(T, RH) = ln(RH/100) + (17.625 * T) / (243.04 + T)
    Td = (243.04 * gamma) / (17.625 - gamma)
    """
    if humidity <= 0:
        return -50.0 # Extreme fallback
    
    gamma = math.log(humidity / 100.0) + (17.625 * temp_c) / (243.04 + temp_c)
    td = (243.04 * gamma) / (17.625 - gamma)
    return td

def get_sweat_level(temp_c: float, humidity: float, in_ac: bool = False) -> str:
    """
    Determine Sweat Level (HIGH, MEDIUM, LOW) based on Temperature, 
    Dew Point, and contextual override (AC).
    """
    # Contextual Override: If spending the day in AC, sweat is LOW
    if in_ac:
        return "LOW"
    
    td = calculate_dew_point(temp_c, humidity)
    
    # Logic Gate Matrix
    if td > 22:
        return "HIGH"
    elif temp_c > 30:
        return "MEDIUM"
    else:
        return "LOW"
