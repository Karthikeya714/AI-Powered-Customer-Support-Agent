# Hiver SDE Intern — Brand-Specific AI Customer Support Agent

Take-home assignment: build an offline prototype that takes a new customer
support message and (1) classifies its intent, (2) retrieves similar
historical support cases for one brand, (3) drafts a reply grounded in that
evidence, and (4) decides whether to auto-handle the case or escalate it to
a human — then rigorously evaluates how well each step works.

This is a research/evaluation prototype, not a production system. No LLM is
trained from scratch; the Twitter support history is used as retrieval
knowledge, not training data for a new model.

**Status:** Phase 0 through Phase 13 complete (setup, dataset inspection,
brand selection, data cleaning, intent discovery, golden set, majority
baseline, TF-IDF baseline, AI intent classifier, historical case
retrieval, grounded reply generation, escalation decision, the integrated
agent, and the evaluation harness). Later sections of this README (LLM
judge, failure analysis) will be filled in as each phase lands — see
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
| `LLM_MODEL` | LLM model name — Google Gemini's free tier (see `DECISION_LOG.md` for why, and for the model-string saga) | `gemini-3.5-flash-lite` |
| `EMBEDDING_MODEL` | Local sentence-transformers embedding model for retrieval (Phase 9+) — no API key needed | `all-MiniLM-L6-v2` |
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

Then the TF-IDF + Logistic Regression baseline — trained only on the
Phase 4 weak-labeled knowledge data, with a validation split (also
non-golden) used to pick the regularization strength `C`:

```bash
python -m baselines.tfidf_classifier
```

**Result: 56.8% accuracy, 0.511 macro F1** — a large jump over the
majority baseline, but per-intent F1 is exactly 0 for the 3 intents with
no weak-label training coverage (`account_data_loss`,
`account_security_compromise`, `cancellation_or_refund_request` — see
Phase 4's decision log). The confusion matrix
(`artifacts/plots/tfidf_baseline_confusion_matrix.png`) shows those 3
intents' true examples mostly fall back to `account_access_issue` — the
closest available trained category. Writes the same predictions/metrics/
confusion-matrix-plot artifact triad as the majority baseline.

### AI intent classifier (Phase 8)

An LLM-based classifier (Google Gemini's free tier — see `DECISION_LOG.md`
for why Gemini rather than the originally-planned Claude), with output
constrained to the 12 approved intent labels via a JSON schema enum (not
just a prompt instruction — an out-of-vocabulary label fails schema
validation):

```bash
python -m src.intents.classifier
```

**Result: 84.7% accuracy, 0.846 macro F1** — decisively beats both
baselines, and correctly handles the 3 intents that structurally broke the
TF-IDF baseline (zero weak-label training coverage):
`account_security_compromise` (F1=0.973), `cancellation_or_refund_request`
(F1=0.786), plus `student_discount_issue` (F1=0.971, included for
contrast — this one *does* have weak-label coverage). Zero classification
errors across all 229 calls. The remaining confusions
(`artifacts/plots/ai_classifier_confusion_matrix.png`) concentrate on
intent-boundary pairs I personally found genuinely ambiguous while
hand-labeling the golden set (e.g. `cancellation_or_refund_request` vs
`billing_subscription_issue`) — a good sign the errors reflect real
taxonomy ambiguity, not noise. Full comparison:

| Model | Accuracy | Macro F1 |
|---|---:|---:|
| Majority baseline | 12.2% | 0.018 |
| TF-IDF + Logistic Regression | 56.8% | 0.511 |
| **AI classifier (Gemini)** | **84.7%** | **0.846** |

### Retrieval (Phase 9)

Build the FAISS vector index over knowledge-split cases (golden_pool is
never indexed — see `src/retrieval/index.py`):

```bash
python -m scripts.build_index
```

Embeds all 36,723 knowledge-split customer messages locally with
`sentence-transformers` (no API key, no rate limits) and writes
`data/index/knowledge.faiss` + `data/index/knowledge_metadata.jsonl`
(gitignored — regenerate with the command above).

Then evaluate retrieval quality on the golden set:

```bash
python -m scripts.evaluate_retrieval
```

**Result: mean top-1 similarity 0.858** (median 0.868) across all 229
golden queries — the index reliably finds close semantic matches. Writes
`artifacts/metrics/retrieval_stats.json` and
`artifacts/predictions/retrieval_examples.json` (10 example queries with
their top-5 retrieved cases).

There's no manually-labeled retrieval-relevance ground truth, so retrieval
quality is also measured with a proxy — intent-agreement@k: do the top-k
retrieved cases share the query's `gold_intent` (using Phase 4's weak
intent labels on the knowledge side)? This inherits the same known gap as
the Phase 7 baseline: for the 3 intents with zero weak-label training
coverage, agreement reads as 0.0 — **not because retrieval fails for
them**, but because the proxy metric itself has no positively-labeled
comparison data. Spot-checking confirms retrieval works fine there too:
querying an `account_security_compromise` example (a hacked-account
report) correctly retrieves other hacked-account cases at 0.70-0.72
similarity, entirely via semantic embedding similarity — retrieval is
more robust to the labeling gap than the classifiers were, since it never
depends on the weak-label taxonomy at all. See
`artifacts/predictions/retrieval_examples.json` for the full example.

### Grounded reply generation (Phase 10)

```bash
python -m scripts.generate_replies
```

Drafts a reply from the customer message + `gold_intent` (not a predicted
intent — isolates reply-generation quality from classifier error; the full
agent in Phase 12 chains the real predicted intent through instead) +
top-5 retrieved cases. The LLM must not invent policies, amounts,
deadlines, guarantees, or unverifiable account actions — if the evidence
doesn't support a confident answer it sets `grounded: false` and writes a
short honest holding reply instead. `evidence_ids` the model cites are
filtered against the case_ids actually retrieved (a hallucinated citation
is dropped, not trusted). Writes
`artifacts/predictions/reply_generation_examples.json`.

**Result (15 examples): 15/15 grounded, 0 errors.** SpotifyCares' actual
historical replies are overwhelmingly low-specificity triage messages
("DM us your account email") rather than concrete policy/amount/deadline
statements, so there's rarely a risky factual claim to hallucinate in the
first place — worth reading as a property of this brand's data, not proof
the grounding mechanism generalizes to a brand with more substantive
replies. Two real findings from this run, both in `DECISION_LOG.md`: a
citation-format bug (fixed — the model sometimes drops the `case_` prefix
when citing `evidence_ids`) and a reproducible generation artifact
(documented, not fixed — one reply mirrors a historical response that is
itself only half of a multi-part tweet, a known Phase 3 limitation;
good material for Phase 15's failure analysis).

### Escalation decision (Phase 11)

```python
from src.escalation.decision import decide
decide(customer_message, intent, intent_confidence, retrieved_cases, reply_grounded)
# -> {"decision": "AUTO_HANDLE" | "ESCALATE", "reason": "..."}
```

A transparent rules engine, not a learned classifier — escalates on any of:
low intent confidence, low retrieval similarity (or nothing retrieved), an
ungrounded generated reply, a hard-coded high-risk intent
(`account_security_compromise`), or two regex checks for repeated/
unresolved-complaint and legal/sensitive language. `MIN_RETRIEVAL_SIMILARITY`
was recalibrated from Phase 0's placeholder (0.5, which turned out to never
fire) to 0.70 using `scripts/calibrate_escalation_thresholds.py` against a
200-case validation sample drawn from `golden_pool` cases **not** in
`golden_set` — never tuned against the golden set itself. See
`DECISION_LOG.md` for the full calibration reasoning and the known gap
(`account_data_loss`/`cancellation_or_refund_request` aren't hard-coded as
always-escalate, since the golden-labeling rubric treats them
conditionally, not unconditionally).

### The complete agent (Phase 12)

```bash
python -m src.agent "My music keeps stopping every few seconds"
python -m src.agent   # no argument -> interactive loop, Ctrl+C to quit
```

`SupportAgent.handle(message)` chains everything above — classify →
retrieve → (maybe) generate → decide — behind one call, returning the
full structured result (intent + confidence, retrieved case_ids +
similarities, draft reply + evidence, and the final decision + reason).

Generation is skipped (`draft_reply: null`) whenever the case is already
escalate-worthy from intent confidence, retrieval similarity, or a
high-risk intent alone — no point spending a second LLM call on a reply
that will never be shown to the customer. Verified live:

- `"My music keeps stopping every few seconds, it's really annoying"` →
  `AUTO_HANDLE`, with a grounded reply citing its evidence case.
- `"I don't recognize this large payment... someone must have hacked in"`
  → `ESCALATE`, `draft_reply: null`, reason citing *two* signals at once
  (high-risk intent + retrieval similarity 0.65 below the 0.70 threshold).

Each dependency (classifier/retriever/generator) can be injected into
`SupportAgent(...)`, so `tests/test_agent.py` exercises every branch
(auto-handle, pre-check escalate with generation skipped, post-generation
escalate on an ungrounded reply, classifier failure, retrieval failure)
without making real API calls.

### Evaluation harness (Phase 13)

```bash
python -m evaluation.run_evaluation
```

Runs the full pipeline (retrieve → maybe-generate → decide) over all 229
golden examples and computes intent, retrieval, and escalation metrics
together. Reuses Phase 8's classifier predictions rather than
re-classifying (same model/prompt/inputs — see `DECISION_LOG.md`), so
this run only spends new API calls on generation. Writes
`artifacts/predictions/golden_predictions.jsonl` (full result per
example) and `artifacts/metrics/{intent,escalation,retrieval}_metrics.json`.

**Headline result:** intent accuracy 84.7% (same as Phase 8) — but
**escalation accuracy is only 60.3%**, with a **64.8% false auto-handle
rate** (of golden examples that should have escalated, the system
dangerously auto-handled 65% of them). Root cause, verified by breaking
down the errors by intent: `HIGH_RISK_INTENTS` (Phase 11) hard-codes only
`account_security_compromise`; `account_data_loss` and
`cancellation_or_refund_request` alone account for a third of the
dangerous errors, plus real repeated-complaint language the regex safety
net doesn't match. **This was deliberately not patched** — doing so would
mean tuning escalation rules directly against `gold_action`, exactly the
leakage the plan warns against. Full root-cause analysis and why this is
being left for a proper validation-set-driven fix (not a golden-set
patch) in `DECISION_LOG.md` — this is this project's own "what is
misleading about my headline number" finding (Phase 16 material,
surfacing here first): intent accuracy looks good in isolation; the
number that actually predicts deployment safety does not.

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
