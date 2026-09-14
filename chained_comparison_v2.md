# One call vs two calls

**single** quality 4.36 | worst criterion 3.2 | 2.7s | 0 rule breaks
**chained** quality 4.03 | worst criterion 2.5 | 4.6s | 0 rule breaks
  facts kept through the rewrite: 41%

## Scores by criterion

| arm | names_cause | follows_depth | follows_structure | answers_them | sounds_emerson | stays_grounded |
|---|---|---|---|---|---|---|
| single | 3.8 | 5.0 | 5.0 | 4.5 | 3.2 | 4.7 |
| chained | 4.3 | 5.0 | 3.5 | 4.0 | 3.0 | 4.3 |

## Every reply

### buildup
> customer: my curls have gone limp and my leave-in just sits on top of my hair now

**single** — 5 sentences, 5.0s, quality 4.5

> Your leave-in is sitting on the surface because a layer of buildup is blocking absorption. Limp curls on low porosity hair in the GCC always point to residue—either leftover product, natural oils, or mineral deposits from hard water. Until you remove that barrier with a clarifying or chelating wash, nothing you apply will actually reach the cuticle. Start there before changing anything else. Once you reset, watch how your hair responds to your usual routine before adding new products or steps.

- `names_cause` **5** — It explicitly names a concrete barrier—'a layer of buildup is blocking absorption'—and specifies 'mineral deposits from hard water' as a cause.
- `follows_depth` **5** — It stays within the 3–5 sentence limit by using five sentences, ending with 'Once you reset, watch how your hair responds to your usual routine before adding new products or steps.'
- `follows_structure` **5** — It follows the beats in order: 'Your leave-in is sitting on the surface' (What is Happening) → 'because a layer of buildup is blocking absorption' and '...hard water' (Most Likely Cause) → 'remove that barrier with a clarifying or chelating wash' (What to Change First) → 'watch how your hair responds' (What to Monitor).
- `answers_them` **4** — It echoes their complaint—'Your leave-in is sitting on the surface' and 'Limp curls'—but assumes 'low porosity hair in the GCC,' which the customer never stated.
- `sounds_emerson` **4** — It feels Emerson-specific by referencing 'in the GCC' and using curl-community terms like 'clarifying or chelating wash,' but it doesn’t define 'chelating' in plain English.
- `stays_grounded` **4** — Advice is realistic and product-safe, but absolutes like 'always point to residue' and 'nothing you apply will actually reach the cuticle' overstate certainty.

**chained** — 5 sentences, 5.2s, quality 4.67, facts kept 39%

<details><summary>draft from call 1</summary>

> Your hair is not absorbing products because there is a coating on the surface, which is blocking moisture and leaving treatments sitting on top. This buildup is most likely from leftover product, natural oils, or minerals from hard water. The first thing to do is use a clarifying or chelating wash to remove the residue, which should help your hair absorb moisture again. After clarifying, you can return to your usual routine and see if your hair responds better. Watch for improved absorption and curl definition after this step.

</details>

> Your leave-in sits on the surface because a coating blocks absorption. This buildup comes from product residue, natural oils, or hard water minerals. Clarify or chelate first: this removes the barrier and restores your hair’s ability to take in moisture. Resume your usual routine after clarifying. Track how your hair absorbs product and how your curls define—both will show if the buildup is gone.

- `names_cause` **5** — It names a concrete mechanism and sources: "a coating blocks absorption" and "buildup comes from product residue, natural oils, or hard water minerals."
- `follows_depth` **5** — It stays within the "3-5 sentences" limit, using five sentences from "Your leave-in sits on the surface..." to "both will show if the buildup is gone."
- `follows_structure` **5** — It follows the required beats in order: What is Happening—"Your leave-in sits on the surface..."; Most Likely Cause—"This buildup comes from..."; What to Change First—"Clarify or chelate first:"; What to Monitor—"Track how your hair absorbs product and how your curls define..."
- `answers_them` **5** — It mirrors the user’s issue—"Your leave-in sits on the surface"—and ties it to limp definition to monitor—"how your curls define."
- `sounds_emerson` **3** — While authoritative, it reads generic and uses the curl term "chelate" without a plain-English definition, which blunts Emerson’s distinct, explanatory voice.
- `stays_grounded` **5** — It makes modest, plausible claims—"removes the barrier and restores your hair’s ability to take in moisture"—without health promises or overreach.

**single** — 5 sentences, 2.6s, quality 4.5

> Your leave-in is sitting on top because your hair’s surface is coated—either from old product, natural oils, or minerals from washing in hard water. This layer blocks anything new from getting through, so your curls lose their bounce and your products appear to stop working. The only way forward is a reset: clarify or chelate to clear away what’s built up. After that, your hair will start absorbing again, and you’ll know you’re getting real moisture in. Watch how your products behave after the wash—if your leave-in starts to sink in, you’ve cleared the way.

- `names_cause` **4** — It identifies a mechanism ('your hair’s surface is coated') and concrete sources including 'minerals from washing in hard water,' but hedges with 'either from old product, natural oils, or minerals' instead of a single most-likely cause.
- `follows_depth` **5** — It delivers five sentences (from 'Your leave-in is sitting on top...' to 'Watch how your products behave after the wash—if your leave-in starts to sink in, you’ve cleared the way.'), which fits the 3–5 sentence limit.
- `follows_structure` **5** — It follows What is Happening ('Your leave-in is sitting on top...'), Most Likely Cause ('because your hair’s surface is coated—either from old product...'), What to Change First ('The only way forward is a reset: clarify or chelate...'), and What to Monitor ('Watch how your products behave after the wash—if your leave-in starts to sink in...').
- `answers_them` **5** — It directly addresses 'my leave-in just sits on top' with 'Your leave-in is sitting on top' and 'my curls have gone limp' with 'your curls lose their bounce.'
- `sounds_emerson` **3** — While authoritative ('The only way forward is a reset: clarify or chelate...'), this could come from any curl brand and does not define the science term when it says 'chelate'.
- `stays_grounded` **5** — It sticks to observable hair-care mechanisms like 'clarify or chelate to clear away what’s built up' and suggests monitoring ('Watch how your products behave after the wash'), avoiding medical or permanent claims.

**chained** — 5 sentences, 4.6s, quality 4.17, facts kept 37%

<details><summary>draft from call 1</summary>

> Your hair is not absorbing products properly, which is making your curls limp and causing leave-in to sit on top of your hair. This is most likely because there is residue coating your hair, either from product buildup, natural oils, or minerals from hard water. The first step you should take is to use a clarifying or chelating wash to remove this residue. After doing this, your hair should be able to absorb products better again. Keep an eye on how your hair responds after clarifying, and adjust your routine if needed.

</details>

> Your curls have lost definition because residue is blocking absorption. Product buildup, excess oils, or minerals are coating the hair shaft. Begin with a clarifying or chelating wash to remove these layers. Once the surface is clean, your leave-in will penetrate again. Watch how your hair responds post-wash and adjust only if limpness returns.

- `names_cause` **4** — It names a concrete blockage—'residue is blocking absorption'—and specifies sources—'Product buildup, excess oils, or minerals are coating the hair shaft'—though it lists multiple possibilities rather than one clear primary cause.
- `follows_depth` **5** — It uses exactly five sentences, from 'Your curls have lost definition...' through '...adjust only if limpness returns.'
- `follows_structure` **5** — It follows the beats in order: What is Happening ('Your curls have lost definition'), Most Likely Cause ('residue is blocking absorption... Product buildup, excess oils, or minerals'), What to Change First ('Begin with a clarifying or chelating wash'), and What to Monitor ('Watch how your hair responds post-wash').
- `answers_them` **5** — It directly addresses the customer's report of limp curls and leave-in sitting on top by noting 'Your curls have lost definition' and 'your leave-in will penetrate again.'
- `sounds_emerson` **2** — Lines like 'Begin with a clarifying or chelating wash' and 'Your curls have lost definition...' could appear in any curl guide, with no Emerson-specific stance or plain-English definition of terms.
- `stays_grounded` **4** — The advice—'Begin with a clarifying or chelating wash to remove these layers' and 'Watch how your hair responds post-wash'—is practical and safe, though 'your leave-in will penetrate again' overstates certainty.

### climate
> customer: my definition is gone by lunchtime every day here in Dubai

**single** — 4 sentences, 3.2s, quality 4.83

> Your definition is dropping out by midday because Dubai’s humidity is swelling your cuticle and loosening your curl pattern. This isn’t about needing more moisture—your hair is losing shape because moisture in the air is pushing past your natural barrier, breaking up clumps and leaving frizz. Switch focus to anti-humectant styling and sealing: use a glycerin-free styler, then lock it in with a sealing finisher to close the cuticle and shield from the climate. This outperforms moisture-heavy routines, which only invite more disruption in these conditions.

- `names_cause` **5** — It explicitly names the cause as “Dubai’s humidity is swelling your cuticle and loosening your curl pattern” and adds that “moisture in the air is pushing past your natural barrier.”
- `follows_depth` **5** — It uses four sentences (“Your definition is dropping out by midday…” … “This outperforms moisture-heavy routines…”), which fits the 3–5 sentence limit.
- `follows_structure` **5** — It follows Observation (“Your definition is dropping out by midday”), Interpretation (“because Dubai’s humidity is swelling your cuticle…”), Recommendation (“Switch focus to anti-humectant styling and sealing…”), and Why (“This outperforms moisture-heavy routines…”).
- `answers_them` **5** — It reflects their situation by citing timing and place—“by midday” and “Dubai’s humidity”—and offers a climate-specific plan.
- `sounds_emerson` **4** — It takes a clear stance (“This isn’t about needing more moisture”) and uses curl-savvy terms (“anti-humectant,” “glycerin-free styler,” “sealing finisher”), though it doesn’t define those terms in plain English.
- `stays_grounded` **5** — It sticks to plausible hair-science and routine advice—“humidity is swelling your cuticle” and “use a glycerin-free styler… then lock it in with a sealing finisher”—without making health or permanence claims.

**chained** — 4 sentences, 6.0s, quality 4.33, facts kept 41%

<details><summary>draft from call 1</summary>

> Your curls are losing definition by midday because the high humidity in Dubai is causing your hair cuticle to swell and your curl pattern to frizz and fall apart. This is a common challenge for curly, high-porosity hair in this climate. To help, switch to stylers that are free of humectants and glycerin, and use a sealing product to lock in your definition. This approach will protect your curls from humidity and prevent them from swelling and losing shape, unlike moisture-heavy formulas that can make the problem worse here.

</details>

> Midday definition loss in Dubai always traces back to humidity swelling the cuticle. Your curl pattern falls apart because high moisture in the air disrupts the boundaries set during your wash ‘n’ go. Replace stylers containing humectants and glycerin with formulas that seal—this keeps your definition intact. Sealing blocks humidity at the surface, protecting shape where moisture-heavy products would only accelerate frizz.

- `names_cause` **5** — It explicitly names a concrete cause: 'humidity swelling the cuticle' and 'high moisture in the air disrupts the boundaries'.
- `follows_depth` **5** — It stays within the 3–5 sentence limit, delivering four sentences from 'Midday definition...' to '...accelerate frizz.'
- `follows_structure` **3** — It blends Observation and Interpretation in 'Midday definition loss in Dubai always traces back to humidity...' before moving to Recommendation ('Replace stylers...') and Why ('Sealing blocks...'), so the first beat isn’t cleanly separated.
- `answers_them` **5** — It directly addresses the user’s situation by echoing 'Midday definition loss in Dubai' and tailoring advice to that climate.
- `sounds_emerson` **3** — While authoritative and using curl terms ('wash ‘n’ go,' 'humectants'), the guidance 'Replace stylers containing humectants and glycerin with formulas that seal' could come from any curl brand and lacks Emerson-specific framing or definitions.
- `stays_grounded` **5** — The mechanism 'Sealing blocks humidity at the surface' and the advice to avoid 'humectants and glycerin' in humidity are cautious and plausible without overpromising.

**single** — 4 sentences, 2.1s, quality 4.83

> Your curl definition fades by lunchtime because Dubai’s humidity is swelling your cuticle and lifting your pattern apart. This isn’t about lacking moisture—your hair is losing shape as water moves in and out, breaking up your clumps and creating frizz. The next step is to switch to an anti-humectant layering method and finish with a true sealer to keep the pattern locked down. Glycerin-rich formulas will undo your results here, which is why a climate-control approach outranks just adding more moisture or hold.

- `names_cause` **5** — It names a concrete driver—"Dubai’s humidity is swelling your cuticle and lifting your pattern apart," further explained by "water moves in and out, breaking up your clumps."
- `follows_depth` **5** — It uses four sentences—"Your curl definition fades...," "This isn’t about lacking moisture—...," "The next step is to...," "Glycerin-rich formulas will..."—within the 3–5 sentence limit.
- `follows_structure` **5** — Observation: "Your curl definition fades by lunchtime"; Interpretation: "This isn’t about lacking moisture—your hair is losing shape as water moves in and out"; Recommendation: "switch to an anti-humectant layering method and finish with a true sealer"; Why: "which is why a climate-control approach outranks just adding more moisture or hold."
- `answers_them` **5** — It directly addresses their situation—"by lunchtime" and "here in Dubai"—and tailors guidance to local humidity and product choices.
- `sounds_emerson` **4** — Authoritative, curl-native phrasing—"anti-humectant layering," "true sealer," and a clear stance on "Glycerin-rich formulas"—fits Emerson’s voice, though it doesn’t reference a distinctly Emerson-named method.
- `stays_grounded` **5** — It sticks to plausible mechanisms and care steps—"switch to an anti-humectant layering method... finish with a true sealer"—without promising permanent change or health claims.

**chained** — 5 sentences, 5.2s, quality 4.67, facts kept 36%

<details><summary>draft from call 1</summary>

> Your curls are losing definition by midday because the high humidity in Dubai is making your hair cuticle swell and separate the curl pattern, which leads to frizz and dropped styling. Emerson believes the main issue is the climate causing your hair to react this way, rather than a problem with your routine or technique. You should focus on using products that seal the hair and stay away from formulas heavy in humectants or glycerin, as these pull even more moisture from the humid air. This approach works better in your climate because sealing helps keep the curl pattern intact and avoids extra swelling, which is the main reason for your definition loss.

</details>

> Definition drops by midday because Dubai’s humidity swells your cuticle, breaking up the curl pattern and pushing your hair into frizz. The climate drives this, not a flaw in your routine. Choose sealants and avoid humectant-heavy formulas—especially glycerin—which pull more water from the air and make swelling worse. Prioritising sealing holds your curl structure together in these conditions and prevents the pattern from unraveling. This is the only lever that addresses the mechanism at work in your environment.

- `names_cause` **5** — It names a concrete mechanism: 'Dubai’s humidity swells your cuticle, breaking up the curl pattern' and notes 'humectant-heavy formulas—especially glycerin—...make swelling worse.'
- `follows_depth` **5** — It delivers exactly five sentences, from 'Definition drops by midday...' to 'This is the only lever that addresses the mechanism at work in your environment.'
- `follows_structure` **5** — It hits all beats in order: Observation 'Definition drops by midday...'; Interpretation 'The climate drives this...'; Recommendation 'Choose sealants and avoid humectant-heavy formulas—especially glycerin—'; Why 'Prioritising sealing holds your curl structure together...' and 'This is the only lever...'.
- `answers_them` **5** — It directly addresses their situation by citing 'Dubai’s humidity' and 'Definition drops by midday,' mirroring the user's Dubai context and lunchtime definition loss.
- `sounds_emerson` **4** — It writes with authority and plain-English science—'humectant-heavy formulas—especially glycerin—which pull more water from the air'—but 'Choose sealants' reads generic and not distinctly Emerson-specific.
- `stays_grounded` **4** — The mechanism is accurate and cautious, but 'This is the only lever that addresses the mechanism' is an overconfident absolute.

### frustrated
> customer: ive tried everything and nothing works, im honestly ready to just cut it all off

**single** — 3 sentences, 1.8s, quality 3.67

> If everything so far has felt like effort with no payoff, the issue is friction—too many steps, too much work, not enough result. Strip it all back: just wash and condition, nothing else, for one week. This rest lets your hair reset and shows you what it actually needs, instead of fighting through layers of routine.

- `names_cause` **2** — It calls the problem 'friction—too many steps, too much work,' which is a process label rather than a specific hair cause like buildup or hard-water film.
- `follows_depth` **5** — It uses three sentences—'If everything so far has felt like effort with no payoff.' 'Strip it all back: just wash and condition, nothing else, for one week.' 'This rest lets your hair reset and shows you what it actually needs'—matching the 1–3 sentence limit.
- `follows_structure` **5** — It notices their experience—'If everything so far has felt like effort with no payoff'—then gives one next step—'Strip it all back: just wash and condition, nothing else, for one week.'
- `answers_them` **4** — It echoes their frustration—'everything so far has felt like effort with no payoff'—and offers a simple next move, but it doesn’t acknowledge 'ready to just cut it all off.'
- `sounds_emerson` **2** — Phrases like 'the issue is friction—too many steps, too much work' and 'This rest lets your hair reset' are generic and lack Emerson’s curl-community specificity or defined terms.
- `stays_grounded` **4** — The advice—'just wash and condition, nothing else, for one week'—is conservative and the rationale—'shows you what it actually needs'—avoids unsupported claims.

**chained** — 2 sentences, 3.0s, quality 2.83, facts kept 43%

<details><summary>draft from call 1</summary>

> You sound really frustrated, and I noticed your high porosity curls get frizzy and lose definition. Try gently smoothing a little leave-in conditioner onto soaking wet hair right after washing, then let it air dry without touching it.

</details>

> High porosity curls lose definition and frizz because the cuticle stays lifted. Smooth a small amount of leave-in onto soaking wet hair, then air dry hands-off.

- `names_cause` **2** — They said 'ive tried everything and nothing works,' but you jump to 'High porosity curls lose definition and frizz because the cuticle stays lifted,' a specific cause for frizz not the problem they described.
- `follows_depth` **5** — The brief is 'required length: 1-3 sentences' and your reply is two sentences ('High porosity...' + 'Smooth a small amount...'), so it fits.
- `follows_structure` **1** — The instruction says 'Structure: what you noticed in their words → the one thing to do next,' but the reply opens with a diagnosis and never states what you noticed in their words.
- `answers_them` **2** — They said 'im honestly ready to just cut it all off,' yet the reply offers 'Smooth a small amount of leave-in...' without acknowledging that frustration or readiness to chop.
- `sounds_emerson` **3** — Using curl terms like 'High porosity' and 'cuticle stays lifted' shows authority, but the generic tip 'Smooth a small amount of leave-in...' could come from any brand, not distinctly Emerson.
- `stays_grounded` **4** — It sticks to plausible mechanism ('cuticle stays lifted') and a safe, simple step ('Smooth a small amount of leave-in... then air dry hands-off') without overpromising.

**single** — 2 sentences, 1.3s, quality 3.83

> When nothing is working, your hair is blocking what you put on it instead of letting it in. The single change: use less, not more—next wash, strip everything back to the simplest cleanse and style, nothing extra.

- `names_cause` **2** — It only says "your hair is blocking what you put on it instead of letting it in," which gestures at absorption issues without naming a concrete cause like mineral buildup, silicone film, or product overload.
- `follows_depth` **5** — It uses exactly two sentences—"When nothing is working..." and "The single change: use less, not more..."—within the 1–3 sentence limit.
- `follows_structure` **5** — It notices their words with "When nothing is working" and then gives the next action with "The single change: use less, not more—...simplest cleanse and style, nothing extra."
- `answers_them` **4** — It mirrors the customer’s "nothing works" with "When nothing is working" and offers a next step, though it doesn’t acknowledge "ready to just cut it all off."
- `sounds_emerson` **2** — Phrases like "use less, not more—...simplest cleanse and style" are generic and lack Emerson’s curl-community voice or clear stance grounded in curl science.
- `stays_grounded` **5** — It makes no unsupported promises and keeps advice practical: "use less, not more—...simplest cleanse and style, nothing extra."

**chained** — 3 sentences, 3.3s, quality 3.5, facts kept 49%

<details><summary>draft from call 1</summary>

> You are frustrated because your high porosity, medium density curly hair keeps frizzing and nothing has worked. The next step is to use a leave-in conditioner right after washing, while your hair is still very wet, to help lock in moisture and reduce frizz. This helps with definition and protects against dryness.

</details>

> You have high porosity, medium density curls that frizz because moisture escapes before your hair can hold definition. Apply a leave-in conditioner immediately after washing, while your hair is still very wet. This seals in moisture, reduces frizz and improves curl definition.

- `names_cause` **5** — It names a concrete mechanism: 'You have high porosity, medium density curls that frizz because moisture escapes before your hair can hold definition.'
- `follows_depth` **5** — It stays within 1–3 sentences, using exactly three: 'You have...'; 'Apply a leave-in...'; 'This seals in moisture...'.
- `follows_structure` **2** — It starts with a diagnosis—'You have high porosity...'—and then a next step, but never states 'what you noticed in their words' before giving the action.
- `answers_them` **2** — The customer said 'ive tried everything and nothing works, im honestly ready to just cut it all off,' but the reply assumes 'frizz because moisture escapes' without acknowledging their specific frustration or cutting impulse.
- `sounds_emerson` **3** — While it uses curl-community terms like 'high porosity' and 'leave-in conditioner,' the phrasing 'reduces frizz and improves curl definition' could come from any brand and lacks Emerson’s distinctive explanatory voice.
- `stays_grounded` **4** — The advice 'Apply a leave-in conditioner... This seals in moisture, reduces frizz and improves curl definition' is reasonable and non-misleading, though asserting 'You have high porosity, medium density curls' is a confident claim without evidence.
