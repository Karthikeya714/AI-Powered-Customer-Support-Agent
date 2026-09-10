# Decision Log

Non-obvious engineering decisions made throughout the project, in
chronological order. Each entry: decision, reason, alternatives considered,
trade-off.

## 2026-09-09 — Project structure follows the provided architecture spec exactly

**Decision:** Use the directory layout from
`Hiver_SDE_Project_Architecture_for_Claude_Code.md` section 4 verbatim
(`src/{data,intents,retrieval,generation,escalation}`, `baselines/`,
`evaluation/`, `scripts/`, `app/`, `tests/`, `artifacts/`, `docs/`).

**Reason:** The spec was clearly designed so each pipeline stage
(classification, retrieval, generation, escalation) is independently
testable and explainable, which matters for a live interview walkthrough.

**Alternatives considered:** A flatter `src/` with fewer subpackages — rejected
because it would blur the boundary between components the assignment
explicitly wants kept separate (see architecture doc section 25).

**Trade-off:** More boilerplate `__init__.py`/folders up front for a project
that starts empty, in exchange for a structure that won't need reshuffling
later.

## 2026-09-09 — Centralized config via `src/config.py` + `.env`, no per-module env reads

**Decision:** All environment-variable-driven settings (API keys, model
names, thresholds, paths, random seed) are read once into a frozen
`Settings` dataclass in `src/config.py`, exposed as a module-level `settings`
singleton.

**Reason:** The assignment requires configurable thresholds (not hard-coded)
and reproducible seeds; centralizing this in one place makes it auditable
and prevents drift where different modules read the same env var
differently.

**Alternatives considered:** `pydantic-settings` — deferred for now since
`pydantic` is already a dependency for later structured-output schemas, but
a plain frozen dataclass is simpler to explain live and has no additional
dependency surface for Phase 0.

**Trade-off:** Slightly less validation than a pydantic `BaseSettings` model
would give (e.g. no automatic type coercion errors), acceptable at this
stage since there are few settings.

## 2026-09-09 — golden set data path is git-tracked; raw/processed data paths are not

**Decision:** `.gitignore` excludes `data/raw/*` and `data/processed/*.{jsonl,csv}`
but leaves `data/golden/` untouched so the golden evaluation set can be
committed once created.

**Reason:** Raw Twitter data and large processed derivatives shouldn't be
committed (repo size, licensing), but the 150–250-example golden set is a
required deliverable and needs to ship with the repo for reproducibility.

**Alternatives considered:** Committing a small processed data subset too —
deferred to Phase 20 (reproducibility check), where the exact
evaluation-ready subset to ship will be decided.

**Trade-off:** None for the golden set once labeled — this only needs
noting in case it's obscured by `.gitignore` later.

## 2026-09-09 — Two-pass streaming scan instead of loading the full 2.8M-row CSV

**Decision:** `scripts/inspect_dataset.py` scans the raw CSV twice in
200k-row chunks: Pass A reads only `author_id`/`inbound`/`in_response_to_tweet_id`
to cheaply rank all 108 brand accounts by volume and pick a shortlist; Pass B
reads all columns once to compute global data-quality stats (missing values,
duplicates, date range) and buffers only the shortlisted brands' rows for
detailed per-brand stats and conversation sampling.

**Reason:** The full file is 516MB / 2.8M rows. Ranking brands first with a
narrow column read is fast (~10s) and lets the expensive full-column pass
avoid holding anything beyond a handful of brands' worth of rows in memory
(the buffered subset is a small fraction of the full dataset).

**Alternatives considered:** Loading the whole file into one DataFrame —
would likely still fit in memory on most machines (~2-3GB), but violates the
explicit instruction not to load the full dataset when a chunked approach is
straightforward, and would not generalize if the dataset were larger.

**Trade-off:** Two passes means the file is read from disk twice
(~2.5 minutes total on this machine) instead of once. Considered acceptable
since this script is run rarely (during inspection/setup), not in any hot path.

## 2026-09-09 — Customer-message-to-brand linkage uses @-mention regex, not full id-graph resolution

**Decision:** For Phase 1's per-brand `customer_messages` count, a customer
tweet is attributed to a brand if its text contains an `@handle` mention
matching that brand's account name (case-insensitive), rather than by
resolving `in_response_to_tweet_id` through a full tweet-id → author-id
index built over all 2.8M rows.

**Reason:** This is a well-known, simple convention for this dataset (a
customer's tweet addressed to support almost always @-mentions the handle)
and only requires a single regex pass over the `text` column — no need to
hold a multi-million-entry id map in memory just to answer "roughly how much
volume does each candidate brand have."

**Alternatives considered:** Building a global `tweet_id -> author_id` map
to resolve replies exactly — deferred to Phase 3 (conversation
reconstruction), where exact linkage actually matters for building the
support-case records the system will use as evidence. For Phase 1's purpose
(comparing candidate brands), the mention-based approximation is sufficient
and keeps the script simple.

**Trade-off:** A small number of customer tweets that reply to a brand
without repeating the @-mention in text (rare, since Twitter's reply UI
auto-inserts the mention) will be undercounted. Not material at this stage.

## 2026-09-09 — Selected brand: SpotifyCares

**Decision:** `SpotifyCares` is the one brand this entire project is built
around (`SELECTED_BRAND=SpotifyCares` in `.env`). Scope: 43,265 brand
tweets, 43,243 of which are direct replies ("conversations"), and 31,308
customer tweets that @-mention the account, out of the full ~2.8M-tweet
dataset (see `data/processed/brand_statistics.csv`). Only this subset will
be used for the knowledge index, intent discovery, and the golden set going
forward — not the full dataset.

**Reason:** Evaluated against the Phase 2 selection criteria (sufficient
volume, clear support interactions, diverse-but-understandable problems,
consistent historical resolutions, enough data for splits, minimal noise),
against the four other Phase 1 candidates (`docs/brand_shortlist.md`):
- SpotifyCares showed the richest *in-thread* troubleshooting content of any
  candidate — real multi-turn diagnostic exchanges (device/OS/version
  questions, a restart step, a follow-up when the issue recurs — see
  `data/processed/sample_conversations.txt`), not just "please DM us"
  deflections. This matters directly for grounded reply generation: the
  system can only ground replies in what the historical `brand_response`
  text actually contains.
- It's a single global consumer product (a streaming subscription service)
  with no jurisdiction-specific policy (unlike Tesco's UK alcohol law or
  Delta's aviation regulations), which lowers the risk of the LLM needing
  external policy knowledge it doesn't have and shouldn't invent.
- Its problem space is naturally bounded and maps cleanly onto the target
  8–15 intents: playback/streaming issues, account/login, billing/subscription,
  device compatibility, ads, password reset — without the sprawl seen in
  AmazonHelp (orders, devices, Prime, sellers, payments, fraud all mixed
  together) or Delta (many threads need real-time facts like current flight
  status that can't safely be part of a "grounded" answer).
- 43k conversations is comfortably enough for a knowledge index + a
  150–250-example golden set with room to spare, while being *small enough*
  to keep the whole pipeline easy to build, inspect, and explain live — in
  line with the instruction to prefer simple, reproducible solutions over
  maximizing scale.

**Alternatives considered:**
- `AmazonHelp` — largest volume (169k conversations) but rejected: too
  heterogeneous a problem space for a tight 8–15 intent taxonomy, and its
  size adds no real benefit here since 43k is already far more than needed.
- `AppleSupport` — largest reply-ratio and volume among tech brands, but
  rejected: sample threads are dominated by single-turn "DM us" deflections
  with little resolvable content, which would starve grounded generation of
  real evidence.
- `Tesco` — rich, human complaint text, but rejected: spans website/IT
  issues, delivery, and UK-specific in-store policy (e.g. Think25 alcohol
  verification), adding jurisdiction-specific policy risk without a
  corresponding benefit over SpotifyCares.
- `Delta` — good diversity, but rejected: many threads hinge on real-time,
  case-specific facts (flight status, confirmation numbers) that push most
  cases toward mandatory escalation, limiting how well the project can
  demonstrate the auto-handle path.

**Trade-off:** Smaller absolute volume than Amazon/Apple/Delta/Tesco means
less headroom if a much larger knowledge base turns out to be needed later,
and Spotify's intents (streaming/technical) are narrower in scope than a
multi-category retailer's — acceptable since the assignment explicitly asks
for a justified subset, not maximum scale. Per the Phase 2 instruction, this
brand will not be changed unless a serious data problem surfaces during
later phases.

## 2026-09-09 — Exact thread reconstruction via a lightweight full-dataset id graph

**Decision:** `src/data/conversation_builder.py` builds a `TweetGraph` from
the full 2.8M-row dataset, but only 5 light columns (no `text`): a chunked
read is concatenated into id→author/inbound/parent/children dicts. BFS out
from every SpotifyCares-authored tweet collects the exact set of tweet ids
in those threads (capped at 200 nodes / 15 hops per thread as a safety
valve — 59 of 43,265 threads hit this cap). A second chunked pass then
fetches full rows (with text) for only that ~92k-id subset.

**Reason:** Phase 1's mention-regex approach was a fine approximation for
*ranking* brands, but is not good enough for *reconstructing* threads:
sampling showed a customer's own thread-opening tweet often doesn't
@-mention the brand at all (e.g. "Spotify keeps crashing my PC any
suggestions lads?", only reachable by following `in_response_to_tweet_id`).
Exact graph traversal is required for correctness here.

**Alternatives considered:** Holding full text for all 2.8M rows in memory
to avoid a second pass — rejected as unnecessary memory cost when only
~92k of 2.8M rows are ever needed; the light-columns-first design keeps
peak memory to a small fraction of the full dataset while still giving
exact (not approximate) reconstruction.

**Trade-off:** Two full file reads instead of one (~15s combined) for the
light index and the targeted fetch. Acceptable for a script that runs
rarely (whenever the processed dataset needs rebuilding).

## 2026-09-09 — One support case per brand reply tweet, walking past multi-part replies

**Decision:** Every `SpotifyCares` reply tweet that resolves to a customer
ancestor becomes its own case (`case_id = case_{tweet_id}`). When resolving
the customer ancestor, any brand-authored tweets in between (e.g. a
numbered "(1/2)" then "(2/2)" reply) are walked past and recorded in
`source_ids` for traceability, not merged into one case.

**Reason:** Merging multi-part replies into a single case would require
guessing which brand tweets belong together (no explicit grouping field
exists), adding real complexity for a modest fraction of cases. Keeping
one case per brand reply is simple, matches Phase 3's "prefer simple
implementations" guidance, and both parts still end up in the case pool as
independently useful (customer_message, brand_response) evidence pairs.

**Alternatives considered:** Concatenating consecutive same-thread brand
replies into one `brand_response` — deferred; would help grounding slightly
for split replies but adds real complexity for uncertain benefit.

**Trade-off:** A customer message can be the `customer_message` of more
than one case (each with a different, partial `brand_response`). Measured
at 7.38% of cases sharing a `customer_tweet_id` with another case (see next
entry — this also captures a smaller, separate data-quality issue, not only
legitimate multi-part replies).

## 2026-09-09 — Known limitation: some in_response_to_tweet_id links are semantically incoherent

**Finding (not a bug):** Spot-checking `support_cases_sample.jsonl` found
case `case_1184204`, whose `brand_response` ("...your full payment card
info...") does not match its `customer_message` ("booooooo. You're ignoring
me."). Tracing the raw rows showed the customer tweet's `response_tweet_id`
lists **two** children (`1184204,1184206`) — SpotifyCares' numbered "2. ..."
reply is threaded to a customer tweet it doesn't actually answer, most
likely a scraping/threading artifact in the original dataset, not a defect
in `build_cases`' graph traversal (confirmed by reading the raw CSV rows
directly around this id).

**Decision:** Do not attempt to detect or repair semantically-incoherent
thread links in Phase 3. `pct_cases_sharing_a_customer_tweet` (7.38%,
`data/processed/preprocessing_stats.json`) is reported as an upper-bound
proxy for this phenomenon (it also includes legitimate multi-part replies,
which look the same structurally), and this finding is carried forward for
Phase 15 (failure analysis) and Phase 16 ("what is misleading about my
headline number") rather than papered over now.

**Reason:** Detecting this reliably needs semantic judgment (does the reply
text actually address the customer text?), which is exactly what later
phases (retrieval relevance, LLM-judge groundedness scoring) are built to
evaluate. Building an ad-hoc heuristic filter in the cleaning step would be
guessing, and could silently discard legitimate cases.

**Trade-off:** A small fraction of `support_cases.jsonl` records are
structurally valid (correct graph traversal of the source data) but
semantically wrong. This is a known, quantified limitation, not a hidden
one — it should be mentioned in the final report's limitations section.

## 2026-09-09 — Intent discovery via TF-IDF+KMeans clustering, not an LLM

**Decision:** `src/intents/discovery.py` uses TF-IDF (5000 features,
unigrams+bigrams, `min_df=5`) + KMeans (k=30, fixed seed) over the
knowledge-split customer messages to surface candidate themes, rather than
asking an LLM to propose/cluster intents.

**Reason:** `LLM_API_KEY` is not configured for this project. Clustering
is also fully deterministic and free to re-run, and — usefully — the same
TF-IDF machinery gets reused for the Phase 7 TF-IDF+LogisticRegression
baseline, so this isn't throwaway infrastructure.

**Alternatives considered:** Manually skimming a random sample of
messages with no clustering assistance — would work but is much slower
and more subjective for finding 30 candidate themes across 36,723
messages; clustering gives a structured starting point that a human then
merges/prunes (exactly what the plan's "use clustering/LLM analysis only
as assistance" instruction asks for).

**Trade-off:** TF-IDF clusters group by lexical similarity (shared words),
not semantic issue-type — e.g. iOS/Android/desktop technical complaints
formed separate clusters purely because of device-name vocabulary, and had
to be manually merged into one `playback_technical_issue` intent. An
LLM-assisted discovery pass might group by meaning more directly; this is
worth revisiting if `LLM_API_KEY` becomes available.

## 2026-09-09 — 12 intents; 3 have no automated weak-label coverage

**Decision:** Final taxonomy (`src/intents/labels.py`, reasoning in
`docs/intent_definitions.md`) has 12 intents. 9 are backed by one or more
of the 30 discovery clusters and get weak labels for Phase 7 training
(18,100 of 36,723 knowledge messages, 49%). 3 — `account_security_compromise`,
`account_data_loss`, `cancellation_or_refund_request` — are grounded in
real examples that appeared *inside* other clusters' example lists but
never dominated a cluster of their own at k=30, so they get zero automated
weak-label coverage; they still exist for manual golden-set labeling
(Phase 5) and the LLM classifier (Phase 8).

**Reason:** These 3 are exactly the kind of high-risk, escalation-relevant
categories the assignment calls out (potential fraud, data loss, explicit
cancel/refund requests) — dropping them for lack of a clean cluster would
mean the taxonomy under-represents the cases where correct escalation
behavior matters most. Forcing them onto an unrelated cluster instead
(just to get weak-label coverage) would inject label noise elsewhere.

**Alternatives considered:** A supplementary keyword-regex pass (e.g.
"hack", "compromised", "cancel", "refund") to weakly-label these 3 intents
too — deferred; if Phase 7's baseline needs better coverage of them it can
be added then, scoped to that phase rather than Phase 4.

**Trade-off:** The Phase 7 TF-IDF+LogisticRegression baseline will have
zero training signal for these 3 intents and is expected to never predict
them — an explicit, documented limitation (and a natural input to Phase 16
"what is misleading about my headline number?"), not an oversight.

## 2026-09-09 — Roughly half of knowledge messages discarded as clustering noise

**Decision:** 7 of 30 discovery clusters (18,623 of 36,723 knowledge
messages, ~51%) are mapped to `None` in `CLUSTER_TO_INTENT` — discarded
from the weak-labeled training set rather than assigned to the
closest-seeming intent.

**Reason:** These clusters' top TF-IDF terms were generic, dataset-wide
vocabulary ("spotify", "https", "help", "don't") rather than a specific
topic, and their sampled example messages span clearly unrelated subjects
(a technical complaint next to a thank-you next to a feature idea). This
includes the single largest cluster (10,003 messages, 27% of the knowledge
split) — its size comes from being a catch-all for messages without a
strong distinguishing topic, not from being one coherent intent.

**Alternatives considered:** Assigning the largest generic cluster to
`playback_technical_issue` anyway, since a visible chunk of its examples
were technical — rejected: spot-checking showed real mixed content (ads
complaints, artist-attribution requests, thank-yous), and forcing the
label would measurably dilute that intent's training-data precision for
uncertain benefit.

**Trade-off:** Only 49% of the knowledge pool ends up with a weak label —
still 18,100 examples, far more than Phase 7 needs, so no practical
shortage. The discarded half is a real property of this dataset (a lot of
Twitter replies to a support account are generic/off-topic chatter, not
clean single-issue reports) worth stating plainly rather than hiding
behind a forced 100%-coverage labeling.

## 2026-09-09 — Golden set sampling uses transform-only clustering + keyword search, never re-fits on golden_pool

**Decision:** To stratify the 293 golden candidates across all 12 intents,
`scripts/sample_golden_candidates.py` re-fits the identical Phase 4
TF-IDF+KMeans model on `knowledge`-split data (same params/seed, so the
clusters are bit-for-bit identical), then only calls `.transform()`/
`.predict()` on `golden_pool` messages — never `.fit()`. The 3 intents with
no dedicated cluster get candidates via a separate keyword/regex search
over `golden_pool` text instead.

**Reason:** Phase 5 needs `golden_pool` messages roughly bucketed by
likely intent so sampling can guarantee coverage of rare intents — but
`golden_pool` must never influence how any model is *fit*, per the
project's core leakage rule. Transform-only projection through an
already-frozen model is a read operation, not a fit; it cannot leak
information back into the model.

**Alternatives considered:** Pure random sampling with no stratification —
rejected, since Phase 5 explicitly requires including rare-but-important
intents, and 3 of the 12 intents have zero representation in the automated
clustering signal at all (see the Phase 4 entry above), so pure random
sampling from 6,480 cases would likely surface very few or zero examples
of `account_security_compromise`, `account_data_loss`, and
`cancellation_or_refund_request`.

**Trade-off:** None significant — the hint is explicitly documented as a
sampling aid only; every candidate was still read and independently
labeled by hand (see `docs/golden_set_methodology.md`), and about a third
of hints turned out to be wrong on inspection, which is expected and fine
given the hint's only job is getting a diverse pool of messages in front
of a human, not producing correct labels itself.

## 2026-09-09 — Golden action labels follow a documented rubric, not a per-system output

**Decision:** `gold_action` (AUTO_HANDLE/ESCALATE) was assigned by
applying the plan's stated escalation principles (Phase 11: fraud,
payment disputes, repeated/unresolved issues, low-confidence/ambiguous
cases, high-risk categories) directly to each message's content and
context — not derived from any classifier or heuristic score, since no
escalation engine exists yet at this point in the project. Two refinements
were applied consistently rather than left to case-by-case judgment: (1)
within `account_data_loss`, lost downloaded/offline songs (a
well-precedented, reliably-fixable pattern in the historical data) were
auto-handled on first occurrence while lost playlists/whole-library data
were always escalated; (2) every non-English message was escalated,
regardless of its apparent severity, since the retrieval/generation
pipeline is grounded in English historical evidence.

**Reason:** These labels are the ground truth Phase 11's actual escalation
engine will later be evaluated against — they have to come from first
principles, not from a system that doesn't exist yet, or the evaluation
would be circular. The two consistency refinements exist so the golden
set doesn't quietly depend on ad-hoc per-message judgment calls that would
be impossible to explain or reproduce.

**Alternatives considered:** Judging every non-English message purely on
its content's apparent severity (escalating only the severe ones) —
rejected for simplicity and consistency: correctly judging severity in a
message you can only partially read is itself an argument for escalating,
not a reason to skip it.

**Trade-off:** The non-English-always-escalates rule is deliberately
conservative and will escalate some genuinely low-stakes non-English
messages (e.g. a mild feature request) — accepted as a simplicity/safety
trade-off, and stated explicitly rather than left implicit.

## 2026-09-09 — Label consistency checked via blind self-review, not a second human

**Decision:** Since no second human labeler is available in this
environment, label consistency was checked by blindly re-labeling 25
random golden examples (message text only, original labels hidden) and
comparing against the saved labels: 25/25 (100%) agreement on both intent
and action (`data/golden/consistency_check_results.json`).

**Reason:** The plan calls for a second-human consistency check "if
possible" — it isn't possible here, so the closest honest substitute is a
blind self-consistency check, explicitly documented as measuring rubric
*consistency* (same annotator, same rules, reapplied blind) rather than
label *correctness*, which only independent review could establish.

**Alternatives considered:** Skipping the check entirely — rejected, since
even a self-consistency check catches careless/contradictory labeling,
which is a real failure mode worth ruling out.

**Trade-off:** 100% agreement is a weaker signal than genuine
inter-annotator agreement would be (it can't catch a systematic bias the
one annotator holds throughout). This is stated plainly in
`docs/golden_set_methodology.md` rather than presented as equivalent to
real human validation.

## 2026-09-09 — Majority baseline's class comes from training distribution, not the golden set

**Decision:** `baselines/majority.py` determines its single predicted
class (`playback_technical_issue`) from the Phase 4 weak-labeled
*knowledge-split* intent distribution (`data/processed/intent_distribution.json`),
never from `golden_set.jsonl`'s own label distribution, even though the
plan's Phase 6 text only says "predict the most common intent for every
message in the golden set" (which could be read either way).

**Reason:** Keeping every baseline's fitting/decision-making restricted to
non-golden data, and evaluating once on golden, is the same rule Phase 7
(TF-IDF+LogReg) and every later classifier follow — applying it here too
means the majority baseline is a fair, directly comparable floor rather
than a special case that gets to peek at the answer key it's being scored
against.

**Alternatives considered:** Computing the mode of `golden_set.jsonl`
directly — simpler, and in this instance would have produced the same
predicted class anyway (`playback_technical_issue` is also the largest
single intent within the capped golden set), but rejected as the general
rule since it would silently break if the golden set's composition ever
changed, and is inconsistent with how every other baseline in this
project is required to work.

**Trade-off:** None material here since both approaches happen to agree
on the predicted class this time; recorded because the reasoning
(training-only decisions) matters more going forward than this particular
outcome.

## 2026-09-09 — Shared evaluate_intents.py built one phase early

**Decision:** `evaluation/evaluate_intents.py` (accuracy, macro F1,
per-intent precision/recall/F1, confusion matrix) was built now, during
Phase 6, and used by `baselines/majority.py`, rather than waiting for
Phase 13's evaluation harness.

**Reason:** Phase 7 (TF-IDF+LogReg) needs the identical set of metrics
computed the identical way for the two baselines to be genuinely
comparable — duplicating this logic in `baselines/tfidf_classifier.py`
next phase, only to consolidate it later in Phase 13 anyway, would mean
writing it twice and risking the two computations subtly diverging.

**Alternatives considered:** Inlining metric computation directly in
`baselines/majority.py` — rejected for the duplication reason above; this
is a small, single-purpose, easily-testable module, not scope creep into
Phase 13's actual harness (which will additionally handle retrieval,
reply, and escalation metrics, running the full agent end-to-end).

**Trade-off:** None — this is exactly the kind of shared utility the
"keep functions small and testable" project guideline calls for.

## 2026-09-09 — TF-IDF baseline uses class_weight="balanced"

**Decision:** `baselines/tfidf_classifier.py`'s `LogisticRegression` uses
`class_weight="balanced"`, and the regularization strength `C` is chosen
from `{0.1, 1.0, 10.0}` by validation macro F1 (not accuracy).

**Reason:** The training distribution is severely imbalanced
(`playback_technical_issue` is ~41% of weakly-labeled data,
`customer_service_feedback` ~1%). An unweighted model would mostly relearn
majority-class behavior and this baseline would stop being a meaningful
midpoint between the majority baseline and the AI classifier. Selecting
`C` by macro F1 (not accuracy) keeps the tuning objective consistent with
what actually matters for this project — per-intent performance, not just
overall correctness, matching the "macro F1 matters because accuracy can
hide poor performance on minority intents" principle from the architecture
doc.

**Alternatives considered:** A full grid search over TF-IDF parameters too
(max_features, ngram_range) — rejected for Phase 7 as unnecessary
complexity; a single reasonable fixed TF-IDF config plus a small,
explainable `C` sweep is enough to demonstrate the pipeline and stays
within "prefer simple implementations that can be explained in an
interview."

**Trade-off:** Validation macro F1 (0.72) is noticeably higher than golden
macro F1 (0.51) — expected, since validation is drawn from the same
weakly-labeled, noisier distribution as training (no manual verification,
no deliberately-included hard cases, and it never contains the 3
intents that got zero weak-label coverage). This gap itself is a useful
data point for Phase 16 ("what is misleading about my headline number"):
the validation score alone would overstate how well this baseline
actually performs.

## 2026-09-09 — AI intent classifier uses Google Gemini's free tier, not Claude

**Decision:** `src/intents/classifier.py` calls Google's Gemini API
(`google-genai` SDK, `gemini-3.6-flash` model) instead of Anthropic Claude,
even though `.env.example`'s original default (from Phase 0) was
`claude-sonnet-5`.

**Reason:** No Anthropic API key was available in this environment, and
Anthropic requires a billing method on file to issue one. The user chose
to use Gemini's free tier instead of adding a paid key. `LLM_API_KEY`/
`LLM_MODEL` were already provider-agnostic names (Phase 0), so this only
meant swapping the client implementation and the model string, not
restructuring config.

**Alternatives considered:** Groq's free tier (open-weight models) and a
local model via Ollama — both viable; Gemini was chosen by the user, and
its native structured-output support (JSON schema with enum constraints)
made it a clean fit for "never invent a new intent label."

**Trade-off:** The project's config default no longer matches Claude. This
is stated explicitly here rather than silently left inconsistent with the
architecture doc's original example — the config remains provider-agnostic
so switching back (or adding Claude as an option) only touches
`.env`/`classifier.py`, not the rest of the pipeline.

**Note:** `gemini-2.5-flash` (the initially planned model) returned a 404
on the first real API call — "no longer available to new users," with the
error message itself recommending `gemini-3.6-flash`. Caught by an actual
smoke-test call before running the full golden set, not by trusting
documentation alone (docs and the live API disagreed on model naming by
the time of implementation).

## 2026-09-09 — "Never invent a label" enforced via JSON schema enum, not just prompt wording

**Decision:** `IntentPrediction` (the Pydantic model given to Gemini as
`response_format.schema`) types `intent` as a dynamically-built `Enum` over
exactly the 12 `INTENTS` keys, so the JSON schema sent to the model
contains an `enum` constraint — an out-of-vocabulary label fails Gemini's
structured-output validation (or, if it somehow slipped through, fails
`IntentPrediction.model_validate_json` on our side) rather than silently
returning a string that isn't one of the 12 intents.

**Reason:** The plan requires the classifier to "avoid inventing new
intent labels." A prompt instruction alone is a request the model can
still ignore; a schema constraint is enforced by the response-generation
mechanism itself, which is meaningfully stronger.

**Alternatives considered:** Prompt-only enforcement plus a post-hoc
string-match validation step — rejected as strictly weaker for the same
implementation cost; there's no reason not to use the schema constraint
when the API supports it natively.

**Trade-off:** None identified.

## 2026-09-09 — Confidence score doubles as the ambiguity signal; no separate "ambiguous" flag

**Decision:** The classifier's system prompt instructs the model to use
confidence below 0.5 for genuinely ambiguous, off-topic, or non-English
messages, rather than adding a separate boolean `ambiguous` field to the
output schema. `MIN_INTENT_CONFIDENCE` (already in `src/config.py` since
Phase 0) is the threshold Phase 11's escalation logic will read.

**Reason:** The plan's escalation signals explicitly include "low intent
confidence" as its own criterion — a single confidence score already
carries this information, and a redundant second field would just be
two representations of the same underlying judgment with no clear rule
for resolving disagreement between them.

**Alternatives considered:** Adding `ambiguous: bool` anyway for
explicitness — rejected; smoke-testing (see below) confirmed the model
reliably drops confidence for non-English input specifically because the
prompt asked it to, so the single-field design works as intended.

**Trade-off:** None identified — verified via smoke test before committing
to the full golden-set run: a non-English message scored confidence 0.45
with reasoning explicitly citing the language barrier as the reason.

## 2026-09-09 — Local raw-prediction cache to avoid re-spending API calls

**Decision:** `classify_golden_set()` reads/writes
`artifacts/predictions/ai_classifier_raw_cache.jsonl`, keyed by golden
example id, and only calls the API for ids missing from the cache or
whose cached entry has a non-null `error`. A 2-second pacing delay runs
between calls.

**Reason:** Classifying 229 examples against a live free-tier API takes
real wall-clock time and consumes free-tier quota; re-running the driver
during development (e.g. after fixing a bug in metric computation
downstream) shouldn't have to re-classify examples that already succeeded.
The pacing delay is a courtesy against free-tier rate limits, on top of
the classifier's own per-call retry/backoff for transient failures.

**Alternatives considered:** No caching, re-run everything every time —
rejected as wasteful given the classifier itself is deterministic-ish
(temperature not explicitly pinned) but expensive to re-query, and
reproducibility doesn't require re-hitting the network if a cached,
successful result already exists.

**Trade-off:** The cache can go stale if the prompt or schema changes
without also being cleared — acceptable since it's a local, gitignored-if-
large, easily-deleted file, not a source of truth.

## 2026-09-10 — Switched Phase 8's model twice more after hitting per-model free-tier quotas

**Decision:** Final model: `gemini-3.5-flash-lite` (not `gemini-3.6-flash`,
the model chosen when Phase 8 was first implemented).

**Reason:** Running the classifier against the full 229-example golden set
surfaced two real problems undocumented until they were hit live:
1. `gemini-2.5-flash` (the originally planned default) 404'd on the very
   first real call — "no longer available to new users" (already recorded
   above).
2. `gemini-3.6-flash` worked for ~30-56 calls, then started failing almost
   every subsequent call with a 429 `quota exceeded... limit: 20` error.
   Increasing the pacing delay between calls (2s → 3.5s, comfortably under
   a 20-requests/minute reading of that message) did not fix it — the same
   error persisted for many minutes regardless of pacing, which only makes
   sense if the limit is a **daily** quota, not per-minute, despite the
   error text's "retry in 42s" phrasing (misleading — that's a generic
   retry hint, not the actual quota reset time).
3. Switching to `gemini-3.5-flash-lite` immediately worked with no 429s
   across a 10-call rapid-fire stress test, confirming free-tier quota is
   tracked **per model**, not per API key/project — `flash-lite` variants
   get a separate, far more generous allotment than the newer `flash`
   tier.

**Alternatives considered:** Waiting out the `gemini-3.6-flash` quota
(unknown reset time, possibly up to 24h) — rejected, since switching
models was immediately verifiable and unblocked the run in minutes instead
of an indefinite wait. Batch API (mentioned in Gemini's own docs as having
separate, more generous limits) — not pursued; `interactions.create` was
already working end-to-end and switching APIs entirely was unnecessary
once the per-model quota theory was confirmed correct.

**Trade-off:** `flash-lite` is a smaller/cheaper model than `flash` —
plausibly slightly less capable at nuanced classification. Spot-checked
before committing to the full run: 10/10 correct classifications across a
manually-verified mix of all 12 intents, so no accuracy concern observed
in practice for this task. The `ai_classifier_raw_cache.jsonl` entries
from the two earlier (broken/mixed-model) runs were deleted rather than
partially reused, so the final result set is from one consistent model,
not silently blended across three.

## 2026-09-10 — Embeddings run locally, not via an LLM API

**Decision:** `src/retrieval/embeddings.py` uses a local
`sentence-transformers` model (`all-MiniLM-L6-v2`, already the Phase 0
config default) rather than an embeddings API endpoint from Gemini or any
other provider.

**Reason:** The project already depends on one rate-limited free-tier LLM
API for intent classification (Phase 8), where quota limits turned out to
be a real, time-consuming obstacle (see the entry above). Embeddings don't
need an LLM's reasoning capability — a local model avoids a second network
dependency, has no rate limits on ~37k documents, downloads once (~90MB)
and caches locally, and keeps retrieval fully reproducible offline.

**Alternatives considered:** Gemini's embedding endpoint
(`gemini-embedding-2-preview`, confirmed free-tier in Phase 8's model
research) — rejected given the demonstrated fragility of this project's
free-tier LLM quota; embedding 36,723 documents through a rate-limited API
would risk the same multi-hour quota problem, for a task a small local
model handles in ~2 minutes with no external dependency at all.

**Trade-off:** `all-MiniLM-L6-v2` (384 dimensions) is a smaller, older
embedding model than current API-hosted options, and downloads ~90MB on
first use. Retrieval quality observed in practice is strong (mean top-1
cosine similarity 0.858 across the golden set; a spot-checked
`account_security_compromise` query correctly retrieved other
hacked-account cases at 0.70+ similarity), so this trade-off did not show
up as a real limitation for this project's scale and domain.

## 2026-09-10 — Exact FAISS search (IndexFlatIP), not an approximate index

**Decision:** `src/retrieval/index.py` uses `faiss.IndexFlatIP` (exact
brute-force inner-product search over L2-normalized vectors, i.e. exact
cosine similarity) rather than an approximate index like IVF or HNSW.

**Reason:** The knowledge pool is ~37k documents at 384 dimensions —
small enough that exact search completes in well under a second per
query. Approximate indexes trade a small amount of recall for speed at
much larger scale (millions of vectors); at this project's scale that
trade-off has no benefit and would only add tuning complexity (index
parameters, recall/speed trade-off knobs) with nothing to show for it —
directly against "prefer simple implementations that can be explained in
an interview."

**Alternatives considered:** `IndexIVFFlat` — rejected as unnecessary at
this scale; would need its own training step and parameter tuning
(`nlist`, `nprobe`) for a speed gain that isn't needed.

**Trade-off:** Would not scale gracefully to a much larger knowledge base
(millions of cases) without revisiting this choice — acceptable and
explicitly noted, since the project's own scope (one brand, a justified
subset, not the full ~3M-tweet dataset) means this ceiling is unlikely to
be hit.

## 2026-09-10 — Retrieval quality measured via similarity stats + an intent-agreement proxy, not manual relevance labels

**Decision:** `evaluation/evaluate_retrieval.py` reports two things: (1)
similarity score statistics (top-1 and average-top-k) across all golden
queries, and (2) "intent-agreement@k" — the fraction of top-k retrieved
cases whose Phase 4 weak intent label matches the query's Phase 5
`gold_intent`. No new manual relevance-labeling pass was created.

**Reason:** The plan says to measure retrieval quality "where feasible"
and explicitly allows stating a limitation if formal relevance labels are
hard to construct. Manually judging relevance for 229 queries × 5 retrieved
cases each (1,145 judgments) would be a large new labeling effort with its
own leakage risk (it would effectively be grading retrieval against
labels created by looking at retrieval's own output). The two metrics used
instead are both derived from data that already exists for other reasons
(Phase 4/5 labels), at zero additional labeling cost.

**Alternatives considered:** Skipping retrieval evaluation entirely (the
plan permits stating retrieval labels are infeasible) — rejected, since a
reasonable proxy was available cheaply; a full manual relevance study —
deferred as out of scope for this phase, could be added later if time
permits (Phase 19 "what we'd do with one more week" candidate).

**Trade-off:** The intent-agreement proxy inherits the Phase 4/7 weak-label
coverage gap by construction — it reads exactly 0.0 for the 3 intents with
no weak-label coverage, which looks like a retrieval failure but isn't
(verified by spot-checking: `account_security_compromise` queries retrieve
genuinely relevant hacked-account cases at 0.70+ similarity; those cases
just don't carry a `weak_intent` value the proxy can compare against).
Documented explicitly in the README and here rather than left as an
unexplained low number — an example of the project's own "misleading
headline number" principle (Phase 16) showing up one intent-taxonomy layer
below where it was first observed in Phase 7.
