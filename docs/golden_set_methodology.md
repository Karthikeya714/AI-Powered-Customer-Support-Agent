# Golden Evaluation Set Methodology

229 manually labeled examples, sampled exclusively from `golden_pool`
(the 15% of SpotifyCares support cases held out in Phase 3 and never used
to build the knowledge index, weak intent labels, or any other part of the
system). `data/golden/golden_set.jsonl` / `.csv`.

## Pipeline

1. **`scripts/sample_golden_candidates.py`** — stratified sampling of 293
   candidate messages from the 6,480 `golden_pool` cases.
2. **Manual labeling** (this document + `data/golden/gold_labels_draft.json`)
   — every one of the 293 candidates read individually and assigned a
   `gold_intent`, `gold_action`, and `gold_notes`, or dropped for quality.
3. **`scripts/build_golden_set.py`** — merges labels with candidates, drops
   low-quality candidates, caps oversized intents, writes the final set.

## Sampling strategy

**Golden_pool is the only thing touched.** No candidate came from
`knowledge`-split data, so nothing used to build the retrieval index or
train the Phase 7 baseline could influence which examples ended up here.

Stratification needed intent labels for `golden_pool` messages before any
existed (weak intent labels were only ever computed for `knowledge`-split
data, by design — see Phase 4's decision log). To sample across all 12
intents without leaking `golden_pool` into model *fitting*:

- The same frozen TF-IDF+KMeans model from Phase 4 (deterministic given
  the fixed seed) was re-fit on `knowledge` data only, then used to
  **transform** (never re-fit) `golden_pool` messages — a read-only
  projection through an already-frozen model, not a new fit. This gave a
  rough cluster hint per message, used only to pick a diverse sample.
- For the 3 intents with no dedicated cluster
  (`account_security_compromise`, `account_data_loss`,
  `cancellation_or_refund_request`), a keyword/regex search over
  `golden_pool` text surfaced candidates directly (e.g. `hack`,
  `compromised`, `disappeared`, `cancel`, `refund`).
- A "hard cases" bucket added the 28 messages farthest from any cluster
  centroid (lowest clustering confidence) — a cheap proxy for
  atypical/ambiguous text. This bucket turned out to contain nearly all
  the non-English messages in the sample (Dutch, Swedish, French,
  Indonesian, Tagalog), which became a deliberate category of hard case
  in their own right (see Action rubric below).

Target counts per intent were set deliberately unbalanced from real
traffic — `playback_technical_issue` (the largest real category) was
capped relative to its true frequency, and the 3 no-cluster risk intents
were oversampled relative to their rarity — because a golden set
proportional to raw traffic would be dominated by the majority class and
make headline metrics even more misleading than they already risk being
(see `DECISION_LOG.md` and the Phase 16 "misleading headline number"
section of the eventual report).

## Labeling

Every one of the 293 sampled candidates (not a further sub-sample) was
read individually — message text plus any prior conversation context and
the historical brand response — and assigned:

- **`gold_intent`** — one of the 12 `src/intents/labels.py` categories.
  The clustering/keyword hint that got a message sampled was frequently
  **not** the final label: reading the actual text corrected the intent
  in roughly a third of cases (e.g. a message clustered into
  `playback_technical_issue` because it shared troubleshooting vocabulary
  turned out, on reading, to be a feature request or a billing question).
  This is expected and is exactly why the hint is only a sampling aid, not
  a label source.
- **`gold_action`** — `AUTO_HANDLE` or `ESCALATE`, per the rubric below.
- **`gold_notes`** — why, especially for anything reclassified or
  non-obvious.

11 candidates that were reclassified into an intent with no dedicated
cluster, or that were pure keyword-search false positives, or duplicates,
or too vague to label with confidence, were dropped (`keep: false`) rather
than forced into a label — e.g. `gc_0210` was an exact duplicate of
`gc_0208`, `gc_0257` matched the keyword "cancel" but was about a UI
dialog button, not subscription cancellation. Full reasoning for every one
of the 293 candidates — kept or dropped — is in
`data/golden/gold_labels_draft.json`.

### Action rubric

There is no working escalation engine yet (that's Phase 11) — these
`gold_action` labels **are** the ground truth that engine will eventually
be measured against, assigned by applying the plan's stated escalation
principles directly to real message content:

**Escalate when:** potential fraud/account compromise; explicit refund or
cancellation demands (not just an informational "how do I cancel"
question); repeated/unresolved complaints (customer states they already
tried multiple times, or an issue is explicitly recurring); payment
disputes (charged but no service, wrong amount, double-charged); data
loss affecting playlists or an entire library (as opposed to downloaded
songs, where a consistent, well-precedented fix pattern exists in the
historical data); safety or legal/contractual language; hostile or
all-caps tone where de-escalation matters; and — a rule applied for
simplicity and consistency rather than case-by-case — **any message not
in English**, since the retrieval/generation pipeline is grounded in
English historical evidence and a confidently-wrong reply in a language
the system hasn't been evaluated in is worse than escalating.

**Auto-handle when:** a common, well-precedented issue with a consistent
historical resolution pattern (device/OS troubleshooting, catalog/feature
requests, informational billing questions, first-instance login trouble)
and no signal above.

Two specific refinements worth calling out because they show the rubric
isn't a flat per-intent lookup:

- Within `account_data_loss`, **downloaded/offline songs** disappearing
  has a consistent, well-documented fix in the historical data ("Downloads
  unexpectedly removed" steps) and was auto-handled on first occurrence;
  **playlists or an entire library** disappearing was escalated regardless
  — no comparable reliable fix pattern exists, and the emotional/data
  stakes are higher.
- Within `dm_followup`, a calm first follow-up ("just sent a DM, thanks!")
  was auto-handled; explicit urgency ("URGENT", "being ignored all day")
  was escalated.

### Label consistency check

The plan calls for a second human to review a subset. No second reviewer
is available in this environment, so a **blind self-consistency check**
was run instead: 25 examples (seed 123) were re-labeled from the message
text alone — without looking at the saved `gold_intent`/`gold_action` —
and compared against the original labels.

**Result: 25/25 (100%) agreement on both intent and action**
(`data/golden/consistency_check_results.json`).

This is evidence the rubric is being applied *consistently* by the same
annotator, not evidence that the labels are *correct* — a truly
independent second annotator would likely surface some genuine
disagreement on the harder boundary cases (e.g. the exact line between
"repeated" and "first-instance", or intent boundaries like
`billing_subscription_issue` vs. `cancellation_or_refund_request`). This
limitation is stated plainly rather than implied away by a clean number,
and should be read alongside Phase 14 (LLM-judge vs. human agreement),
where the same honesty standard applies.

## Final composition

229 examples (within the required 150–250), all 12 intents represented,
124 `AUTO_HANDLE` / 105 `ESCALATE` (54%/46% — deliberately not skewed
toward the "safe" majority class, so escalation precision/recall can
actually be measured):

| intent | count |
|---|---:|
| playback_technical_issue | 28 |
| feature_request_or_missing_content | 26 |
| billing_subscription_issue | 24 |
| account_access_issue | 20 |
| account_security_compromise | 19 |
| family_plan_issue | 18 |
| student_discount_issue | 18 |
| cancellation_or_refund_request | 17 |
| account_data_loss | 16 |
| acknowledgment_closing | 15 |
| customer_service_feedback | 15 |
| dm_followup | 13 |

Oversized intents (mostly ones that absorbed messages reclassified away
from their clustering hint) were capped by `scripts/build_golden_set.py`
using a seeded, deterministic sample that **keeps all `ESCALATE` examples
first**, filling the remainder with `AUTO_HANDLE` — so capping doesn't
quietly erase the rarer, more valuable escalation signal.

## How this avoids leakage

- Only `golden_pool` cases were candidates — `knowledge`-split data was
  never sampled.
- The clustering model used for sampling hints was fit on `knowledge`
  data only; `golden_pool` messages only ever passed through it via
  `.transform()`/`.predict()` (no re-fitting).
- `gold_action` labels were assigned from first principles (the plan's
  stated escalation criteria), not from any system output — no escalation
  engine exists yet to leak from.

## Reproduce

```bash
python -m scripts.sample_golden_candidates   # writes golden_candidates.jsonl (candidates only, no labels)
python -m scripts.build_golden_set           # merges with gold_labels_draft.json -> golden_set.jsonl / .csv
```
