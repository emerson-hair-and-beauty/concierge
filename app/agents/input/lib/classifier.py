# the purpose of this file is to do the following: 
# 1. Define a Classifier class that can classify input data
# 2. The Classifier should classify data based on hair type, and other relevant features


def classify_scalp(answer):
    scalp_map = {
        'Oily': {
            "label": "Oily Scalp",
            "directive": "Focus on scalp cleansing, regulate sebum, avoid heavy oils.",
            "product_needs": ["clarifying shampoo", "scalp exfoliant"],
            "routine_flags": ["more_frequent_wash", "lightweight_products"]
        },
        'Dry': {
            "label": "Dry Scalp",
            "directive": "Increase scalp hydration, avoid strong surfactants, use soothing agents.",
            "product_needs": ["soothing ingredients", "humectants"],
            "routine_flags": ["gentle_cleanse", "scalp_serum"]
        },
        'Normal': {
            "label": "Normal Scalp",
            "directive": "Maintain balance with gentle cleansing and lightweight conditioners.",
            "product_needs": ["mild shampoo"],
            "routine_flags": ["standard_cleansing"]
        },
        'Sensitive': {
            "label": "Sensitive Scalp",
            "directive": "Avoid fragrance, use hypoallergenic formulas, avoid harsh cleansers.",
            "product_needs": ["fragrance_free", "hypoallergenic"],
            "routine_flags": ["low_irritation"]
        }
    }

    return scalp_map.get(answer, {
        "label": "Unknown Scalp Type",
        "directive": "No directive available.",
        "product_needs": [],
        "routine_flags": []
    })

def classify_moisture_behaviour(answer):
    """
    Previously 'classify_porosity'. The client now labels this as 'Moisture Behaviour'.
    Accepts both old porosity labels and new moisture behaviour labels.
    """
    moisture_map = {
        # New labels (Moisture Behaviour screen)
        'Low Porosity': {
            "label": "Low Porosity",
            "directive": "Use lightweight humectants, avoid heavy oils and butters, incorporate heat for better absorption.",
            "product_needs": ["humectants", "lightweight formulas"],
            "routine_flags": ["avoid_butters", "use_heat_for_masks"]
        },
        'Medium Porosity': {
            "label": "Medium Porosity",
            "directive": "Maintain balance with regular moisture and protein.",
            "product_needs": ["balanced_moisture", "moderate_protein"],
            "routine_flags": ["standard_care"]
        },
        'High Porosity': {
            "label": "High Porosity",
            "directive": "Use rich moisturizers, seal moisture, incorporate protein.",
            "product_needs": ["protein", "occlusives"],
            "routine_flags": ["seal_moisture", "strengthen"]
        },
        # Backward compatibility aliases
        'Low': {
            "label": "Low Porosity",
            "directive": "Use lightweight humectants, avoid heavy oils and butters, incorporate heat for better absorption.",
            "product_needs": ["humectants", "lightweight formulas"],
            "routine_flags": ["avoid_butters", "use_heat_for_masks"]
        },
        'Medium': {
            "label": "Medium Porosity",
            "directive": "Maintain balance with regular moisture and protein.",
            "product_needs": ["balanced_moisture", "moderate_protein"],
            "routine_flags": ["standard_care"]
        },
        'High': {
            "label": "High Porosity",
            "directive": "Use rich moisturizers, seal moisture, incorporate protein.",
            "product_needs": ["protein", "occlusives"],
            "routine_flags": ["seal_moisture", "strengthen"]
        },
    }

    return moisture_map.get(answer, {
        "label": "Unknown Moisture Behaviour",
        "directive": "No directive available.",
        "product_needs": [],
        "routine_flags": []
    })

# Keep old name as an alias for backward compatibility
classify_porosity = classify_moisture_behaviour

def classify_texture(answer):
    """
    Updated to match new onboarding options:
      - Soft waves     → Type 2
      - Loose curls    → Type 3A/B
      - Spring curls   → Type 3C
      - Tight coils    → Type 4
    Old generic labels (Wavy, Curly, Coily, Straight) are kept as aliases.
    """
    texture_map = {
        # New onboarding labels
        'Soft waves': {
            "label": "Type 2 — Soft Waves",
            "directive": "Use lightweight gels and creams that enhance and define wave pattern. Avoid heavy products that collapse waves.",
            "product_needs": ["light_gels", "mousse", "lightweight_leave_in"],
            "routine_flags": ["enhance_waves", "avoid_heavy"]
        },
        'Loose curls': {
            "label": "Type 3A/B — Loose Curls",
            "directive": "Enhance definition and bounce with curl creams and medium-hold gels. Focus on moisture and frizz control.",
            "product_needs": ["curl_creams", "medium_gels", "leave_in_conditioner"],
            "routine_flags": ["enhance_curls", "frizz_control"]
        },
        'Spring curls': {
            "label": "Type 3C — Spring Curls",
            "directive": "Use hold-forward products to define tight curl pattern. Prioritise moisture retention and anti-frizz sealants.",
            "product_needs": ["defining_gel", "curl_cream", "anti_frizz_serum"],
            "routine_flags": ["strong_definition", "seal_moisture", "frizz_control"]
        },
        'Tight coils': {
            "label": "Type 4 — Tight Coils",
            "directive": "Use rich moisturizers, creams and sealant oils. Minimise manipulation; protective styling recommended.",
            "product_needs": ["butters", "oils", "thick_creams"],
            "routine_flags": ["high_moisture", "protective_styles", "seal_with_oil"]
        },
        # Backward compatibility aliases
        'Straight': {
            "label": "Type 1",
            "directive": "Avoid heavy products, focus on volume and scalp health.",
            "product_needs": ["lightweight stylers"],
            "routine_flags": ["boost_volume"]
        },
        'Wavy': {
            "label": "Type 2",
            "directive": "Use lightweight gels and creams that enhance wave definition.",
            "product_needs": ["light_gels", "light_creams"],
            "routine_flags": ["enhance_waves"]
        },
        'Curly': {
            "label": "Type 3",
            "directive": "Enhance definition with curl creams and gels, focus on moisture retention.",
            "product_needs": ["curl_creams", "gels"],
            "routine_flags": ["enhance_curls"]
        },
        'Coily': {
            "label": "Type 4",
            "directive": "Use rich moisturizers and sealants, minimize manipulation.",
            "product_needs": ["butters", "oils"],
            "routine_flags": ["high_moisture", "protective_styles"]
        }
    }

    return texture_map.get(answer, {
        "label": "Unknown Texture",
        "directive": "No directive available.",
        "product_needs": [],
        "routine_flags": []
    })

def classify_density(answer):
    density_map = {
        'Thin': {
            "label": "Low Density",
            "directive": "Use lightweight products to avoid flattening.",
            "product_needs": ["foams", "light gels"],
            "routine_flags": ["avoid_heavy"]
        },
        'Medium': {
            "label": "Medium Density",
            "directive": "Use balanced stylers, avoid unnecessary heaviness.",
            "product_needs": ["medium_hold_gels"],
            "routine_flags": ["balanced_volume"]
        },
        'Thick': {
            "label": "High Density",
            "directive": "Use defining stylers with strong hold to control volume.",
            "product_needs": ["strong_hold_gels", "creams"],
            "routine_flags": ["strong_hold"]
        }
    }

    return density_map.get(answer, {
        "label": "Unknown Density",
        "directive": "No directive available.",
        "product_needs": [],
        "routine_flags": []
    })

def classify_damage(answer):
    damage_map = {
        'Yes': {
            "label": "Damaged Hair",
            "directive": "Prioritize repair, strengthen with protein and bond builders.",
            "product_needs": ["protein", "bond_builders"],
            "routine_flags": ["repair_mode"]
        },
        'No': {
            "label": "Healthy Hair",
            "directive": "Maintain hydration and protect from future damage.",
            "product_needs": ["moisturizers", "UV_protection"],
            "routine_flags": ["maintenance"]
        }
    }

    return damage_map.get(answer, {
        "label": "Unknown Damage State",
        "directive": "No directive available.",
        "product_needs": [],
        "routine_flags": []
    })

def classify_humidity_response(answer):
    """
    GCC-specific climate classifier. Determines how the user's curls react to humidity.
    This is treated as an environmental constraint (not an intrinsic hair trait).
    """
    humidity_map = {
        'Expand and become frizzy': {
            "label": "High Humidity Sensitivity",
            "directive": "Prioritise anti-humectant strategy in humid conditions: use sealants and strong-hold gels to block moisture from the air.",
            "product_needs": ["strong_hold_gel", "anti_frizz_sealant", "non_humectant_stylers"],
            "routine_flags": ["anti_humectant", "strong_hold", "humidity_shield"]
        },
        'Lose definition': {
            "label": "Moderate Humidity Sensitivity",
            "directive": "Layer a medium-hold gel or cream over leave-in to maintain definition in humidity. Avoid heavy humectants as a top layer.",
            "product_needs": ["medium_hold_gel", "curl_defining_cream"],
            "routine_flags": ["definition_lock", "frizz_control"]
        },
        'Stay mostly the same': {
            "label": "Low Humidity Sensitivity",
            "directive": "Hair is relatively humidity-resistant. Standard moisture-balance routine applies.",
            "product_needs": [],
            "routine_flags": ["standard_care"]
        }
    }

    return humidity_map.get(answer, {
        "label": "Unknown Humidity Response",
        "directive": "No directive available.",
        "product_needs": [],
        "routine_flags": []
    })
