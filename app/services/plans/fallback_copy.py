"""Conservative fallback copy derived from the resolved routine, not a new diagnosis.

Emerson should review this copy with the fixed titles before customer launch.
"""
REASONS = {
    'gentle_cleanse': 'Begin with gentle cleansing before the next care step.',
    'cleanse': 'Start with cleansing before you condition and style.',
    'clarify': 'Address product residue before you apply the next products.',
    'condition': 'Condition after cleansing to support the rest of the routine.',
    'light_condition': 'Keep conditioning light in this routine.',
    'protein_treatment': 'This routine prioritises strengthening before heavier care.',
    'scalp_treatment': 'Give scalp comfort its own step in the routine.',
    'moisture_seal': 'Follow the treatment step with moisture support.',
    'moisturise': 'Add a moisture step before styling.',
    'light_styler': 'Keep styling light after the cleansing and conditioning steps.',
    'anti_humectant_styler': 'Use the styling step to support humidity control.',
    'style': 'Finish with a styling step for your routine.',
    'gel_or_cast': 'Use this step to support definition and hold.',
    'seal': 'Finish with a sealing step to support moisture retention.',
    'sealant': 'Finish with a sealing step to support moisture retention.',
    'steam_or_heat_treatment': 'This step supports moisture absorption in the selected routine.',
    'stretch_or_elongate': 'Include a gentle stretch step for your curl pattern.',
    'maintain_current_steps': 'Keep the steps that already work for you.',
}


def fallback_prose(steps):
    return {'summary': 'Your routine follows the profile and concerns you shared. '
                       'Follow the steps in the order shown.',
            'climate_note': None,
            'steps': [{'step': step['step'], 'why': REASONS[step['step']], 'products': []}
                      for step in steps]}
