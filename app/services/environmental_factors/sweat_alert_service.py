from typing import Optional
from app.services.environmental_factors.sweat_service import get_sweat_level, calculate_dew_point

def check_sweat_trigger(temp_c: float, humidity: float) -> Optional[str]:
    """
    Checks if environmental conditions warrant a sweat-related prompt.
    Returns a string prompt if a trigger is hit, otherwise None.
    """
    # Environmental Triggers
    sweat_level = get_sweat_level(temp_c, humidity)
    
    if sweat_level == "HIGH":
        td = calculate_dew_point(temp_c, humidity)
        return (f"The forecast predicts very high humidity today (Peak Dew Point: {td:.1f}°C). "
                f"Sweat may sit on your skin and clog pores. "
                f"Are you spending most of your day in AC?")
    
    elif sweat_level == "MEDIUM":
        return (f"The forecast predicts a hot day ({temp_c}°C). Active sweating might "
                f"leave salt on your hair. Are you spending most of your day in AC?")
    
    # Fallback: Always ask about AC even in normal conditions
    return "The weather looks great today! Are you spending most of your day in AC?"
