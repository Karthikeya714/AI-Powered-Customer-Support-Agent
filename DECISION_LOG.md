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
