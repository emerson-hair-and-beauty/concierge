def get_water_hardness(country: str) -> str:
    """
    Determine if water is hard or soft based on the country.
    UAE, Saudi Arabia, and Oman have soft water; all others are hard.
    """
    soft_water_countries = {
        "uae", "united arab emirates", "ae",
        "saudi arabia", "saudi", "sa",
        "oman", "om"
    }
    
    # Normalize input for case-insensitive comparison
    normalized_country = country.strip().lower()
    
    if normalized_country in soft_water_countries:
        return "soft"
    else:
        return "hard"
