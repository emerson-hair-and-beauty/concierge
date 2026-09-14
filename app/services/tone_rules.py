"""Deterministic voice checks — the rules that are word lists, not judgement calls.

Emerson's voice guide contains two kinds of rule, and they need different tools.

**Enumerable rules.** "Never use: holy grail, game changer, obsessed, amazing,
love, perfect." "Never say: You need to... / Guaranteed results... / The secret
is..." And the resolution rule, which names its own tells: "it depends", "varies",
"might", "in some cases". These are lists. A regex catches every instance, costs
nothing, and can say exactly which word was wrong.

**Judgement rules.** Whether a reply carries authority, whether it sounds like a
support ticket, whether it reads like Emerson at all. No word list captures those,
which is what the tone model is for.

Putting the first group through an embedding model was a mistake. Measured on the
trained model, adding hedge words to a firm sentence moved the score by 0.023 on
average — inside the noise — and in one case *raised* it. Meanwhile "likely"
slipped through a 0.85 floor in live output. The model cannot see single-word
hedges, and it never needed to: the word is right there.

So this runs first. It is exact, free, and instant, and its feedback names the
offending word rather than describing a vibe.
"""

from __future__ import annotations

import re

# Always a dodge, wherever they appear. Measured across Emerson's own blog these
# are rare (0.1–0.4% of chunks each), so enforcing them strictly costs almost
# nothing in false positives.
STRICT_HEDGES = [
    r"\blikely\b", r"\bprobably\b", r"\bpossibly\b", r"\bperhaps\b", r"\bmaybe\b",
    r"\bmight\b",
    r"\bit depends\b", r"\bresults? (?:may )?var(?:y|ies)\b", r"\bvary from\b",
    r"\bin some cases\b", r"\bfor some people\b", r"\bsome people find\b",
    r"\bhard to say\b", r"\bdifficult to say\b", r"\bno one size fits all\b",
]

# Legitimate when teaching in general, a dodge when they are about this person's
# hair. "Gels may contain moisturising properties" is a fact about gels; "your
# hair may be struggling with buildup" is a refusal to say what is wrong.
#
# These are the common ones in Emerson's blog voice — "may" alone appears in 3.6%
# of chunks — so firing them unconditionally would flag the brand's own writing as
# off-brand. They fire only in a sentence addressed to the reader.
CONTEXTUAL_HEDGES = [
    r"\bmay\b", r"\bcould be\b", r"\btends? to\b",
    r"\bgenerally\b", r"\btypically\b", r"\busually\b",
    r"\bdepends on\b", r"\bdepending on\b", r"\bvaries\b",
]

_ADDRESSES_READER = re.compile(r"\b(?:you|your|you're|youre)\b", re.I)

# Straight from the voice guide's "Never use" list.
BANNED_WORDS = [
    r"\bholy grail\b", r"\bgame changer\b", r"\bgame-changer\b", r"\bobsessed\b",
    r"\bamazing\b", r"\bperfect\b", r"\bmiracle\b",
]

# Straight from the voice guide's "Never say" list.
BANNED_PHRASES = [
    r"\byou need to\b", r"\byou should definitely\b", r"\bthis fixes\b",
    r"\bguaranteed\b", r"\bthe secret is\b", r"\bchanges everything\b",
]

# The most widely recognised marker of machine-written text, and measured in 73%
# of replies before the prompt was changed. Cheap to catch exactly, so there is no
# reason to leave it to the model's discretion.
#
# These used to require whitespace on both sides, which missed the unspaced form
# entirely: both replies in the first repair_first batch went through clean while
# writing "moisture—especially in high porosity hair—the result" and
# "contracting—a cycle called hygral fatigue". Same marker, same clause join, no
# spaces. An em dash is caught wherever it appears; an en dash is left alone
# between digits, because "2–3 days" is a range, not a joined clause.
DASHES = [
    r"—",
    r"(?<!\d)–(?!\d)",
    r"\s--\s",
    r"(?<=[A-Za-z])--(?=[A-Za-z])",
]

# The texture traits the prompt passes as internal context, quoted back with their
# values. The prompt already forbids internal system language, but the model reads
# the profile block aloud when it needs a reason for an action: "with medium
# fragility and high definition difficulty, your hair is struggling to hold
# together". That is a data sheet, not a diagnosis.
#
# Only the label-plus-value form is caught. "Softened to the point of fragility"
# is ordinary English and stays legal, which is why the plain word is not banned.
INTERNAL_LABELS = [
    r"\b(?:low|medium|high)\s+(?:shrinkage|fragility|definition difficulty)\b",
    r"\b(?:shrinkage|fragility|definition difficulty)\s+(?:low|medium|high)\b",
    # "definition difficulty" is deliberately absent here. It always arrives with
    # a value, so the two patterns above catch it, and listing it again reports
    # the same words twice in one violation.
    r"\b(?:shrinkage factor|fragility index|porosity match|decision state|texture traits)\b",
]

_CATEGORIES = {
    "internal_label": (
        INTERNAL_LABELS,
        "reads our internal profile fields back to the customer",
        "Remove {found}. These are our internal labels for her hair, not words she would "
        "recognise. Say what the trait means for her in plain English, or leave it out.",
    ),
    "dash": (
        DASHES,
        "uses dashes to join clauses",
        "Replace {found} with a comma, a colon, or a full stop. If the sentence needs a dash to "
        "hold together, split it into two sentences.",
    ),
    "hedge": (
        STRICT_HEDGES,
        "leaves a claim unresolved",
        "Every qualifier signals a specific cause you have not named yet. Remove {found} "
        "and state the factor directly — \"this comes down to porosity\", not \"this may be "
        "porosity\". End every sentence on a named cause, never an open condition.",
    ),
    "banned_word": (
        BANNED_WORDS,
        "uses banned hype language",
        "Remove {found}. These read as social-media captions and Emerson's voice guide "
        "rules them out. Replace the enthusiasm with a concrete statement of what happens "
        "and why.",
    ),
    "banned_phrase": (
        BANNED_PHRASES,
        "uses banned sales language",
        "Remove {found}. Emerson recommends from expertise, not pressure or promises. "
        "Make the case and let it stand without the guarantee.",
    ),
}


def check(text: str) -> list[dict]:
    """Return every rule violation in `text`, each with the exact words matched.

    Empty list means the text is clean by these rules — which says nothing about
    whether it sounds like Emerson. That question is the tone model's.
    """
    violations = []
    reader_sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if _ADDRESSES_READER.search(s)]

    for name, (patterns, summary, template) in _CATEGORIES.items():
        found = []
        for pattern in patterns:
            found.extend(match.group(0) for match in re.finditer(pattern, text, flags=re.I))

        if name == "hedge":
            # Soft hedges only count where the sentence is about the reader.
            for pattern in CONTEXTUAL_HEDGES:
                for sentence in reader_sentences:
                    found.extend(m.group(0) for m in re.finditer(pattern, sentence, flags=re.I))

        if found:
            unique = sorted({f.lower() for f in found})
            quoted = ", ".join(f'"{f}"' for f in unique)
            violations.append({
                "category": name,
                "summary": summary,
                "found": unique,
                "guidance": template.format(found=quoted),
            })
    return violations


def guidance(violations: list[dict]) -> str:
    """Combine violations into one instruction for a retry prompt."""
    return "\n".join(v["guidance"] for v in violations)
