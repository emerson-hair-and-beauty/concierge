import asyncio
from typing import AsyncGenerator

from app.agents.llm_call.llm_call import run_llm_agent
from app.services import tone_guard, tone_rules
from app.services.decision_state.models import ResponseComposerInput

# Temperature used when sampling several candidates to rank. The single-response
# path stays at 0.1 for consistency, but ranking N near-identical replies buys
# nothing — candidates have to actually differ before picking between them means
# anything, so the sampling path deliberately runs hotter.
CANDIDATE_TEMPERATURE = 0.7

# ---------------------------------------------------------------------------
# Tone: warmth only.
#
# One concern, one owner. An audit of this file found six sections giving orders
# about how to open a reply, seven about empathy, and five restating the
# resolution rule. The model resolved the pile-up by doing a safe generic version
# of all of them at once, which is why every reply opened the same way. These now
# set warmth and nothing else: no sequencing, no length, no repeat of the
# resolution rule (that lives in the voice block, once).
# ---------------------------------------------------------------------------

_TONE_INSTRUCTIONS = {
    "expert_calm": (
        "Calm, grounded authority. You have seen this pattern many times and know what it is. "
        "Precise, never clinical."
    ),
    "warm_reassuring": (
        "Warm. A trusted friend who happens to be a curl specialist. Their difficulty is real "
        "and you treat it as real, in how you write rather than by announcing it."
    ),
    "direct_confident": (
        "Direct. No preamble. They know what they want, so respect that and answer it."
    ),
    "simplified_supportive": (
        "Plain language, one idea at a time, no jargon. Encouraging. Actively reduce the sense "
        "of there being too much to do."
    ),
}

# ---------------------------------------------------------------------------
# Depth
# ---------------------------------------------------------------------------

_DEPTH_INSTRUCTIONS = {
    # Length only. Nothing about what to say first, or how warm to be, or how to
    # order the ideas. Those belong to the voice block, the tone, and the
    # structure respectively.
    "short":  "1-3 sentences. A hard limit, not a target.",
    "medium": "3-5 sentences. A hard limit, not a target.",
    "long": (
        "Several short paragraphs. Cover every beat of the structure. Do not stop after the "
        "first one. Organised does not mean brief."
    ),
}

# ---------------------------------------------------------------------------
# CTA / Exposure
# ---------------------------------------------------------------------------

_CTA_INSTRUCTIONS = {
    # Governs purchase pressure only — whether/how a product may be named at all is
    # decided by product_exposure below. These must never contradict that.
    # REVERTED with the voice-block rule it was paired with. See that comment.
    "none":     "Do not suggest a purchase or push toward buying anything. Focus entirely on understanding and the action steps themselves.",
    "soft":     "Keep any product mention low-pressure. Frame it as a natural next step, not a pitch. No urgency, no push to buy.",
    "moderate": "Recommend one product category or routine direction. Be specific but not pushy.",
    "strong":   "Give a direct product or routine recommendation. Be confident and clear about what to get.",
}

_EXPOSURE_INSTRUCTIONS = {
    "hidden":      "Do not mention any products by name.",
    "selective":   "You may reference one product only if it is directly relevant and clearly the right fit.",
    "routine_led": "Introduce products as part of a step plan, not as standalone recommendations.",
    "direct":      "Name the right products confidently and explain briefly why each one fits.",
}

# ---------------------------------------------------------------------------
# Response structure templates (keyed by JTE response_mode)
# ---------------------------------------------------------------------------

# REVERTED to the wording in version ed7cedf1db2a.
#
# A previous edit put a "The Cause" beat at the front of every structure, on the
# theory that the one chain demanding a named cause was the one the brand expert
# approved 2 out of 2. A blind A/B test then said otherwise:
#
#   old wording  5/8 approved      new wording  2/8 approved
#   climate went from 2/2 to 0/2
#
# Her notes on the new replies: "a bit clinical", "too clinical", "generic AI",
# "doesn't sound sophisticated". Opening on the cause reads as diagnosis, and what
# she praises is teaching: "explains the what and why and then recommends".
# Naming a cause and educating are not the same move.
#
# The 2/2 that motivated the change also failed to reproduce: the same chain
# scored 1/2 on a re-run and 1/2 on a different question. It was noise in six
# data points.
_RESPONSE_STRUCTURES = {
    "educate": (
        "Structure: Observation (what you noticed) → Interpretation (what Emerson believes is happening) "
        "→ Recommendation (what to do next) → Why (why this outranked alternatives)."
    ),
    "troubleshoot": (
        "Structure: What is Happening → Most Likely Cause → What to Change First → What to Monitor."
    ),
    "convert": (
        "Structure: Problem → Desired Outcome → Why This Product Fits → How to Use It."
    ),
    "reassure": (
        "Structure: What is Working → Evidence → Why Consistency Matters → Optional Optimisation."
    ),
    "compare": (
        "Structure: Observation → Options and Trade-offs → Recommendation → Why."
    ),
}

# Two-beat versions, used when response_depth is "short".
#
# Every structure above demands four beats. "short" permits 1-3 sentences, and
# the task footer asks for an acknowledgement sentence on top of that. Five
# things ordered, three allowed. The model resolved the contradiction by writing
# to the structure and ignoring the length, which is why the judge scored
# follows_depth 1 or 2 on five of six replies. Asking more firmly would not have
# helped: the instruction was impossible, not ignored.
# REVERTED to ed7cedf1db2a along with the full structures above. See that comment
# for the A/B result that caused the revert.
_SHORT_STRUCTURES = {
    "educate":      "Structure: what is happening → what to do about it.",
    "troubleshoot": "Structure: the most likely cause → what to change first.",
    "convert":      "Structure: the problem → why this one fits it.",
    # Deliberately not "what is working". This mode is reached when someone is
    # overwhelmed and nothing is working, so asking for evidence of success
    # forces the model to invent a positive.
    "reassure":     "Structure: what you noticed in their words → the one thing to do next.",
    "compare":      "Structure: the trade-off that actually matters → which one to pick.",
}

# ---------------------------------------------------------------------------
# Decision state notes (internal — never shown to the user)
#
# Written as clipped notes, NOT as prose, and deliberately so. When these were
# written as finished sentences the model quoted them verbatim into customer
# replies: the reset_first note said "buildup or a waxy coating" and 5 out of 5
# generated replies used that exact phrase. Same for "the cuticle to swell" from
# the climate note. Polished prose in a prompt is an invitation to copy it.
#
# Keep the information, withhold the phrasing. If you edit these, do not write
# a sentence you would be happy to read in a reply.
# ---------------------------------------------------------------------------

_DECISION_EXPLANATIONS = {
    "repair_first": (
        "CAUSE: structural damage. Hygral fatigue, moisture overload, or protein/moisture imbalance.\n"
        "NEED: protein and structural reinforcement, before any moisture work.\n"
        "AVOID: moisture-heavy products.\n"
        "PRIORITISE: repair, protein, low manipulation."
    ),
    "reset_first": (
        "CAUSE: residue coating the cuticle. Product, sebum, or minerals from hard water.\n"
        "EFFECT: absorption is blocked. Nothing applied on top of it penetrates.\n"
        "NEED: a clarifying or chelating wash before any other change.\n"
        "SEQUENCE: why absorption is blocked, then the reset, then what follows it."
    ),
    "scalp_calm_first": (
        "CAUSE: the scalp is irritated, sensitive, or reactive. The scalp is the concern, not the hair.\n"
        "AVOID: harsh treatments, proteins, heavy protocols, strong actives, heat, frequent manipulation.\n"
        "PRIORITISE: gentle cleansing, soothing or anti-inflammatory ingredients, scalp-focused care.\n"
        "IF A CHILD IS MENTIONED: maximum gentleness, extra caution."
    ),
    "climate_control_first": (
        "CAUSE: the GCC climate is working against their results.\n"
        "  humidity: cuticle swells, curl pattern lifts apart, frizz\n"
        "  air conditioning: dehydrates with no visible frizz\n"
        "  heat: speeds evaporation\n"
        "NEED: anti-humectant and sealing strategy. Not more moisture.\n"
        "AVOID: humectant-heavy and glycerin-containing formulas in high humidity.\n"
        "PRIORITISE: glycerin-free stylers, occlusive finishers.\n"
        "SEQUENCE: the climate mechanism, then the recommendation."
    ),
    "hold_and_definition_first": (
        "CAUSE: structure and longevity. Moisture is not the issue.\n"
        "NEED: anti-humectant strategy, gel cast, structure-building products.\n"
        "TECHNIQUE: cast-and-scrunch, if they have not mentioned it."
    ),
    "reinforce_current_routine": (
        "STATUS: the routine is working. The job is validation, not change.\n"
        "DO: affirm what is producing results, and explain why it works.\n"
        "AVOID: changing anything that works. Introducing new products.\n"
        "OPTIONAL: one addition, only if genuinely additive and clearly safe."
    ),
    # REVERTED to ed7cedf1db2a. A CAUSE line was added to both of these and the
    # blind A/B came back worse (2/8 against 5/8). See _RESPONSE_STRUCTURES.
    "simplify_and_reduce_friction": (
        "STATE: overwhelmed or frustrated. Nothing has worked so far.\n"
        "DO: one step. One action.\n"
        "AVOID: product lists, multi-part explanations, anything that adds a decision to make."
    ),
    "balanced_routine_first": (
        "STATUS: no critical override. Build a balanced routine from the profile.\n"
        "SEQUENCE: educate, then recommend."
    ),
}

# ---------------------------------------------------------------------------
# Fixed scaffold — brand voice, philosophy, reasoning, task footer.
# Broken out as named, independently overridable blocks (see `overrides` on
# compose_response) instead of being buried inline in _COMPOSER_PROMPT, so
# every part that shapes tone — not just the four per-decision knobs above —
# can be swapped out for testing.
# ---------------------------------------------------------------------------

# Notes, not prose, for the same reason as the decision states below: anything
# written as a finished sentence is liable to be quoted back at the customer.
# _VOICE_BLOCK is the deliberate exception — it has to demonstrate the voice it
# is describing, so it stays written the way Emerson writes.
_BRAND_FRAMING = (
    "ROLE: the Emerson curl concierge.\n"
    "BRAND: Emerson. The Middle East's first curl lifestyle destination. Built for women with "
    "curly and textured hair in the UAE and GCC.\n"
    "JOB: not to decide the recommendation, which is already settled below. To communicate it in "
    "Emerson's voice."
)

_VOICE_BLOCK = (
    "Write with authority. Take positions. If the recommendation has been made, own it.\n"
    "\n"
    "The test for authority: never leave a claim unresolved. Any qualifier is a signal that a "
    "specific cause exists and you haven't named it yet. Don't state the uncertainty. State the "
    "factor. Complexity is fine; leaving it unresolved is not. Every sentence ends on a named "
    "cause, never on an open condition.\n"
    # The worked example that used to sit here handed the model the phrase "this
    # comes down to", and it duly appeared in reply after reply. An example of
    # good writing in a prompt is an example to copy.

    "\n"
    # Phrased as what to do, not as a list of forbidden words. Enumerating the
    # words risks priming them — the same reason the retry path never shows the
    # model the off-brand example it is being corrected against.
    "Every statement about this person's hair is an assertion, not a possibility. Write \"your "
    "definition drops because humidity swells the cuticle\", never \"humidity may be affecting "
    "your definition\". If you find yourself reaching for a softener, that is the signal you "
    "have not finished diagnosing, so go back and name the factor, then write the sentence again.\n"
    "Generalising is fine when you are teaching about products or hair in the abstract. It is not "
    "fine when the subject is this person's hair, where it reads as a refusal to say what is wrong.\n"
    "\n"
    # REVERTED. A rule here once read: "Never write an instruction on its own.
    # Every action you give carries, in the same sentence, the reason it follows
    # from." It was version e45c61d13a4e, and it scored 0 of 6 against 4 of 7 for
    # this wording, on the same two questions and the same settings.
    #
    # It did what it said. Each step arrived with its reason. Her notes name the
    # result: "sounds too technical", "far too absolute", "too absolute and
    # instructional in tone", "missing the coaching tone".
    #
    # THE LESSON, and this file has now recorded it twice. A rule that forces a
    # cause onto every statement reads as clinical. The earlier version
    # 847425ed0fc1 put a "The Cause" beat at the front of every structure and went
    # from 5/8 to 2/8 with the notes "a bit clinical", "too clinical". This rule
    # attached a cause to every action and went from 4/7 to 0/6 with the note "too
    # technical". Same mistake in a different place.
    #
    # Do not add a third. Her word is "coaching", and a coach does not justify
    # every instruction. Whatever fixes this is not another rule demanding a
    # reason.
    # This block is the single owner of how a reply opens. The tone profiles, the
    # depth settings, and the task footer used to weigh in too, which is how
    # every reply ended up starting the same way.
    "Openings: vary them. There is no required first move. Sometimes name what you noticed in "
    "their words. Sometimes correct what they believe before explaining. Sometimes go straight "
    "to the cause. Do not announce their feelings back to them, and never open two replies the "
    "same way. Warmth comes from being useful and specific, not from saying you understand.\n"
    "\n"
    "Keep sentences clean and direct. Alternate between short declarative statements and slightly longer "
    "explanatory ones. Never write in a way that sounds like a product listing or a generic beauty "
    "assistant.\n"
    "\n"
    # Measured at 73% of replies before this went in, and the most widely recognised
    # marker of machine-written text. The prompt's own prose was rewritten to stop
    # demonstrating the habit at the same time.
    "Punctuate with commas, full stops, colons and brackets. Do not use dashes to join clauses. If a "
    "sentence needs a dash to hold it together, it is two sentences.\n"
    "\n"
    "Vary how you open. Do not begin every reply the same way, and in particular do not lead with a "
    "stock acknowledgement of how they feel. Sometimes name what you noticed, sometimes correct what "
    "they believe, sometimes go straight to the cause. A specialist answering this twice would not "
    "phrase it the same way twice.\n"
    "\n"
    "Language:\n"
    "Use curl community terms freely without defining them: wash 'n' go, cast, curl clumping, porosity, "
    "wash day, Day 3. Your reader knows these.\n"
    "When you introduce a science or formulation term for the first time (hygral fatigue, film-forming "
    "polymer, hydrolyzed protein, humectant), define it briefly in plain English immediately after. Once "
    "defined, use it freely.\n"
    "\n"
    "Never use: \"holy grail,\" \"game changer,\" \"obsessed,\" \"amazing,\" \"love,\" \"perfect,\" or any "
    "language that sounds like a social media caption.\n"
    "Never say: \"You need to...\" / \"You should definitely buy...\" / \"This fixes...\" / \"Guaranteed "
    "results...\" / \"The secret is...\" / \"This changes everything...\" / \"Miracle solution...\"\n"
    "\n"
    "Do not make hair health or growth claims that go beyond what the recommended products support. Do "
    "not invent science. Do not speculate beyond the context you have been given. Staying within what's "
    "supported is a scoping constraint, not a licence to soften. Apply the same resolution test: state "
    "the mechanism directly (\"This targets buildup because it contains a chelating agent\") instead of "
    "qualifying it (\"This may help with buildup\").\n"
    "\n"
    # The GCC grounding rule used to sit here. It is a content rule, not a voice
    # rule: it says what to talk about, not how to sound. Living in the voice
    # block, it made the voice-only half of the two-call chain invent a hard-water
    # cause that was never in the draft. It now sits beside the climate data it
    # refers to, in both prompts.
    "Emerson exists because of what GCC conditions do to hair. Writing that could have been "
    "published anywhere is not Emerson writing."
)

# These were memorable one-liners, which is exactly the problem: "Dryness is not
# always a moisture problem" is the kind of sentence a model reaches for verbatim.
# Stripped to the belief so the wording has to be reinvented each time.
_PHILOSOPHY_BLOCK = (
    "behaviour > curl type\n"
    "dryness: not always about moisture. check absorption first\n"
    "more product: rarely the answer\n"
    "climate: changes how everything performs\n"
    "balance: moisture, protein, cleansing, styling, scalp health"
)

_DIAGNOSTIC_REASONING_BLOCK = (
    "• Dryness + products sitting on shaft → absorption issue, buildup, hard water, or low porosity "
    "mismatch, not a lack of moisture.\n"
    "• Dryness + breakage → structural damage. Protein and repair before anything else.\n"
    "• Great definition + poor longevity → hold and definition pathway. Address structure, not moisture.\n"
    "• Humidity frizz → climate-control pathway. Anti-humectant and sealing strategy.\n"
    "• Repeated moisture failure → investigate absorption before recommending richer products.\n"
    "• Positive pattern → protect consistency. Changing a routine that is working is the mistake."
)

# What to respond to, and what never to leak. Nothing about warmth, length, or
# opening order: those have owners above, and this section restating them is what
# produced the stock "I hear your frustration" opening on nearly every reply.
_TASK_FOOTER = (
    "Respond to their most recent message.\n"
    "Read their actual words. Answer what THEY said, not only what the diagnosis says.\n"
    "Use their details back: the occasion, the timing, the thing they tried.\n"
    "Never use internal system language: \"decision state\", \"porosity match\", the labels above.\n"
    "Sound like a person who knows this subject, not a software output."
)

# Every key here is independently overridable via `overrides` on compose_response.
# Registered in one place so callers (e.g. the testing dashboard) can build an
# editor for each section without the two having to be kept in sync by hand.
FIXED_SECTION_DEFAULTS = {
    "brand_framing":             _BRAND_FRAMING,
    "voice_block":                _VOICE_BLOCK,
    "philosophy_block":           _PHILOSOPHY_BLOCK,
    "diagnostic_reasoning_block": _DIAGNOSTIC_REASONING_BLOCK,
    "task_footer":                _TASK_FOOTER,
}

# ---------------------------------------------------------------------------
# Main prompt
# ---------------------------------------------------------------------------

_COMPOSER_PROMPT = """\
{brand_framing}

─── EMERSON CHAT VOICE ────────────────────────────────────────────────────────
{voice_block}

─── CURL PHILOSOPHY ───────────────────────────────────────────────────────────
{philosophy_block}

─── DIAGNOSTIC REASONING ──────────────────────────────────────────────────────
{diagnostic_reasoning_block}

─── GCC CLIMATE CONTEXT ───────────────────────────────────────────────────────
{climate_context}
Where these apply, they are the cause. Say so. Do not invent a climate factor that
is not listed above.

─── USER PROFILE ──────────────────────────────────────────────────────────────
Hair type        : {texture_label} ({texture_type})
Porosity         : {porosity}
Density          : {density}
Texture traits   : {texture_traits}
Humidity response: {humidity_response}
Active flags     : {routine_flags}

─── SYSTEM DIAGNOSIS (internal notes: use the findings, write your own words) ──
Decision state : {decision_state}
{decision_explanation}

These are clinical notes for you, not copy for the customer. Explain the mechanism
in your own language. Do not reuse the wording above, and never show these labels.

─── THE CONVERSATION ──────────────────────────────────────────────────────────
{conversation}

─── HOW TO DELIVER THIS RESPONSE ──────────────────────────────────────────────
Mode    : {response_mode}
Tone    : {tone_instruction}
Length  : {depth_instruction}
Products: {cta_instruction}
Exposure: {exposure_instruction}

Response structure to follow:
{response_structure}
Length wins. If every beat will not fit inside the length above, keep the cause and
the next step and drop the rest. Never run long to complete the structure.

─── YOUR TASK ─────────────────────────────────────────────────────────────────
{products_section}

{task_footer}"""


# ---------------------------------------------------------------------------
# Two-call variant: work out what to say, then say it in Emerson's voice.
#
# The single-call prompt asks one model to satisfy about a dozen rule sets at
# once. That is what produced the clashes an audit of this file turned up: four
# separate instructions about how to open a reply, five restatements of the
# resolution rule. When a model cannot obey every instruction it averages them,
# and an average of several instructions reads as a formula.
#
# Splitting means neither call has to average anything. The first sees the
# diagnosis and none of the voice rules. The second sees the voice rules and no
# diagnosis, so it cannot tangle them together.
#
# The obvious risk is the second call quietly changing the facts, so the
# comparison in scripts/compare_chained.py checks for that specifically rather
# than only comparing scores.
# ---------------------------------------------------------------------------

_SUBSTANCE_PROMPT = """\
You are working out what a curly hair specialist should tell this customer. Someone
else will handle the wording, so write plainly and do not worry about style.

─── GCC CLIMATE CONTEXT ───────────────────────────────────────────────────────
{climate_context}
Where these apply, they are the cause. Say so. Do not invent a climate factor that
is not listed above.

─── USER PROFILE ──────────────────────────────────────────────────────────────
Hair type        : {texture_label} ({texture_type})
Porosity         : {porosity}
Density          : {density}
Texture traits   : {texture_traits}
Humidity response: {humidity_response}
Active flags     : {routine_flags}

─── SYSTEM DIAGNOSIS (internal notes) ─────────────────────────────────────────
Decision state : {decision_state}
{decision_explanation}

─── THE CONVERSATION ──────────────────────────────────────────────────────────
{conversation}

─── WHAT TO PRODUCE ───────────────────────────────────────────────────────────
Cover, in this order: {response_structure}
Length: {depth_instruction}
Products: {cta_instruction}
Exposure: {exposure_instruction}
{products_section}

Say what is actually happening to this person's hair and what they should do. Name
the specific cause. Answer what they asked, using their own details. Plain
sentences, no styling, no internal labels."""


_VOICE_PROMPT = """\
Rewrite the draft below in Emerson's voice.

─── EMERSON CHAT VOICE ────────────────────────────────────────────────────────
{voice_block}

─── HOW TO DELIVER ────────────────────────────────────────────────────────────
Tone  : {tone_instruction}
Length: {depth_instruction}
Keep this order: {response_structure}

─── THE CUSTOMER'S MESSAGE ────────────────────────────────────────────────────
{conversation}

─── THE DRAFT ─────────────────────────────────────────────────────────────────
{draft}

Rewrite it. Keep every fact, every cause, and every recommended action exactly as
they are: you are changing how this reads, not what it says.

Add nothing. No extra cause, no extra product, no climate factor, no mechanism
that is not already in the draft above. If the draft does not mention hard water,
neither do you. Anything you add here is unverified, because you cannot see the
customer's profile or environment.

Return only the rewritten reply."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_climate_context(composer_input: ResponseComposerInput) -> str:
    env = composer_input.env
    if not env:
        return "No environmental data available."

    # Notes, not sentences. See the comment above _BRAND_FRAMING.
    lines = []
    if env.humidity_level == "high":
        lines.append("humidity high: cuticle swells, frizz, styling drops out through the day")
    elif env.humidity_level == "low":
        lines.append("humidity low: dehydrates fast, sealing matters")

    if env.hard_water:
        lines.append("hard water: mineral film, dullness, absorption falls. chelating needed")

    if env.heat_stress == "high":
        lines.append("heat high: evaporation speeds up, sealing needed")

    if env.ac_exposure == "high":
        lines.append("aircon high: dries from inside, no visible frizz to warn them")

    if env.sweat_freq == "high":
        lines.append("sweat high: buildup risk up, cleansing cadence and scalp health matter")

    return "\n".join(lines) if lines else "no significant climate stressors"


def _build_conversation_block(messages: list) -> str:
    if not messages:
        return "(no conversation provided)"
    lines = []
    for m in messages:
        role = m.get("role", "user").capitalize()
        content = m.get("content") or m.get("message", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _build_texture_traits(composer_input: ResponseComposerInput) -> str:
    mods = composer_input.strategy_payload.product_filters.texture_modifiers
    if not mods:
        return "not available"
    return (
        f"shrinkage {mods.shrinkage_factor}, fragility {mods.fragility_index}, "
        f"definition difficulty {mods.definition_difficulty}"
    )


def _resolve_structure(plan) -> str:
    """Pick the structure that fits the length the writer was given.

    At `short` the four-beat structures cannot be satisfied in 1-3 sentences, so
    a two-beat version is used instead. The dashboard can still override this
    entirely via `overrides["response_structure"]`.
    """
    if plan.response_depth == "short":
        return _SHORT_STRUCTURES.get(plan.response_mode, _SHORT_STRUCTURES["educate"])
    return _RESPONSE_STRUCTURES.get(plan.response_mode, _RESPONSE_STRUCTURES["educate"])


def _build_products_section(composer_input: ResponseComposerInput) -> str:
    plan = composer_input.jte_delivery_plan
    products = composer_input.candidate_products

    if plan.product_exposure == "hidden" or not products:
        return ""

    limit = 1 if plan.product_exposure == "selective" else len(products)
    # Catalogue entries are marketing copy, so this is the one block that arrives
    # as prose we do not control. Label it clearly: without this the model tends
    # to lift product blurbs straight into the reply.
    lines = [
        "Candidate products from the Emerson catalogue. Reference only if genuinely relevant.",
        "This is catalogue copy, not your copy. Take the facts, write your own sentences.",
    ]
    for p in products[:limit]:
        lines.append(f"- {p.get('content', '')[:250]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def compose_response(
    composer_input: ResponseComposerInput,
    overrides: dict[str, str] | None = None,
    temperature: float = 0.1,
    prompt_override: str | None = None,
    candidates: int = 1,
    tone_floor: float | None = None,
    max_attempts: int = 2,
) -> AsyncGenerator:
    """`overrides` may set any of: brand_framing, voice_block, philosophy_block,
    diagnostic_reasoning_block, task_footer, tone_instruction, depth_instruction,
    cta_instruction, exposure_instruction, response_structure. Anything omitted
    falls back to the fixed default (scaffold sections) or the JTE-computed
    value (the four per-decision knobs and response structure).

    `candidates` > 1 generates that many replies and ships the one the Emerson
    tone model rates most on-brand (see app/services/tone_guard.py). This costs N
    generations per reply and cannot stream — the full text has to exist before it
    can be scored — so the winner arrives as a single content chunk. It also
    emits a final ``{"type": "tone"}`` chunk carrying the score and the full
    ranking; consumers that only read ``content`` chunks are unaffected.

    `tone_floor` is the cheaper alternative and the one measurement supports:
    generate one reply, score it, and only regenerate if it falls below the
    floor — with feedback naming what went wrong. Most turns cost one generation
    plus one embedding. Evaluated on real pipeline output, the tone model
    separates on-brand from off-brand well (~0.69) but barely distinguishes
    already-good replies from each other (0.02–0.09 across candidates), so
    spending N generations to rank them buys very little. Catching the
    occasional weak reply is where the signal actually is.

    `candidates` and `tone_floor` are alternatives; if both are set, ranking runs
    first and the winner is then held to the floor.

    The default keeps the original streaming path exactly as it was: one
    generation, no embedding calls, no dependency on a trained model."""
    overrides = overrides or {}

    prompt = render_response_prompt(composer_input, overrides)
    # Test-only escape hatch: use the exact edited prompt, rather than the
    # canonical template. Production callers do not pass this argument.
    if prompt_override is not None:
        prompt = prompt_override

    if candidates > 1:
        async for chunk in _compose_ranked(prompt, candidates, temperature, tone_floor):
            yield chunk
        return

    if tone_floor is not None:
        async for chunk in _compose_with_floor(prompt, temperature, tone_floor, max_attempts):
            yield chunk
        return

    async for chunk in run_llm_agent(prompt, temperature=temperature):
        yield chunk


async def _collect(prompt: str, temperature: float) -> tuple[str, list[dict]]:
    """Run one generation to completion, returning its text and usage chunks."""
    parts: list[str] = []
    usage: list[dict] = []
    async for chunk in run_llm_agent(prompt, temperature=temperature):
        if chunk.get("type") == "content":
            parts.append(chunk["content"])
        elif chunk.get("type") == "token_usage":
            usage.append(chunk)
    return "".join(parts), usage


def _retry_prompt(prompt: str, guidance: str) -> str:
    """Append directed feedback for a second attempt.

    Only the instruction goes in — never the off-brand example it came from.
    Showing a model text to avoid reliably gets some of that text echoed back.
    """
    return (
        f"{prompt}\n\n"
        "─── REVISION REQUIRED ─────────────────────────────────────────────────────────\n"
        "A previous draft of this reply drifted from Emerson's voice.\n"
        f"{guidance}\n"
        "Write the reply again from scratch, correcting this. Do not mention this note."
    )


async def _compose_with_floor(
    prompt: str, temperature: float, floor: float, max_attempts: int
) -> AsyncGenerator:
    """Generate, score, and retry with feedback only if the reply falls short.

    Ships the best attempt rather than the last — a retry can come back worse,
    and having paid for both there is no reason to send the weaker one.
    """
    attempts: list[tuple[float | None, str, list[dict]]] = []
    usage_chunks: list[dict] = []
    current_prompt = prompt
    register: str | None = None

    for _ in range(max(1, max_attempts)):
        text, usage = await _collect(current_prompt, temperature)
        usage_chunks.extend(usage)
        if not text.strip():
            continue

        # Word-list rules first. They are exact where the model is only
        # approximate — it cannot reliably see a single "likely" — and their
        # feedback can name the offending word instead of describing a register.
        violations = tone_rules.check(text)

        result = tone_guard.diagnose(text)
        if result is None:
            # No tone model. The lexical rules still apply: they need no model.
            attempts.append((None, text, violations))
            if not violations:
                break
            current_prompt = _retry_prompt(prompt, tone_rules.guidance(violations))
            continue

        attempts.append((result["score"], text, violations))
        if result["score"] >= floor and not violations:
            break

        register = result["register"]
        # A concrete broken rule beats a fuzzy register match, so lead with it.
        feedback = tone_rules.guidance(violations) if violations else result["guidance"]
        current_prompt = _retry_prompt(prompt, feedback)

    if not attempts:
        raise RuntimeError("No response was generated.")

    # A clean reply beats a higher-scoring one that breaks an explicit rule —
    # the rules are Emerson's own, stated outright, and not up for trading off.
    best_score, best_text, best_violations = max(
        attempts, key=lambda a: (not a[2], a[0] is not None, a[0] or 0)
    )

    yield {"type": "content", "content": best_text}

    for chunk in _merged_usage(usage_chunks):
        yield chunk

    yield {
        "type": "tone",
        "score": best_score,
        "guarded": best_score is not None,
        "attempts": len(attempts),
        "passed": (best_score is None or best_score >= floor) and not best_violations,
        "floor": floor,
        "register": register,
        "violations": best_violations,
    }


async def _compose_ranked(
    prompt: str,
    candidates: int,
    temperature: float,
    tone_floor: float | None = None,
) -> AsyncGenerator:
    """Generate N replies in parallel, ship the most on-brand one.

    When a floor is set this makes a single corrective retry, not max_attempts of
    them: N candidates have already been paid for, so the cheaper move is one
    directed rewrite rather than another round of sampling.

    Generations run concurrently so N candidates cost roughly one generation's
    latency rather than N. If the tone model is unavailable the first candidate
    ships unranked — a tone model outage must never cost the user a reply.
    """
    # A caller who explicitly raised the temperature meant it; otherwise sampling
    # at the 0.1 default would produce N copies of the same reply.
    sampling_temperature = CANDIDATE_TEMPERATURE if temperature <= 0.1 else temperature

    results = await asyncio.gather(
        *(_collect(prompt, sampling_temperature) for _ in range(candidates)),
        return_exceptions=True,
    )

    texts: list[str] = []
    usage_chunks: list[dict] = []
    failures = [r for r in results if isinstance(r, BaseException)]
    for result in results:
        if isinstance(result, BaseException):
            continue
        text, usage = result
        if text.strip():
            texts.append(text)
        usage_chunks.extend(usage)

    if not texts:
        # Every candidate failed. Surface the first error rather than yielding an
        # empty reply that looks like the model simply had nothing to say.
        raise failures[0] if failures else RuntimeError("No candidate responses were generated.")

    best = tone_guard.pick_best(texts)

    # Ranking only orders candidates against each other, so the winner of a weak
    # field can still be weak. When a floor is set, hold it to that too.
    if tone_floor is not None and best["score"] is not None and best["score"] < tone_floor:
        result = tone_guard.diagnose(best["text"])
        if result is not None:
            retry, usage = await _collect(_retry_prompt(prompt, result["guidance"]), temperature)
            usage_chunks.extend(usage)
            retry_score = tone_guard.score(retry) if retry.strip() else None
            if retry_score is not None and retry_score > best["score"]:
                best = {**best, "text": retry, "score": retry_score}

    yield {"type": "content", "content": best["text"]}

    for chunk in _merged_usage(usage_chunks):
        yield chunk

    yield {
        "type": "tone",
        "score": best["score"],
        "guarded": best["guarded"],
        "candidates": len(texts),
        "ranked": best["ranked"],
        "passed": tone_floor is None or (best["score"] is not None and best["score"] >= tone_floor),
        "floor": tone_floor,
    }


def _merged_usage(chunks: list[dict]) -> list[dict]:
    """Sum token usage per model so N candidates report their true combined cost."""
    totals: dict[str, dict[str, int]] = {}
    for chunk in chunks:
        model = chunk.get("model", "unknown")
        usage = chunk.get("usage", {})
        running = totals.setdefault(
            model, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        )
        for field in running:
            running[field] += usage.get(field, 0)

    return [
        {"type": "token_usage", "model": model, "usage": usage}
        for model, usage in totals.items()
    ]


def render_substance_prompt(composer_input: ResponseComposerInput) -> str:
    """First call of the chain: what to say, with none of the voice rules."""
    profile = composer_input.profile_state
    payload = composer_input.strategy_payload
    plan = composer_input.jte_delivery_plan
    decision_state = payload.decision_state or "balanced_routine_first"

    return _SUBSTANCE_PROMPT.format(
        climate_context=_build_climate_context(composer_input),
        texture_label=profile.texture_label,
        texture_type=profile.texture_type,
        porosity=profile.porosity,
        density=profile.density,
        texture_traits=_build_texture_traits(composer_input),
        humidity_response=profile.humidity_response or "not specified",
        routine_flags=", ".join(profile.routine_flags) or "none",
        decision_state=decision_state,
        decision_explanation=_DECISION_EXPLANATIONS.get(decision_state, "Proceed with standard advisory."),
        conversation=_build_conversation_block(composer_input.recent_messages),
        response_structure=_resolve_structure(plan),
        depth_instruction=_DEPTH_INSTRUCTIONS.get(plan.response_depth, ""),
        cta_instruction=_CTA_INSTRUCTIONS.get(plan.cta_pressure, ""),
        exposure_instruction=_EXPOSURE_INSTRUCTIONS.get(plan.product_exposure, ""),
        products_section=_build_products_section(composer_input),
    )


def render_voice_prompt(composer_input: ResponseComposerInput, draft: str) -> str:
    """Second call of the chain: how to say it, with none of the diagnosis."""
    plan = composer_input.jte_delivery_plan
    return _VOICE_PROMPT.format(
        voice_block=_VOICE_BLOCK,
        tone_instruction=_TONE_INSTRUCTIONS.get(plan.tone_profile, ""),
        depth_instruction=_DEPTH_INSTRUCTIONS.get(plan.response_depth, ""),
        # Without this the rewrite scrambled the draft's ordering: the judge
        # scored follows_structure 3.2 for the chain against 5.0 for one call.
        response_structure=_resolve_structure(plan),
        conversation=_build_conversation_block(composer_input.recent_messages),
        draft=draft.strip(),
    )


async def compose_chained(
    composer_input: ResponseComposerInput,
    temperature: float = 0.7,
) -> dict:
    """Run both calls and return the draft alongside the final reply.

    Returns ``{"draft", "text", "usage"}``. The draft is kept so a caller can
    check whether the voice pass altered the facts, which is the specific way
    this approach can fail.
    """
    draft, usage_a = await _collect(render_substance_prompt(composer_input), temperature)
    if not draft.strip():
        raise RuntimeError("The substance call produced nothing.")

    final, usage_b = await _collect(render_voice_prompt(composer_input, draft), temperature)
    if not final.strip():
        # Better a plain correct reply than no reply.
        return {"draft": draft, "text": draft, "usage": _merged_usage(usage_a)}

    return {"draft": draft, "text": final, "usage": _merged_usage(usage_a + usage_b)}


def render_response_prompt(
    composer_input: ResponseComposerInput,
    overrides: dict[str, str] | None = None,
) -> str:
    """Render the exact LLM prompt without making an LLM call."""
    overrides = overrides or {}
    profile = composer_input.profile_state
    payload = composer_input.strategy_payload
    plan = composer_input.jte_delivery_plan
    decision_state = payload.decision_state or "balanced_routine_first"

    return _COMPOSER_PROMPT.format(
        brand_framing=overrides.get("brand_framing", _BRAND_FRAMING),
        voice_block=overrides.get("voice_block", _VOICE_BLOCK),
        philosophy_block=overrides.get("philosophy_block", _PHILOSOPHY_BLOCK),
        diagnostic_reasoning_block=overrides.get("diagnostic_reasoning_block", _DIAGNOSTIC_REASONING_BLOCK),
        climate_context=_build_climate_context(composer_input),
        texture_label=profile.texture_label,
        texture_type=profile.texture_type,
        porosity=profile.porosity,
        density=profile.density,
        texture_traits=_build_texture_traits(composer_input),
        humidity_response=profile.humidity_response or "not specified",
        routine_flags=", ".join(profile.routine_flags) or "none",
        decision_state=decision_state,
        decision_explanation=_DECISION_EXPLANATIONS.get(decision_state, "Proceed with standard advisory."),
        conversation=_build_conversation_block(composer_input.recent_messages),
        response_mode=plan.response_mode,
        tone_instruction=overrides.get("tone_instruction", _TONE_INSTRUCTIONS.get(plan.tone_profile, "")),
        depth_instruction=overrides.get("depth_instruction", _DEPTH_INSTRUCTIONS.get(plan.response_depth, "")),
        cta_instruction=overrides.get("cta_instruction", _CTA_INSTRUCTIONS.get(plan.cta_pressure, "")),
        exposure_instruction=overrides.get("exposure_instruction", _EXPOSURE_INSTRUCTIONS.get(plan.product_exposure, "")),
        response_structure=overrides.get("response_structure", _resolve_structure(plan)),
        task_footer=overrides.get("task_footer", _TASK_FOOTER),
        products_section=_build_products_section(composer_input),
    )
