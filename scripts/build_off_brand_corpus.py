"""Build the off-brand half of the Emerson tone training set.

Why this file exists
--------------------
The first model was trained in on-brand-only mode, where Simasia generates the
negatives by asking an LLM to rewrite each on-brand chunk "more formally", "more
hedged", and so on. The LLM produced polite paraphrases rather than off-brand
copy: 6 of 600 came back byte-identical to their source and ~60% landed within
0.9 cosine of it. The classifier was shown Emerson's voice twice and told the two
halves were opposites, so it never learned a boundary — good and bad examples
overlapped 71% in the resulting scores.

These are written by hand instead, from the prohibitions Emerson's own voice
guide already spells out (see _VOICE_BLOCK in response_composer.py). That guide
is a specification of off-brand; this file just instantiates it.

Two rules govern every example here
-----------------------------------
1. **Same topic, wrong voice.** Every example is about curly or textured hair.
   If the negatives were about order tracking and the positives about hair, the
   classifier would learn to detect the topic and score any hair-related text as
   on-brand — which is not the question we are asking it.

2. **Match the on-brand granularity.** Emerson's chunks average 38 words across
   about two sentences. These are written to the same shape so the model is not
   also learning "short text = bad".

Expanding this
--------------
Add examples to the registers below. More is better, and real text is better
still: rejected replies from feedback_log.jsonl are the strongest negatives you
will ever have, because they are genuinely off-brand, genuinely about hair, and
genuinely written in the register your pipeline actually produces. Fold those in
as they accumulate and lean on this file less.

Usage:
    python scripts/build_off_brand_corpus.py
    python scripts/check_corpus_separation.py    # verify before you train
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.tone_registers import EXAMPLES  # noqa: E402

OUTPUT_PATH = Path("data/simasia/emerson_off_brand_corpus.txt")


# The examples and the taxonomy live in app/services/tone_registers.py so that the
# category a reviewer picks on a thumbs-down, the category the tone model infers
# from a low score, and the category a training example belongs to are all the
# same string. See that module for the rules every example follows.
REGISTERS = EXAMPLES


def main() -> None:
    examples = [text for register in REGISTERS.values() for text in register]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Blank-line separated, no register labels: the labels are scaffolding for
    # whoever edits this file, and would become training text if written out.
    OUTPUT_PATH.write_text("\n\n".join(examples) + "\n", encoding="utf-8")

    print(f"Wrote {len(examples)} off-brand examples to {OUTPUT_PATH}")
    for name, register in REGISTERS.items():
        words = sum(len(t.split()) for t in register) / len(register)
        print(f"  {name:20s} {len(register):3d} examples   avg {words:.0f} words")
    print("\nNext: python scripts/check_corpus_separation.py")


if __name__ == "__main__":
    main()
