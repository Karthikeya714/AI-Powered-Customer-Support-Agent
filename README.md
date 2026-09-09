# Hiver SDE Intern — Brand-Specific AI Customer Support Agent

Take-home assignment: build an offline prototype that takes a new customer
support message and (1) classifies its intent, (2) retrieves similar
historical support cases for one brand, (3) drafts a reply grounded in that
evidence, and (4) decides whether to auto-handle the case or escalate it to
a human — then rigorously evaluates how well each step works.

This is a research/evaluation prototype, not a production system. No LLM is
trained from scratch; the Twitter support history is used as retrieval
knowledge, not training data for a new model.

**Status:** Phase 0 (project setup) complete. Later sections of this README
(dataset, brand selection, results, reproduction steps) will be filled in as
each phase lands — see `Hiver_SDE_Intern_Project_Plan_for_Claude_Code.txt`
for the full phase plan and `DECISION_LOG.md` for engineering decisions.

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

## Running tests

```bash
pytest
```

## Roadmap

See `Hiver_SDE_Intern_Project_Plan_for_Claude_Code.txt` for the full 20-phase
plan. Phases are implemented one at a time and in order; this README will
grow a "Data preparation", "How to build index", "How to run agent", "How to
run evaluation", and "Headline results" section as those phases are built.
