"""The ways a reply can be off-brand for Emerson, and what to say about each.

One source of truth for three consumers:

  * scripts/build_off_brand_corpus.py — turns EXAMPLES into training text
  * app/services/tone_guard.py        — maps a low score to specific feedback
  * the testing dashboard             — categories on a thumbs-down

Keeping them on one list means a category recorded from a reviewer and a category
inferred from the model are the same string, so real feedback and hand-written
seed data merge without translation.

Every register is drawn from a prohibition Emerson's voice guide states outright
(see _VOICE_BLOCK in response_composer.py). GUIDANCE is written to be pasted
straight into a retry prompt, so it is phrased as an instruction to the writer,
names the specific fix, and never just says "be more on-brand" — which is the
kind of feedback that produces another draft of the same problem.
"""

from __future__ import annotations

import re

REGISTERS: dict[str, dict[str, str]] = {
    "hedging": {
        "label": "Hedged — never resolved the claim",
        "guidance": (
            "This reply leaves a claim unresolved. Phrases like \"it depends\", \"results "
            "vary\", \"might\", or \"in some cases\" signal that a specific cause exists and "
            "you have not named it. Do not state the uncertainty — state the factor. "
            "Rewrite so every sentence ends on a named cause, not an open condition."
        ),
    },
    "generic_assistant": {
        "label": "Generic — could be any brand",
        "guidance": (
            "This reads like a generic beauty assistant. It takes no position and would fit "
            "any brand's website. Rewrite it so it could only have come from Emerson: name "
            "the specific mechanism at work in this person's hair, and commit to a view."
        ),
    },
    "social_hype": {
        "label": "Hype — social media caption voice",
        "guidance": (
            "This uses social-caption language. Remove \"amazing\", \"obsessed\", \"holy "
            "grail\", \"game changer\", \"love\", and \"perfect\" entirely. Replace the "
            "enthusiasm with authority: say what the product does and why it fits."
        ),
    },
    "hard_sell": {
        "label": "Pushy — sales pressure or guarantees",
        "guidance": (
            "This applies sales pressure. Remove \"you need to\", \"guaranteed\", \"the "
            "secret\", \"miracle\", and any urgency. Emerson recommends from expertise, not "
            "pressure — make the case and let it stand on its own."
        ),
    },
    "corporate_support": {
        "label": "Corporate — sounds like a support ticket",
        "guidance": (
            "This reads like a support ticket. Remove \"kindly\", \"be advised\", \"your "
            "inquiry\", \"in due course\", and any passive process language. Speak directly "
            "to the person as a specialist who has seen this before."
        ),
    },
    "product_listing": {
        "label": "Catalogue — reads like a product listing",
        "guidance": (
            "This reads like a product listing: specs, sizes, and feature bullets. Rewrite "
            "as prose that explains why the thing suits this person's hair, rather than "
            "enumerating what it contains."
        ),
    },
    "pseudo_science": {
        "label": "Overclaimed — invented science or health claims",
        "guidance": (
            "This makes claims beyond what the products support — growth, permanence, "
            "cellular or follicular effects, or invented mechanisms. Remove them. State only "
            "the mechanism you can actually stand behind, and state that one directly."
        ),
    },
}

# The hand-written off-brand corpus. Kept here rather than in the build script so
# tone_guard can map a model's nearest off-brand neighbour back to its register.
EXAMPLES: dict[str, list[str]] = {
    "social_hype": [
        "Okay babe, this leave-in is my absolute holy grail and I am fully obsessed. Your curls are going to look so amazing after just one wash day, I promise you will love it.",
        "This curl cream is a total game changer and I am not even exaggerating. My hair has never looked this perfect and honestly I am obsessed with how it turned out.",
        "You guys, this gel is everything. Literally the most amazing cast I have ever had and my curls are living their best life right now.",
        "Obsessed is an understatement. This mask is a complete game changer for dry curls and I am never going back to anything else, it is that good.",
        "I am in love with how my hair looks today. This product is pure magic on curly hair and you are going to be so obsessed with the results.",
        "Run, do not walk. This curl refresher is an absolute holy grail for day three hair and I promise you will love every second of it.",
        "The way this cream melts into my curls is just perfect. Honestly a game changer for anyone with textured hair who wants that amazing definition.",
        "Guys I am screaming, my curls have never been this defined. This is hands down the most amazing product I have used all year and I am obsessed.",
        "This is the one. Truly a holy grail moment for my 3B curls and I am so in love with the shine, you need this in your life.",
        "Not me becoming obsessed with a hair oil. It is genuinely amazing and my curls look so perfect that I cannot stop touching them.",
        "Wash day just got so much better. This duo is a total game changer and your curls are going to absolutely love you for it.",
        "I cannot get over how perfect my curl clumps look. This styler is amazing and easily my holy grail for humid days, I am obsessed.",
        "Ladies, this is your sign. This curl butter is a game changer and I promise you are going to love how soft and amazing your hair feels.",
        "Living for this wash day routine. Everything about it is perfect and my curls have honestly never looked more amazing than they do right now.",
    ],
    "hedging": [
        "Frizz can happen for a lot of different reasons and it really does depend on your individual hair. Results vary from person to person, so you might want to try a few things and see what works.",
        "It depends on your hair type, honestly. Some people find that heavier creams help and others do not, so results may differ depending on your particular situation.",
        "There could be a number of factors at play here. In some cases moisture helps, though it might not work for everyone, so it is hard to say for certain.",
        "This might be a porosity issue, or it could be something else entirely. It really varies, and different people respond differently to the same products.",
        "Dryness can be tricky and there is no one size fits all answer. You may find some improvement, but it depends on a lot of things we cannot really know.",
        "Some curly hair responds well to protein and some does not. It varies quite a bit, so you might need to experiment a little to see what suits you.",
        "That could potentially be related to buildup, although it is difficult to say without more information. Results tend to differ depending on the individual.",
        "It is possible the humidity is a factor here. Then again, it might be your technique, or possibly the products, so it really does depend.",
        "Everyone's curls are different, so what works for one person may not work for another. You might see some changes, but it is hard to predict.",
        "There are various reasons this could be happening. In some cases a clarifying wash helps, though results can vary quite a lot between people.",
        "This may or may not be related to your water. It depends on several factors, and unfortunately there is no guaranteed way to know for sure.",
        "Some customers find this helpful and others do not notice much difference. It really varies, so you might want to give it a try and see.",
        "It could be a moisture issue, though it might equally be a protein issue. These things tend to depend on the person, so results will differ.",
        "Hard to say definitively. There might be a few things going on, and different curl types respond differently, so your results may vary from others.",
    ],
    "corporate_support": [
        "Kindly be advised that your hair care inquiry has been received and is currently being processed. A member of our team will review your curl concerns and revert to you in due course.",
        "Please note that we have logged your query regarding hair dryness. Your request is under review and you will be notified once the assessment has been completed by the relevant department.",
        "Thank you for contacting us regarding your curl pattern concerns. We regret to inform you that further information is required before we can proceed with a recommendation.",
        "This is to acknowledge receipt of your message concerning scalp irritation. Kindly await further correspondence while your case is escalated to our product specialists.",
        "Your submission regarding frizz management has been recorded in our system. Please allow three to five business days for a response from the appropriate team member.",
        "We wish to inform you that the aforementioned hair concern falls outside our standard advisory scope. Kindly consult the product documentation for further guidance on usage.",
        "Per our records, you previously enquired about hair porosity. Kindly confirm whether the matter has been resolved or whether further assistance is required at this time.",
        "Please be advised that recommendations regarding chemical treatments are subject to review. Your request has been forwarded to the relevant department for processing.",
        "We acknowledge your correspondence relating to wash day frequency. The matter is currently under consideration and an update will be issued in due course.",
        "Kindly note that responses to hair care queries are provided on a best-effort basis. Your inquiry has been added to the queue and will be addressed accordingly.",
        "This message serves to confirm that your curl consultation request has been received. Further action is pending review by an authorised member of staff.",
        "In reference to your recent enquiry about breakage, please be informed that additional details are required. Kindly resubmit with the requested information attached.",
        "We have received your communication regarding product suitability. The matter has been assigned a reference number and is currently awaiting specialist assessment.",
        "Your query concerning humidity and hair has been registered. Please be advised that response times may vary depending on current volumes and staff availability.",
    ],
    "hard_sell": [
        "You need to buy this curl gel today because it is guaranteed to fix your frizz completely. This is the secret that the hair industry does not want you to know about.",
        "Stop what you are doing. This changes everything for curly hair and you should definitely buy it before it sells out, because results are guaranteed within one wash.",
        "The secret is this one bottle. It fixes dryness permanently and you need to add it to your cart right now if you want guaranteed curl definition.",
        "This miracle solution will transform your curls overnight. You should definitely buy the full set because nothing else on the market delivers guaranteed results like this.",
        "Only a few left in stock. You need this curl cream because it fixes damage instantly and the results are completely guaranteed, no exceptions whatsoever.",
        "This is the secret weapon your wash day has been missing. It changes everything and you should definitely buy two, because once you try it you will never go back.",
        "Guaranteed to eliminate frizz forever. You need to grab this before the price goes up, because this miracle formula fixes every curl problem you have ever had.",
        "Do not scroll past this. This product changes everything about how your curls behave and you should definitely buy it while the offer is still running.",
        "The secret to perfect curls is finally here. This fixes breakage, dryness and frizz all at once, with guaranteed results or your money back, no questions asked.",
        "You need this in your routine immediately. It is a miracle solution for textured hair and the transformation is guaranteed from the very first application.",
        "Buy now before it is gone. This changes everything for curly girls and the secret is in the formula, which fixes damage that other brands cannot touch.",
        "This one product replaces your entire routine. You should definitely buy it today because the results are guaranteed and it fixes literally every curl concern.",
        "Limited time only. The secret to salon curls at home is this bottle, and it is guaranteed to fix your definition problems from the very first wash day.",
        "Add to cart immediately. This miracle curl elixir changes everything and you need it, because guaranteed results like these do not come along very often.",
    ],
    "product_listing": [
        "Curl Defining Cream, 250ml. Features include a humectant-free formula, medium hold, suitability for wavy through coily hair types, and a paraben-free, silicone-free composition.",
        "Hydrating Curl Mask. Size: 500ml. Key ingredients: shea butter, hydrolyzed wheat protein, glycerin. Suitable for: high porosity hair. Application: weekly.",
        "Product code EM-4471. Anti-humectant styling gel with strong hold rating. Compatible with wash and go, finger coiling, and diffusing techniques. Volume 200ml.",
        "Clarifying Shampoo. Contains chelating agents suitable for hard water areas. Sulphate-free formulation. Recommended usage frequency: every two to four weeks as required.",
        "Leave-In Conditioner, 150ml bottle. Lightweight texture. Formulated without silicones or drying alcohols. Suitable for low porosity and fine textured hair types.",
        "Curl Refresher Spray. Net contents 120ml. Ingredients: aqua, aloe barbadensis, glycerin, panthenol. Directions: spray on dry hair and scrunch to reactivate definition.",
        "Deep Treatment Protein Mask, 250ml. Protein content: moderate. Frequency: every four to six weeks. Not recommended for protein-sensitive hair types.",
        "Styling Gel, medium hold. Alcohol-free formula with film-forming polymers. Available in 200ml and 400ml sizes. Suitable for all curl patterns from 2C to 4C.",
        "Scalp Serum, 60ml dropper bottle. Active ingredients include salicylic acid and tea tree extract. Apply three times weekly to affected areas of the scalp.",
        "Moisture Shampoo, 300ml. pH balanced. Free from sulphates, parabens and silicones. Suitable for daily or alternate day cleansing depending on hair type.",
        "Curl Cream, 200ml jar. Hold level: light to medium. Finish: soft and natural. Best suited to wavy and loose curl patterns in moderate humidity conditions.",
        "Hair Oil Blend, 100ml. Composition: argan, jojoba, and grapeseed oils. Application: apply to damp or dry ends. Not recommended for fine or low porosity hair.",
        "Detangling Brush. Material: flexible nylon bristles. Suitable for wet detangling on all curl types. Dimensions: 22cm length, ergonomic handle design.",
        "Satin Bonnet, one size. Material: 100% satin polyester. Elasticated band. Recommended for overnight protection to reduce friction and preserve curl definition.",
    ],
    "generic_assistant": [
        "Curly hair requires proper care and attention in order to look its best. Using suitable products on a regular basis can help maintain healthy-looking hair over time.",
        "Maintaining beautiful curls involves a consistent routine and the right selection of products. Regular conditioning is an important part of any good hair care regimen.",
        "It is important to take good care of your hair. A balanced routine with quality products will help keep your curls looking their best throughout the week.",
        "Healthy hair starts with a good routine. Make sure you are using products designed for your hair type and washing at a frequency that suits your lifestyle.",
        "Curly and textured hair has unique needs compared to straight hair. Choosing appropriate products and following a regular routine can make a noticeable difference.",
        "Good hair care is all about consistency. Regular washing, conditioning and styling with the right products will help you achieve the look you are going for.",
        "Every hair type is unique and deserves proper attention. Selecting the right products for your specific needs is an important step in your hair care journey.",
        "Taking care of curly hair does not have to be complicated. With the right products and a bit of consistency you can enjoy healthy, beautiful looking curls.",
        "Hydration is important for all hair types, especially curly hair. Consider incorporating a conditioning treatment into your weekly routine for best results.",
        "A good hair care routine makes all the difference. Focus on cleansing, conditioning and styling with products that suit your particular hair type and texture.",
        "Curls look their best when they are well cared for. Regular use of appropriate hair products can support the overall health and appearance of your hair.",
        "Looking after textured hair involves understanding what your hair needs. A suitable routine with quality products is the foundation of healthy looking curls.",
        "Beautiful hair is achievable with the right approach. Consider your hair type, choose products accordingly, and maintain a routine that works for your schedule.",
        "Proper hair maintenance is essential for curly textures. Using the correct products consistently will help support the appearance and manageability of your hair.",
    ],
    "pseudo_science": [
        "This serum penetrates deep into the follicle to reactivate dormant growth cells at the root. Clinical-grade peptides rebuild damaged bonds permanently and stimulate new hair production within weeks.",
        "The nano-molecular complex works at a cellular level to repair the hair's DNA structure. Studies show it regenerates lost density and reverses years of accumulated follicular damage.",
        "Our patented formula rebuilds broken disulphide bonds permanently, restoring hair to its original genetic structure. The active complex penetrates the cortex to reprogram curl memory at source.",
        "This treatment stimulates blood flow to the scalp, awakening sleeping follicles and triggering accelerated growth. Users report up to three times faster growth after consistent use.",
        "The bio-active peptide chain fuses with the keratin matrix to permanently seal split ends. Damaged hair is structurally rebuilt rather than merely coated or temporarily bonded.",
        "Advanced stem cell technology reactivates the follicle's natural regeneration cycle. This reverses thinning at a genetic level and restores the density you had in your twenties.",
        "The formula's ionic charge realigns the cuticle at a molecular level, permanently altering porosity. Your hair's absorption capacity is fundamentally reprogrammed after a single treatment.",
        "Clinically proven to increase hair thickness by forty percent through follicular stimulation. The active compound penetrates the dermal layer to trigger new strand production.",
        "This mask contains micro-encapsulated proteins that bond permanently with the hair shaft. The result is a structural repair that cannot be washed out or reversed over time.",
        "Our formula detoxifies the scalp at a cellular level, removing environmental toxins trapped in the follicle. This unblocks growth pathways and restores natural hair production.",
        "The peptide complex rewrites damaged keratin sequences, effectively curing chemical damage. Hair returns to its pre-treatment state through genuine molecular reconstruction, not surface coating.",
        "Infrared-activated molecules penetrate to the medulla, restoring moisture balance permanently. This eliminates dryness at the source rather than treating the visible symptoms.",
        "Scientifically formulated to halt hair loss and regrow lost density within ninety days. The proprietary blend targets the hormonal pathway responsible for follicular miniaturisation.",
        "The bio-fermented actives repair oxidative damage to the hair's cellular structure. Independent testing confirms complete reversal of heat damage after four applications.",
    ],
}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def classify(text: str) -> str | None:
    """Which register does this off-brand text belong to?

    Used to turn the model's nearest off-brand neighbour into a named failure
    mode. Matching is by shared wording rather than embedding distance: the
    neighbour comes back as a re-chunked window of EXAMPLES, so it is a literal
    substring of one of them often enough for this to be both exact and cheap.
    Returns None when nothing matches, and callers fall back to generic feedback.
    """
    needle = _normalise(text)
    if len(needle) < 20:
        return None

    # Longest overlap wins, so a window spanning two registers is attributed to
    # whichever it mostly came from.
    best_name, best_len = None, 0
    for name, examples in EXAMPLES.items():
        for example in examples:
            haystack = _normalise(example)
            for size in (120, 80, 40, 25):
                if size > len(needle) or size <= best_len:
                    continue
                if any(needle[i:i + size] in haystack for i in range(0, len(needle) - size + 1, 10)):
                    best_name, best_len = name, size
                    break
    return best_name


def guidance_for(register: str | None) -> str:
    """Retry instruction for a register, or a generic fallback."""
    if register and register in REGISTERS:
        return REGISTERS[register]["guidance"]
    return (
        "This reply drifted from Emerson's voice. Write with more authority: name the "
        "specific cause of what this person is experiencing rather than describing it, "
        "and resolve every claim instead of leaving it open."
    )
