from hair_profile.hair_profile_generator import (
    POROSITY_ADVICE,
    TEXTURE_ADVICE,
    DENSITY_ADVICE,
    SCALP_ADVICE,
    WASH_FREQUENCY_ADVICE,
    DAMAGE_ADVICE,
    TIME_CONSTRAINT,
    CLEAN_PREFERENCE,
    VEGAN_PREFERENCE,
    CRUELTY_FREE_PREFERENCE,
    BUDGET_ADVICE
)
from hair_profile.hair_porosity import find_porosity_score


# Sample onboarding answers from the client

onboardingAnswers = {
    'porosity': ['A', 'B', 'C', 'A', 'B', 'A', 'B'],
    'texture': 'Wavy',
    'density': 'Medium',
    'scalp': 'oily',
    'wash_frequency': 'Every 2-3 days',
    'damage': 'Yes',
    'clean_preference': "No",
    'vegan_preference': "No",
    'cruelty_free_preference': "No",
    'budget': '$25-$50',
}

porosityOnboardingAnswers = ['A', 'B', 'C', 'A', 'B']
porosityLevel = find_porosity_score(porosityOnboardingAnswers)

systemPrompt = "You are a highly experienced, certified Hair Care Formulation Scientist and Product Recommendation Engine. Your primary goal is to generate a personalized, five-step hair routine and recommend products that maximize the health and success of the user's hair by strictly intersecting all provided data points. Your advice must be professional, practical, and prioritize the user's most restrictive constraints (Budget, Time, and Ethical Preferences)."
print(systemPrompt)
print(f"Porosity Level: {porosityLevel}")

userProfileDetails = f"{POROSITY_ADVICE[porosityLevel]}" + f"{TEXTURE_ADVICE[onboardingAnswers['texture']]}" + \
    f"{DENSITY_ADVICE[onboardingAnswers['density']]}" + f"{SCALP_ADVICE[onboardingAnswers['scalp']]}" + \
    f"{WASH_FREQUENCY_ADVICE[onboardingAnswers['wash_frequency']]}" + \
    f"{DAMAGE_ADVICE[onboardingAnswers['damage']]}" 

productFilteringDetails = f"{CLEAN_PREFERENCE[onboardingAnswers['clean_preference']]}" + \
    f"{VEGAN_PREFERENCE[onboardingAnswers['vegan_preference']]}" + \
    f"{CRUELTY_FREE_PREFERENCE[onboardingAnswers['cruelty_free_preference']]}" + \
    f"{BUDGET_ADVICE[onboardingAnswers['budget']]}."

print("User Profile Details:")
print(userProfileDetails)
print("Product Filtering Details:")
print(productFilteringDetails)











