# What Is Misleading About My Headline Number?

**The headline claim:** *"Our AI intent classifier achieves 84.7% accuracy on the golden evaluation set — a 72.5-point improvement over the majority baseline and 27.9 points over TF-IDF."*

This is true. It is also not the number that should be leading a
discussion of whether this system is safe or useful to deploy. Below is
every way that headline number is incomplete, computed and checked
against real project data rather than asserted.

---

## 1. It has a confidence interval, and it isn't small

229 examples is a golden set, not a firehose. A normal-approximation 95%
confidence interval on 84.7% accuracy at n=229 is **[80.1%, 89.4%]** —
plus or minus 4.7 points. "84.7%" is a point estimate; a re-run with a
different (equally valid) 229-example sample could plausibly land
anywhere in that band. Individual intents fare worse: the rarest
(`dm_followup`, support 13) has an F1 confidence interval wide enough
that its precision (0.650) and recall (1.000) should be read as
directional, not precise.

## 2. The golden set was deliberately rebalanced — and that changes the number, in a specific direction

Phase 5's golden set intentionally does *not* mirror real traffic:
`playback_technical_issue` is capped at 12.2% of the golden set despite
being **41.4%** of real knowledge-pool traffic (`data/processed/intent_distribution.json`),
specifically so the golden set wouldn't be dominated by the majority
class (see `docs/golden_set_methodology.md`).

This was the right call for building a trustworthy evaluation set, but
it means "84.7% accuracy" is **not** an estimate of "how often the
classifier is right on an average incoming message." Recomputing
accuracy weighted by real traffic proportions instead of golden-set
proportions (using the 9 intents with weak-label frequency data):

| Intent | Real traffic share | Recall |
|---|---:|---:|
| playback_technical_issue | 41.4% | 71.4% |
| billing_subscription_issue | 16.1% | 87.5% |
| account_access_issue | 12.4% | 85.0% |
| feature_request_or_missing_content | 9.5% | 88.5% |
| acknowledgment_closing | 6.4% | 86.7% |
| family_plan_issue | 5.7% | 94.4% |
| student_discount_issue | 4.9% | 94.4% |
| dm_followup | 2.3% | 100.0% |
| customer_service_feedback | 1.2% | 86.7% |

**Traffic-weighted accuracy: 81.6%**, not 84.7% — a real, if modest, drop.
The reason is specific and non-obvious: `playback_technical_issue` is
*both* the single most common real-world intent *and* one of the
weaker-performing categories (71.4% recall, the second-lowest of all 12).
A classifier that's slightly worse at the most common thing users ask
about will always look better than it should on a deliberately-balanced
eval set. This isn't a flaw in the golden-set methodology — a
traffic-proportional eval set would have its own, worse problem (see
below) — but it does mean 84.7% should never be read as "accuracy on a
random incoming message."

## 3. Deliberately hard examples pull the number down — and they should

The golden set includes 28 messages sampled specifically because they
sat farthest from any cluster centroid during stratified sampling — a
proxy for "genuinely ambiguous or atypical" (`docs/golden_set_methodology.md`).
22 of those ended up in the final set. On this hard subset:

- **Hard-case accuracy: 77.3%** (n=22)
- **Everything else: 85.5%** (n=207)

An 8-point gap. A golden set that skipped these deliberately-hard cases
(easy to do by accident, sampling only "clean" examples) would report a
higher, less honest number. The gap existing at all is a sign the
sampling worked, not a problem to fix.

## 4. The escalation number is the one that actually matters, and it's much worse

This is the headline finding of the entire evaluation, first surfaced in
Phase 13 and root-caused in Phase 15 — restated here because it's the
single most important answer to "what's misleading about my headline
number":

| Metric | Value | 95% CI |
|---|---:|---:|
| Intent accuracy | 84.7% | [80.1%, 89.4%] |
| **Escalation accuracy** | **60.3%** | **[53.9%, 66.6%]** |

The confidence intervals **don't overlap**. This gap is not sampling
noise — it's a real, structural difference between how well the system
classifies intent and how well it decides when it's safe to act
automatically. Worse, the error is concentrated in the dangerous
direction: a **64.8% false auto-handle rate** — of golden examples a
human said should escalate, the system auto-handled nearly two-thirds.
Root cause (Phase 13/15): `HIGH_RISK_INTENTS` hard-codes only
`account_security_compromise`; two other intents the golden-labeling
rubric escalates *conditionally* (`account_data_loss`,
`cancellation_or_refund_request`) have no corresponding rule, plus
regex safety nets that miss real paraphrases of repeated-complaint
language. If this system's success were reported only via intent
accuracy, this would be invisible.

## 5. Reply-quality scores look great partly because this brand's replies are easy to ground

Phase 14's LLM judge scored generated replies 4.90/5 on groundedness and
4.95/5 on no-hallucination. Genuinely good numbers — but Phase 10 and
Phase 15 both independently noted why they're easier to achieve here
than they'd be elsewhere: SpotifyCares' real historical replies are
overwhelmingly low-specificity triage messages ("DM us your account
email") rather than replies that commit to a concrete refund amount,
deadline, or policy. There's rarely a risky, specific claim available to
hallucinate in the first place. A brand whose historical support
responses made more concrete commitments would give the same generation
approach a harder test, and these scores would not be assumed to
transfer.

## 6. The golden labels themselves carry human-labeling uncertainty that was only partially checked

Phase 5's label-consistency check found 100% agreement — but it was a
**blind self-consistency check by the same annotator**, not independent
verification by a second person (no second labeler was available in this
environment; stated plainly in `docs/golden_set_methodology.md` at the
time). 100% agreement with yourself, re-applying the same rubric, is
evidence the rubric is being applied *consistently* — it is not evidence
the labels are *correct*. A genuinely independent second annotator would
likely disagree on some of the real boundary cases this project's own
analysis surfaced (Phase 15: `cancellation_or_refund_request` vs.
`billing_subscription_issue` accounts for 2 of the classifier's 35
intent errors, and is exactly the kind of case two reasonable people
could label differently). Every accuracy number in this project is
measured against labels that carry some of this same uncertainty.

## 7. What was checked and is *not* a source of doubt: data leakage

Worth stating affirmatively, not just as a caveat: `golden_pool` was
never used to fit the intent classifier's weak labels, the TF-IDF
vectorizer, the retrieval index, or any escalation threshold — every one
of those decisions is documented in `DECISION_LOG.md` with an explicit
non-golden data source (Phase 4's clustering fit on `knowledge` only,
Phase 11's threshold calibrated on a disjoint `golden_pool` validation
sample, Phase 6's majority class computed from training distribution).
This was checked repeatedly across phases, not assumed once and
forgotten — most recently in Phase 13's explicit decision *not* to patch
`decision.py` after seeing exactly which golden examples it was failing.
Leakage is not among this project's list of concerns for the 84.7%
figure.

---

## Bottom line

**84.7% intent accuracy is a real, honestly-measured number** — not
inflated by leakage, not hiding a broken pipeline. But reporting it alone
would be misleading in at least four independent, quantified ways:
traffic-reweighting drops it to 81.6%; the deliberately-hard subset sits
at 77.3%; the number that actually predicts deployment safety
(escalation accuracy) is 60.3%, not 84.7%; and the ground truth it's
measured against carries labeling uncertainty that was checked but not
eliminated. None of these individually invalidate the headline number.
Together, they're the difference between "the classifier works" and
"the system is safe to deploy as-is" — and this project's evaluation was
built specifically to be able to tell those two claims apart, rather than
conflate them.
