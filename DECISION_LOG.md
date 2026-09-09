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
