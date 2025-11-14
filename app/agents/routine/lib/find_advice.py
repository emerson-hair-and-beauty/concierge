from input.lib.classifier import (
    classify_porosity, 
    classify_scalp, 
    classify_damage, 
    classify_density, 
    classify_texture
)

CLASSIFIERS = {
    "porosity": classify_porosity,
    "scalp": classify_scalp,
    "damage": classify_damage,
    "density": classify_density,
    "texture": classify_texture,
}

def collateAdvice(answers):
    return {
        key: CLASSIFIERS[key](answers[key])
        for key in CLASSIFIERS
    }
