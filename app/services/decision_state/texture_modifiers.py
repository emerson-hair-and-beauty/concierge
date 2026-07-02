from app.services.decision_state.models import TextureModifiers

# Behaviour traits per texture_type — grounded in the curl-pattern behaviour mapping
# (2A/2B: low structure, easily weighed down ... 4C: fragile, max shrinkage).
# These are intentionally coarse (low/medium/high) to match every other profile
# dimension in this codebase (porosity, density, elasticity) rather than inventing
# a numeric scale nothing else uses.
_TEXTURE_MODIFIER_TABLE: dict[str, TextureModifiers] = {
    "2A":   TextureModifiers(shrinkage_factor="low",    fragility_index="low",    definition_difficulty="low", label= "Soft Waves"),    
    "2B":   TextureModifiers(shrinkage_factor="low",    fragility_index="low",    definition_difficulty="low", label= "Defined Waves"),    
    "2C":   TextureModifiers(shrinkage_factor="low",    fragility_index="low",    definition_difficulty="medium", label= "Defined Waves"),    
    "3A":   TextureModifiers(shrinkage_factor="low",    fragility_index="low",    definition_difficulty="medium", label= "Loose Curls"),
    "3B":   TextureModifiers(shrinkage_factor="medium",  fragility_index="medium", definition_difficulty="medium", label= "Defined Curls"),
    "3C":   TextureModifiers(shrinkage_factor="medium",  fragility_index="medium", definition_difficulty="high", label= "Tight Curls"),
    "4A":   TextureModifiers(shrinkage_factor="medium",  fragility_index="medium", definition_difficulty="medium", label= "Loose Coils"),
    "4B":   TextureModifiers(shrinkage_factor="high",    fragility_index="high",   definition_difficulty="high", label= "Dense Coils"),
    "4C":   TextureModifiers(shrinkage_factor="high",    fragility_index="high",   definition_difficulty="high", label= "Tight Coils"),
}

_DEFAULT_MODIFIERS = TextureModifiers(
    shrinkage_factor="medium", fragility_index="medium", definition_difficulty="medium", label="Unspecified"
)


def resolve_texture_modifiers(texture_type: str) -> TextureModifiers:
    return _TEXTURE_MODIFIER_TABLE.get(texture_type, _DEFAULT_MODIFIERS)
