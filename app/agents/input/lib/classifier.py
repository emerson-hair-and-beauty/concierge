# the purpose of this file is to do the following: 
# 1. Define a Classifier class that can classify input data
# 2. The Classifier should classify data based on hair type, and other relevant features
from .hair_porosity import find_porosity_score


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

def classify_porosity(answer):
    porosity = find_porosity_score(answer)

    porosity_map = {
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
        }
    }

    return porosity_map.get(porosity, {
        "label": "Unknown Porosity",
        "directive": "No directive available.",
        "product_needs": [],
        "routine_flags": []
    })

def classify_texture(answer):
    texture_map = {
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
