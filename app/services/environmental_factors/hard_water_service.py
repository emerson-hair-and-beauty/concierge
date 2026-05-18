def get_water_hardness(country: str, has_filtration: bool = False) -> str:
    if has_filtration:
        return "soft"

    # GCC countries default to hard — desalinated water carries high mineral content
    gcc_countries = {
        "uae", "united arab emirates", "ae",
        "saudi arabia", "saudi", "sa",
        "oman", "om",
        "qatar", "qa",
        "kuwait", "kw",
        "bahrain", "bh",
    }

    if country.strip().lower() in gcc_countries:
        return "hard"

    return "hard"
