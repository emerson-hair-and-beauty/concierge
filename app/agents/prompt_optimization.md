⭐ 7 Key Optimizations
1. Add a strict interpretation rule

LLMs often combine dictionary values incorrectly.
We add:

Each directive describes a need. Combine all directives into a single unified perspective.
If any directive conflicts, the safest or most gentle option wins.

2. Add a strict definition for routine_flags

Right now the LLM has to guess what a flag means.

You need something like:

Routine flags modify steps. Treat them as instructions:
- flags starting with "avoid_" remove certain actions or ingredients
- flags starting with "use_" enforce their action
- flags about frequency modify the cleansing/conditioning cadence
- flags relating to texture modify styling


You want to teach the agent how to use flags.

3. Add explicit forbidden behaviors (avoid hallucinations)
You must not:
- invent hair traits not in the directives
- add product names
- add brand names
- introduce new concerns not mentioned
- add ingredients that contradict any 'avoid_' routine flags

4. Enforce short, clear responses

Models naturally write long.

Use:

Write all actions in 1–2 concise sentences.
Keep note fields under 25 words.

5. Define allowed ingredient categories

Otherwise the LLM might invent weird ones.

Example:

Allowed ingredient examples (not required): humectants, lightweight oils, gentle surfactants, protein, bond builders, film-formers, emollients, anti-frizz agents.

6. Add a "How to Think" section

Modern agent prompting expects a thinking instruction.

Example:

Think step-by-step. First interpret directives.
Next interpret routine_flags.
Then merge them.
Finally generate the output JSON.
Do not include your reasoning in the final answer.


This reduces chaos by guiding the LLM’s internal chain-of-thought.

7. Add an example JSON (very short)

Not the full routine—just one sample block so it knows the tone.

Example:

Example format (do not copy contents, only follow structure):
{
  "routine": [
    {
      "step": "Cleanse",
      "action": "Use a gentle shampoo.",
      "ingredients": ["gentle surfactants", "soothing botanicals"],
      "notes": "Keep scalp buildup low."
    }
  ]
}


This dramatically increases consistency.

⭐ OPTIMIZED ROUTINE PROMPT (If you want it)

If you want, I can rewrite your RoutineAgent prompt into a fully optimized version that includes:

Combination logic

Constraint enforcement

Flag interpretation

Step-by-step rules

Output format safety

Guidance for ingredients

Strict length limits

An embedded example

And it will work with your existing orchestrator exactly as-is.