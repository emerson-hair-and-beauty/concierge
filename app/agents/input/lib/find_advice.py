from .classifier import (
    classify_porosity,
    classify_scalp,
    classify_damage,
    classify_density,
    classify_texture,
)

CLASSIFIERS = {
    "porosity": classify_porosity,
    "scalp": classify_scalp,
    "damage": classify_damage,
    "density": classify_density,
    "texture": classify_texture,
}

def collateAdvice(answers):
    directives = {}
    product_needs = {}
    routine_flags = {}

    for key, classifier in CLASSIFIERS.items():
        info = classifier(answers[key])
        directives[key] = info.get("directive", "")
        product_needs[key] = info.get("product_needs", [])
        routine_flags[key] = info.get("routine_flags", [])

    return {
        "directives": directives,
        "product_needs": product_needs,
        "routine_flags": routine_flags
    }


    

    
