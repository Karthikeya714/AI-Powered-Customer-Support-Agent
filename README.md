# Hiver SDE Intern — Brand-Specific AI Customer Support Agent

Take-home assignment: build an offline prototype that takes a new customer
support message and (1) classifies its intent, (2) retrieves similar
historical support cases for one brand, (3) drafts a reply grounded in that
evidence, and (4) decides whether to auto-handle the case or escalate it to
a human — then rigorously evaluates how well each step works.

This is a research/evaluation prototype, not a production system. No LLM is
trained from scratch; the Twitter support history is used as retrieval
knowledge, not training data for a new model.

**Status:** Phase 0 (setup) through Phase 6 (majority-class baseline)
complete. Later sections of this README (results, reproduction steps)
will be filled in as each phase lands — see
`Hiver_SDE_Intern_Project_Plan_for_Claude_Code.txt` for the full phase plan
and `DECISION_LOG.md` for engineering decisions.

## Scope

**Selected brand: SpotifyCares.** Chosen from a 5-candidate shortlist after
inspecting the full dataset — see `docs/brand_shortlist.md` for the
comparison and `DECISION_LOG.md` for the full reasoning. From here on, the
project is built entirely around this one brand's data:

- 43,265 brand (support) tweets, 43,243 of them direct replies
- 31,308 customer tweets that @-mention the account
- Out of the full ~2.8M-tweet / 108-brand dataset — the rest is not used

This subset is what gets cleaned into support cases (Phase 3), used to
discover intents (Phase 4), and split into knowledge/golden data (Phase 5+).

## Project layout

```
data/
    raw/         # original dataset files (not committed)
    processed/   # cleaned support cases, brand stats (not committed — large/derived)
    golden/      # manually labelled golden evaluation set (committed)
src/
    config.py    # settings + logging, read by every other module
    data/        # loading, cleaning, conversation reconstruction
    intents/     # intent definitions + classifier
    retrieval/   # embeddings + vector index + retriever
    generation/  # grounded reply generation
    escalation/  # auto-handle vs escalate decision
baselines/       # majority-class and TF-IDF+LogReg intent baselines
evaluation/      # evaluation harness, LLM judge, human agreement analysis
scripts/         # one-off/CLI scripts (dataset inspection, index building, ...)
app/             # simple demo UI
tests/           # pytest suite
artifacts/       # saved metrics, predictions, plots, judge results
docs/            # intent definitions, golden set methodology, failure analysis
```

## Setup

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # then fill in any API keys you have
```

## Configuration

All configuration is environment-variable driven (see `.env.example`) and
loaded centrally in `src/config.py` via `settings`. Nothing else in the
codebase should read `os.environ` directly.

Key variables:

| Variable | Purpose | Default |
|---|---|---|
| `LLM_API_KEY` | API key for the LLM used in intent classification / generation / judging (added Phase 8+) | — |
| `LLM_MODEL` | LLM model name | `claude-sonnet-5` |
| `EMBEDDING_MODEL` | Embedding model for retrieval (added Phase 9+) | `all-MiniLM-L6-v2` |
| `SELECTED_BRAND` | The single brand this project targets (set in Phase 2) | — |
| `TOP_K` | Number of historical cases retrieved per query | `5` |
| `MIN_INTENT_CONFIDENCE` | Escalation threshold, tuned on validation data | `0.6` |
| `MIN_RETRIEVAL_SIMILARITY` | Escalation threshold, tuned on validation data | `0.5` |
| `RANDOM_SEED` | Seed for all deterministic sampling | `42` |

## Data preparation

This project uses the [Customer Support on Twitter](https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter)
dataset (~2.8M tweets, 108 brand support accounts). It is **not** committed
to this repo (516MB, and Kaggle's license doesn't permit redistribution).

1. Download `twcs.csv` from Kaggle (requires a free Kaggle account/API token).
2. Place it at `data/raw/customer-support-on-twitter/twcs.csv`.
3. Run the dataset inspection script:

```bash
python -m scripts.inspect_dataset
```

This streams the file in chunks (never loading all ~2.8M rows into memory
at once) and writes:

- `data/processed/brand_statistics.csv` — per-brand tweet/conversation counts
- `data/processed/dataset_summary.json` — schema, missing values, duplicates, date range
- `data/processed/sample_conversations.txt` — reconstructed example threads per candidate brand

See `docs/brand_shortlist.md` for the resulting shortlist of 5 candidate
brands with supporting evidence (Phase 1 deliverable — brand *selection*
happens in Phase 2).

Once inspected, build the cleaned, reconstructed support-case dataset for
the selected brand (SpotifyCares):

```bash
python -m scripts.build_processed_dataset
```

This does exact conversation-thread reconstruction (id-graph traversal, not
regex mentions) restricted to SpotifyCares' ~92k relevant tweets, and writes:

- `data/processed/support_cases.jsonl` — all 43,203 normalized support cases (gitignored — regenerate with the command above)
- `data/processed/support_cases_sample.jsonl` — 50 random cases, human-inspectable, committed
- `data/processed/preprocessing_stats.json` — cleaning/filtering counts, multi-turn rate, knowledge/golden_pool split sizes

Each case looks like:

```json
{
  "case_id": "case_1277353",
  "conversation_id": "conv_1277350",
  "brand": "SpotifyCares",
  "customer_message": "...",
  "brand_response": "...",
  "context": [{"speaker": "customer", "text": "...", "tweet_id": 1277350}, ...],
  "customer_tweet_id": 1277349,
  "brand_tweet_id": 1277353,
  "source_ids": [1277350, 1277348, 1277349, 1277351, 1277352, 1277353],
  "split": "knowledge"
}
```

`split` is `"knowledge"` (used for the retrieval index / classifier
training) or `"golden_pool"` (held out entirely — Phase 5 samples the
manually-labelled golden evaluation set only from this pool, so it never
leaks into the system being evaluated).

Next, discover intent themes and (once the taxonomy is defined) weakly
label the knowledge pool for baseline training:

```bash
python -m scripts.build_intent_dataset
```

This TF-IDF+KMeans-clusters the knowledge-split customer messages (no LLM
call — no API key is required for this step) and writes
`data/processed/intent_discovery_clusters.json`. The 12-intent taxonomy
derived from reading that report lives in `src/intents/labels.py`, with
full reasoning in `docs/intent_definitions.md`. Re-running the script
applies the taxonomy's cluster→intent mapping to produce
`data/processed/support_cases_with_intents.jsonl` (weak labels, gitignored
— regenerate with the command above) and
`data/processed/intent_distribution.json`.

Finally, build the golden evaluation set — 229 manually labeled examples
sampled exclusively from `golden_pool` (never touched by the steps above):

```bash
python -m scripts.sample_golden_candidates   # stratified candidate sampling from golden_pool
python -m scripts.build_golden_set           # merge with manual labels -> golden_set.jsonl / .csv
```

`data/golden/golden_set.jsonl` is the ground truth the whole system will
eventually be scored against (intent classification, retrieval, generation,
and escalation). See `docs/golden_set_methodology.md` for the full sampling
strategy, the escalation-action rubric applied while labeling, and the
blind self-consistency check.

### Baselines

Every baseline/classifier is evaluated once, on the golden set only.
Start with the deliberately trivial majority-class baseline:

```bash
python -m baselines.majority
```

Predicts `playback_technical_issue` (the most frequent intent in the
Phase 4 weak-labeled *training* distribution — never computed from the
golden set itself) for every golden example. Writes
`artifacts/predictions/majority_baseline_predictions.jsonl` and
`artifacts/metrics/majority_baseline_metrics.json`.

**Result: 12.2% accuracy, 0.018 macro F1** — deliberately weak, since the
golden set was built to not over-represent the majority class (see
`docs/golden_set_methodology.md`). This is the floor later
classifiers are compared against.

## Running tests

```bash
pytest
```

Tests run against a small synthetic CSV fixture (`tests/test_data.py`), not
the real dataset, so they pass without downloading anything.

## Roadmap

See `Hiver_SDE_Intern_Project_Plan_for_Claude_Code.txt` for the full 20-phase
plan. Phases are implemented one at a time and in order; this README will
grow a "Data preparation", "How to build index", "How to run agent", "How to
run evaluation", and "Headline results" section as those phases are built.
