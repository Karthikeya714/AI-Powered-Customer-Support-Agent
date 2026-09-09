# Hiver SDE Intern — AI Customer Support Agent
# Project Architecture Specification for Claude Code

## 1. PROJECT PURPOSE

Build a brand-specific AI customer-support agent using the Customer Support on Twitter
dataset.

The system should take a new customer message and:

1. Classify the message into one of the selected brand-specific intents.
2. Retrieve similar historical customer-support cases.
3. Generate a reply grounded in those historical cases.
4. Decide whether the AI should AUTO_HANDLE the case or ESCALATE it to a human.
5. Provide a reason for the decision.
6. Produce enough intermediate information to evaluate and audit the system.

The project is primarily an offline research/evaluation prototype.

DO NOT build a real Twitter/X integration.
DO NOT train an LLM from scratch.
DO NOT build an unnecessarily complex frontend.
DO NOT hide the evidence used to generate a reply.

---

# 2. HIGH-LEVEL ARCHITECTURE

The complete system should follow this flow:

```text
                         ┌─────────────────────┐
                         │  Twitter Support    │
                         │      Dataset        │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Data Ingestion &    │
                         │ Preprocessing       │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Clean Support Cases │
                         │ + Conversations     │
                         └──────────┬──────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     │                             │
                     ▼                             ▼
          ┌─────────────────────┐       ┌─────────────────────┐
          │ Intent Definitions  │       │ Historical Case     │
          │ + Classifier        │       │ Knowledge Base      │
          └──────────┬──────────┘       └──────────┬──────────┘
                     │                             │
                     │                             │
NEW CUSTOMER ────────┼─────────────────────────────┤
MESSAGE              │                             │
                     ▼                             ▼
          ┌─────────────────────┐       ┌─────────────────────┐
          │ Intent Prediction   │       │ Similar Case        │
          │ + Confidence        │       │ Retrieval            │
          └──────────┬──────────┘       └──────────┬──────────┘
                     │                             │
                     └──────────────┬──────────────┘
                                    ▼
                         ┌─────────────────────┐
                         │ Grounded Reply      │
                         │ Generator (LLM)     │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Escalation / Risk   │
                         │ Decision Engine     │
                         └──────────┬──────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                  ┌─────────────┐       ┌─────────────┐
                  │ AUTO_HANDLE │       │  ESCALATE   │
                  └──────┬──────┘       └──────┬──────┘
                         │                     │
                         ▼                     ▼
                  Draft Response         Human Agent
```

---

# 3. TWO DISTINCT PARTS OF THE PROJECT

The architecture should be understood as two connected systems.

## A. OFFLINE BUILD / PREPARATION PIPELINE

This processes historical data before a new customer query arrives.

```text
Raw Twitter Dataset
        ↓
Data Cleaning
        ↓
Conversation Reconstruction
        ↓
Brand Selection
        ↓
Intent Discovery
        ↓
Historical Support Cases
        ↓
Embedding Generation
        ↓
Vector Index
```

This part creates the knowledge and models required by the agent.

## B. ONLINE / INFERENCE PIPELINE

This processes one new customer message.

```text
New Customer Message
        ↓
Intent Classification
        ↓
Retrieve Similar Historical Cases
        ↓
Generate Grounded Reply
        ↓
Escalation Decision
        ↓
Final Structured Result
```

The "online" part does NOT need to connect to Twitter.
It simply accepts a customer message as input.

---

# 4. RECOMMENDED PROJECT STRUCTURE

Use this structure:

```text
hiver-sde-assignment/
│
├── data/
│   ├── raw/
│   │   └── .gitkeep
│   │
│   ├── processed/
│   │   ├── support_cases.jsonl
│   │   ├── support_cases_sample.jsonl
│   │   ├── brand_statistics.csv
│   │   └── dataset_summary.json
│   │
│   └── golden/
│       ├── golden_set.jsonl
│       └── golden_set.csv
│
├── src/
│   ├── __init__.py
│   │
│   ├── config.py
│   ├── schemas.py
│   ├── agent.py
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   ├── cleaner.py
│   │   └── conversation_builder.py
│   │
│   ├── intents/
│   │   ├── __init__.py
│   │   ├── labels.py
│   │   ├── discovery.py
│   │   └── classifier.py
│   │
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── embeddings.py
│   │   ├── index.py
│   │   └── retriever.py
│   │
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── prompts.py
│   │   └── reply_generator.py
│   │
│   └── escalation/
│       ├── __init__.py
│       └── decision.py
│
├── baselines/
│   ├── majority.py
│   └── tfidf_classifier.py
│
├── evaluation/
│   ├── __init__.py
│   ├── run_evaluation.py
│   ├── evaluate_intents.py
│   ├── evaluate_retrieval.py
│   ├── evaluate_replies.py
│   ├── evaluate_escalation.py
│   ├── llm_judge.py
│   └── human_agreement.py
│
├── scripts/
│   ├── inspect_dataset.py
│   ├── build_processed_dataset.py
│   ├── build_intent_dataset.py
│   └── build_index.py
│
├── app/
│   └── streamlit_app.py
│
├── tests/
│   ├── test_data.py
│   ├── test_intents.py
│   ├── test_retrieval.py
│   ├── test_generation.py
│   ├── test_escalation.py
│   └── test_agent.py
│
├── artifacts/
│   ├── metrics/
│   ├── predictions/
│   ├── plots/
│   └── judge_results/
│
├── docs/
│   ├── intent_definitions.md
│   ├── golden_set_methodology.md
│   └── failure_analysis.md
│
├── README.md
├── REPORT.md
├── DECISION_LOG.md
├── requirements.txt
├── .env.example
└── .gitignore
```

---

# 5. DATA LAYER

## Files

```text
src/data/loader.py
src/data/cleaner.py
src/data/conversation_builder.py
```

## Responsibilities

### loader.py

Responsible for:
- Loading raw dataset files.
- Handling large files safely.
- Reading in chunks when necessary.
- Providing reusable data-loading functions.

Example interface:

```python
load_raw_data(path, sample_size=None)
```

### cleaner.py

Responsible for:
- Removing unusable rows.
- Handling missing values.
- Removing duplicates where appropriate.
- Normalizing text.
- Identifying customer/support messages where possible.

### conversation_builder.py

Responsible for:
- Reconstructing conversation/thread context.
- Pairing customer messages with relevant brand responses.
- Preserving source IDs.
- Preserving timestamps.
- Creating normalized support-case records.

---

# 6. NORMALIZED DATA MODEL

Use a stable schema.

A support case should look approximately like:

```json
{
  "case_id": "case_001",
  "conversation_id": "conv_123",
  "brand": "selected_brand",
  "customer_message": "My refund has not arrived.",
  "brand_response": "Please DM us your transaction ID so we can check.",
  "context": [],
  "timestamp": "2016-01-01T12:00:00",
  "source_ids": ["tweet_1", "tweet_2"]
}
```

If multi-turn context exists:

```json
{
  "case_id": "case_002",
  "conversation_id": "conv_456",
  "brand": "selected_brand",
  "customer_message": "My refund has not arrived.",
  "brand_response": "Please DM us your transaction ID.",
  "context": [
    {
      "speaker": "customer",
      "text": "I cancelled my order last week."
    },
    {
      "speaker": "brand",
      "text": "We'll help check the cancellation."
    }
  ],
  "timestamp": "...",
  "source_ids": ["...", "...", "..."]
}
```

The exact schema can be adjusted after inspecting the dataset.

---

# 7. INTENT LAYER

## Files

```text
src/intents/labels.py
src/intents/discovery.py
src/intents/classifier.py
```

## labels.py

Contains the FINAL manually approved intent definitions.

Example:

```python
INTENTS = {
    "refund": {
        "description": "Questions or complaints about refunds or missing refunds.",
        "examples": [...]
    },
    "payment_issue": {
        "description": "Problems involving payments or charges.",
        "examples": [...]
    }
}
```

Do not hard-code a fixed set before analyzing the dataset.

The final number should probably be around 8–15, but the data should determine this.

## discovery.py

Used during the exploratory phase.

Responsibilities:
- Sample customer messages.
- Identify candidate themes.
- Produce representative examples.
- Help the human define final intents.

This is an analysis tool, not the final classifier.

## classifier.py

Responsible for predicting the intent of a new message.

Input:

```text
"My refund hasn't arrived."
```

Output:

```json
{
  "intent": "refund",
  "confidence": 0.91
}
```

Rules:
- Only return approved intent labels.
- Never invent new labels.
- Support structured output.
- Make model/API configurable.
- Store raw prediction information for evaluation.

---

# 8. RETRIEVAL / KNOWLEDGE LAYER

## Files

```text
src/retrieval/embeddings.py
src/retrieval/index.py
src/retrieval/retriever.py
```

This is the RAG component.

## embeddings.py

Responsibilities:
- Convert historical customer-support cases into embeddings.
- Convert new customer messages into embeddings.
- Use a configurable embedding model.

## index.py

Responsibilities:
- Build FAISS or another local vector index.
- Save/load the index.
- Keep mapping between vector IDs and support-case IDs.

The index must be built from historical data only.

The golden evaluation set must not leak into the index.

## retriever.py

Input:

```text
"My refund hasn't arrived."
```

Output:

```json
{
  "results": [
    {
      "case_id": "case_123",
      "similarity": 0.89,
      "customer_message": "Where is my refund?",
      "brand_response": "Please DM your transaction ID..."
    },
    {
      "case_id": "case_456",
      "similarity": 0.86,
      "customer_message": "Refund is still pending.",
      "brand_response": "We'll check the refund status..."
    }
  ]
}
```

Start with top_k = 3 or 5.

Make top_k configurable.

---

# 9. GENERATION LAYER

## Files

```text
src/generation/prompts.py
src/generation/reply_generator.py
```

The generator should receive:

```text
Customer message
+
Predicted intent
+
Retrieved historical cases
```

Example:

```text
CUSTOMER:
My refund hasn't arrived.

INTENT:
refund

HISTORICAL CASE 1:
Customer:
Where is my refund?
Brand:
Please DM us your transaction ID so we can check.

HISTORICAL CASE 2:
Customer:
Refund is still pending.
Brand:
We'll check the refund status.
```

Then generate a concise support reply.

## Grounding requirements

The LLM must NOT invent:
- Refund policies
- Exact deadlines
- Monetary amounts
- Guarantees
- Account actions
- Company policies
- Facts not supported by retrieved evidence

If the evidence is insufficient, the system should prefer escalation.

## Output schema

```json
{
  "draft_reply": "Sorry for the delay. Please DM us your transaction ID so we can check the refund status.",
  "evidence_ids": ["case_123", "case_456"],
  "grounded": true
}
```

---

# 10. ESCALATION LAYER

## File

```text
src/escalation/decision.py
```

Purpose:

Determine whether the case should be automatically handled or sent to a human.

Input should include:

```text
Customer message
Predicted intent
Intent confidence
Retrieved cases
Retrieval similarity
Generated reply
Risk signals
```

Output:

```json
{
  "decision": "AUTO_HANDLE",
  "reason": "Common issue with strong historical evidence and a consistent resolution pattern."
}
```

OR:

```json
{
  "decision": "ESCALATE",
  "reason": "Potential payment dispute requiring human verification."
}
```

## Possible escalation signals

- Potential fraud
- Payment dispute
- Legal threat
- Highly sensitive issue
- Repeated unresolved complaint
- Low intent confidence
- Low retrieval similarity
- No relevant historical cases
- Conflicting historical resolutions
- High-risk intent

## Auto-handle signals

- Common issue
- High intent confidence
- Strong retrieval evidence
- Consistent historical resolutions
- Low-risk issue

IMPORTANT:

Do not create arbitrary thresholds without validation.

Make thresholds configurable:

```python
MIN_INTENT_CONFIDENCE = ...
MIN_RETRIEVAL_SIMILARITY = ...
```

Tune them using validation data, not the golden test set.

---

# 11. COMPLETE AGENT

## File

```text
src/agent.py
```

This is the main orchestrator.

It should coordinate all components.

Conceptually:

```python
class SupportAgent:

    def handle(self, customer_message):
        intent = classifier.predict(customer_message)

        cases = retriever.retrieve(
            customer_message,
            top_k=5
        )

        reply = generator.generate(
            customer_message=customer_message,
            intent=intent,
            retrieved_cases=cases
        )

        decision = escalation.decide(
            customer_message=customer_message,
            intent=intent,
            retrieved_cases=cases,
            reply=reply
        )

        return {
            "intent": intent,
            "retrieved_cases": cases,
            "draft_reply": reply,
            "decision": decision
        }
```

The actual implementation can be improved, but keep this orchestration simple.

---

# 12. FINAL AGENT OUTPUT

For every input, return a consistent structured object:

```json
{
  "customer_message": "My refund hasn't arrived.",
  "intent": {
    "label": "refund",
    "confidence": 0.91
  },
  "retrieved_cases": [
    {
      "case_id": "case_123",
      "similarity": 0.89
    }
  ],
  "draft_reply": "Sorry for the delay. Please DM us your transaction ID so we can check the refund status.",
  "decision": {
    "action": "AUTO_HANDLE",
    "reason": "Common issue with strong historical evidence."
  }
}
```

For escalation:

```json
{
  "customer_message": "I don't recognize this charge.",
  "intent": {
    "label": "payment_issue",
    "confidence": 0.94
  },
  "retrieved_cases": [],
  "draft_reply": null,
  "decision": {
    "action": "ESCALATE",
    "reason": "Potential payment dispute requiring human verification."
  }
}
```

It is acceptable for draft_reply to be null when escalation happens before safe generation.

---

# 13. BASELINE ARCHITECTURE

The final system must be compared with simpler approaches.

## Baseline 1: Majority Class

```text
Customer Message
       ↓
Most Common Intent
```

File:

```text
baselines/majority.py
```

## Baseline 2: TF-IDF + Logistic Regression

```text
Customer Message
       ↓
TF-IDF
       ↓
Logistic Regression
       ↓
Intent
```

File:

```text
baselines/tfidf_classifier.py
```

Both must use the same golden evaluation set.

---

# 14. EVALUATION ARCHITECTURE

The evaluation system is a separate subsystem.

```text
                    GOLDEN SET
                        │
                        ▼
                 Run Full Agent
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
  Intent Results   Reply Results   Escalation Results
        │               │                │
        ▼               ▼                ▼
   Accuracy/F1      LLM Judge        Precision/Recall
   Confusion        + Human          False Auto-Handle
   Matrix           Agreement       Rate
```

## Files

```text
evaluation/run_evaluation.py
evaluation/evaluate_intents.py
evaluation/evaluate_retrieval.py
evaluation/evaluate_replies.py
evaluation/evaluate_escalation.py
evaluation/llm_judge.py
evaluation/human_agreement.py
```

---

# 15. GOLDEN SET ARCHITECTURE

The golden set is the project's ground truth.

Target:

150–250 manually labelled examples.

Schema:

```json
{
  "id": "gold_001",
  "customer_message": "My refund hasn't arrived.",
  "gold_intent": "refund",
  "gold_action": "AUTO_HANDLE",
  "gold_notes": "Common refund-status issue."
}
```

Important:

```text
TRAINING / KNOWLEDGE DATA
          ≠
GOLDEN EVALUATION DATA
```

Never index or directly tune the final system on the golden set.

The golden set should contain:
- Common cases
- Rare cases
- Ambiguous cases
- Difficult cases
- High-risk cases
- Different wording styles

---

# 16. EVALUATION METRICS

## Intent classification

Report:

```text
Accuracy
Macro F1
Per-intent F1
Confusion Matrix
```

Macro F1 is important because accuracy can hide poor performance on minority intents.

## Retrieval

Where possible:

```text
Recall@K
Relevant-case rate
Similarity distribution
Manual relevance checks
```

If formal retrieval labels are difficult to construct, clearly state the limitation.

## Reply quality

Evaluate:

```text
Correctness
Groundedness
Helpfulness
Tone
Unsupported claims / hallucination
```

Use a 1–5 scale.

## Escalation

Report:

```text
Accuracy
Precision
Recall
F1
False Auto-Handle Rate
False Escalation Rate
```

False auto-handling is especially important because unsafe automatic handling is more serious than unnecessarily escalating a low-risk case.

---

# 17. LLM-AS-JUDGE ARCHITECTURE

```text
Customer Message
       +
Historical Evidence
       +
Generated Reply
       ↓
   LLM Judge
       ↓
┌─────────────────────┐
│ Correctness         │
│ Groundedness        │
│ Helpfulness         │
│ Tone                │
│ Unsupported Claims  │
└─────────────────────┘
       ↓
Scores 1–5
```

The judge should receive the customer query, evidence, and reply.

It should NOT judge based only on whether the response sounds good.

The rubric should explicitly check grounding.

---

# 18. HUMAN AGREEMENT ARCHITECTURE

Use a smaller subset, e.g. 30–50 examples.

```text
                Same Examples
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
     Human Judge            LLM Judge
          │                     │
          └──────────┬──────────┘
                     ▼
              Compare Scores
                     │
                     ▼
           Agreement Analysis
```

Report an appropriate agreement statistic/correlation and manually inspect disagreements.

The purpose is to establish:

> "Our automated judge is reasonably aligned with human evaluation."

---

# 19. ARTIFACTS / OUTPUTS

Every evaluation run should save raw results.

Example:

```text
artifacts/
    metrics/
        intent_metrics.json
        escalation_metrics.json
        reply_metrics.json
        retrieval_metrics.json

    predictions/
        golden_predictions.jsonl

    plots/
        intent_confusion_matrix.png

    judge_results/
        llm_judge_results.jsonl
        human_comparison.csv
```

Do NOT only print metrics to the terminal.

Save the underlying predictions so the reported results can be audited.

---

# 20. CONFIGURATION ARCHITECTURE

Use environment variables/configuration for:

```text
LLM provider
LLM model
Embedding model
API key
Selected brand
Top K
Confidence thresholds
Retrieval thresholds
Dataset paths
```

Example `.env.example`:

```text
LLM_API_KEY=
LLM_MODEL=
EMBEDDING_MODEL=
SELECTED_BRAND=
TOP_K=5
MIN_INTENT_CONFIDENCE=
MIN_RETRIEVAL_SIMILARITY=
```

Never commit real API keys.

---

# 21. COMMAND-LINE INTERFACE

Make common tasks executable with simple commands.

Examples:

```bash
python scripts/inspect_dataset.py
```

```bash
python scripts/build_processed_dataset.py
```

```bash
python scripts/build_index.py
```

```bash
python -m evaluation.run_evaluation
```

```bash
python -m app.streamlit_app
```

Exact commands can change depending on the final implementation.

---

# 22. STREAMLIT DEMO ARCHITECTURE

Keep the UI extremely simple.

```text
┌─────────────────────────────────────────────┐
│       AI CUSTOMER SUPPORT AGENT             │
├─────────────────────────────────────────────┤
│                                             │
│ Customer message:                           │
│ [ My refund hasn't arrived............... ]  │
│                                             │
│              [Analyze]                      │
│                                             │
├─────────────────────────────────────────────┤
│ Intent: Refund                              │
│ Confidence: 0.91                            │
│                                             │
│ Similar historical cases:                   │
│ 1. Refund delayed...                        │
│ 2. Refund pending...                        │
│ 3. Missing refund...                        │
│                                             │
│ Draft reply:                                │
│ "Sorry for the delay..."                    │
│                                             │
│ Decision: AUTO_HANDLE                       │
│ Reason: Strong historical evidence...       │
└─────────────────────────────────────────────┘
```

The UI is only for demonstration.

The core functionality must remain usable without Streamlit.

---

# 23. DATA FLOW IN DETAIL

## Offline preparation

```text
RAW DATA
   ↓
Load
   ↓
Clean
   ↓
Identify Brand
   ↓
Reconstruct Conversations
   ↓
Create Support Cases
   ↓
Split Data
   ├── Knowledge/Training Data
   ├── Validation Data
   └── Golden Evaluation Set
             ↓
          NEVER LEAK
```

## Index creation

```text
Historical Support Cases
        ↓
Embedding Model
        ↓
Vectors
        ↓
FAISS Index
        ↓
case_id mapping
```

## Runtime

```text
New Message
    ↓
Intent Classifier
    ↓
intent + confidence
    ↓
Embedding
    ↓
FAISS Search
    ↓
Top-K Historical Cases
    ↓
LLM
    ↓
Grounded Reply
    ↓
Escalation Engine
    ↓
Final Result
```

---

# 24. DATA LEAKAGE RULES

This is extremely important.

Avoid these situations:

```text
Golden Set
    ↓
Vector Index
    ↓
Retrieved during evaluation
```

or:

```text
Golden Set
    ↓
Prompt examples
    ↓
Intent classifier tuning
```

or:

```text
Golden Set
    ↓
Threshold tuning
    ↓
Same Golden Set used for final metrics
```

Instead:

```text
Training/Knowledge Data
        ↓
Build system

Validation Data
        ↓
Tune thresholds/prompts

Golden Set
        ↓
Final evaluation ONLY
```

If there is any unavoidable overlap in the original Twitter conversation structure,
document it explicitly.

---

# 25. SEPARATE RETRIEVAL FROM GENERATION

Do NOT create a single giant function that does everything.

Bad:

```python
def answer_customer(message):
    # 500 lines of LLM + retrieval + classification...
```

Preferred:

```text
classifier
retriever
generator
escalation
agent
```

Each component should be independently testable.

This will also make live interview modification much easier.

---

# 26. ERROR HANDLING

The system must gracefully handle:

- Empty customer messages
- Missing API key
- LLM timeout
- Invalid LLM output
- Retrieval failure
- No retrieved cases
- Low similarity
- Unknown intent
- Malformed data

If the system cannot safely produce an answer:

```text
ESCALATE
```

is preferable to hallucinating.

---

# 27. OBSERVABILITY / DEBUG INFORMATION

For each agent run, preserve enough information to understand what happened.

Example:

```json
{
  "customer_message": "...",
  "intent": "...",
  "intent_confidence": 0.87,
  "retrieval_results": [...],
  "generation_evidence_ids": [...],
  "draft_reply": "...",
  "decision": "ESCALATE",
  "decision_reason": "...",
  "timings": {
    "classification_ms": 400,
    "retrieval_ms": 30,
    "generation_ms": 1200
  }
}
```

This is useful for debugging and failure analysis.

---

# 28. TESTING ARCHITECTURE

At minimum test:

## Data tests
- Missing values
- Duplicate handling
- Conversation reconstruction
- Schema validity

## Intent tests
- Valid labels only
- Structured output
- Invalid model response handling

## Retrieval tests
- Index loads
- Top-k works
- Case IDs map correctly
- Empty retrieval is handled

## Generation tests
- Required fields exist
- Evidence IDs are returned
- Invalid LLM output is handled

## Escalation tests
- High-risk cases escalate
- Strong low-risk cases can auto-handle
- Low evidence causes escalation

## Agent tests
- Complete pipeline works
- Failure in one component is handled safely

---

# 29. SECURITY / PRIVACY

The dataset contains real customer-support conversations.

Therefore:

- Do not expose unnecessary personal information in the demo.
- Avoid printing sensitive raw data unnecessarily.
- Do not commit secrets.
- Do not send more data to an external LLM than necessary.
- Document if external APIs are used.
- Use a sanitized/limited dataset for public artifacts if required.

---

# 30. WHAT NOT TO BUILD

Do NOT build:

- Real Twitter API integration
- Automatic tweet posting
- Production authentication
- Multi-brand support
- Complex microservices
- Kubernetes deployment
- Custom LLM training
- Fine-tuning unless there is a strong evidence-based reason
- Large production database
- Complex frontend
- Overly complicated agent frameworks

The assignment is about:

```text
DATA → AI → EVIDENCE → EVALUATION
```

not production infrastructure.

---

# 31. IMPLEMENTATION ORDER

Claude Code must implement the architecture in this order:

```text
PHASE 1
Project setup
       ↓
PHASE 2
Dataset inspection
       ↓
PHASE 3
Brand selection
       ↓
PHASE 4
Data preprocessing
       ↓
PHASE 5
Intent discovery
       ↓
PHASE 6
Golden set creation
       ↓
PHASE 7
Majority baseline
       ↓
PHASE 8
TF-IDF baseline
       ↓
PHASE 9
AI intent classifier
       ↓
PHASE 10
Retrieval
       ↓
PHASE 11
Grounded reply generation
       ↓
PHASE 12
Escalation
       ↓
PHASE 13
End-to-end agent
       ↓
PHASE 14
Evaluation harness
       ↓
PHASE 15
LLM judge + human agreement
       ↓
PHASE 16
Failure analysis
       ↓
PHASE 17
Decision log
       ↓
PHASE 18
Streamlit demo
       ↓
PHASE 19
Final report
       ↓
PHASE 20
Clean-environment reproducibility test
```

---

# 32. CLAUDE CODE WORKING RULES

Claude Code should follow these rules throughout the project:

1. Implement only the requested phase.
2. Do not rewrite unrelated components.
3. Before major architectural changes, explain the reason.
4. Keep code modular.
5. Add tests for important logic.
6. Use type hints where practical.
7. Use clear function/class names.
8. Save intermediate artifacts.
9. Never hard-code evaluation results.
10. Never claim a metric without underlying predictions.
11. Never use the golden set for tuning.
12. Never silently drop data.
13. Log important preprocessing statistics.
14. Keep model/API configuration external.
15. Use deterministic seeds for sampling.
16. Keep dependencies minimal.
17. Prefer standard Python libraries where sufficient.
18. Do not add an agent framework unless there is a concrete benefit.
19. If retrieval evidence is weak, allow escalation.
20. If the LLM output is invalid, fail safely.
21. If a proposed feature is not required by the assignment, ask before
    adding significant complexity.
22. Every important engineering decision should eventually be added to
    DECISION_LOG.md.
23. Every final result should be reproducible.
24. Code should be understandable enough to explain in a live interview.
25. Do not optimize for complexity; optimize for evidence and reliability.

---

# 33. DEFINITION OF DONE

The project is complete only when all of the following are true:

[ ] One brand has been selected using dataset evidence.

[ ] Historical customer-support conversations have been cleaned.

[ ] Conversations/support cases can be inspected.

[ ] Final intents have been manually defined.

[ ] 150–250 golden examples exist.

[ ] Golden-set methodology is documented.

[ ] Majority baseline exists.

[ ] TF-IDF + Logistic Regression baseline exists.

[ ] AI intent classifier exists.

[ ] Historical retrieval system exists.

[ ] Grounded reply generation exists.

[ ] Escalation decision exists.

[ ] Complete agent pipeline works.

[ ] Evaluation harness exists.

[ ] Intent metrics exist.

[ ] Retrieval evaluation exists where feasible.

[ ] Reply quality evaluation exists.

[ ] Escalation metrics exist.

[ ] LLM judge exists.

[ ] Human-vs-LLM judge agreement has been measured.

[ ] Top 5 real failure modes are documented.

[ ] "What is misleading about my headline number?" exists.

[ ] 10–15 engineering decisions are documented.

[ ] Simple demo exists.

[ ] README explains setup and reproduction.

[ ] Headline results can be reproduced in under 15 minutes.

---

# 34. THE CORE ARCHITECTURAL PRINCIPLE

The project should always answer this chain:

```text
WHAT DID THE CUSTOMER ASK?
            ↓
WHAT INTENT IS IT?
            ↓
WHAT HAVE WE SEEN BEFORE?
            ↓
HOW DID THE BRAND HANDLE SIMILAR CASES?
            ↓
WHAT REPLY CAN WE SAFELY DRAFT?
            ↓
IS THERE ENOUGH EVIDENCE TO AUTO-HANDLE?
            ↓
IF NOT, WHY SHOULD A HUMAN HANDLE IT?
            ↓
HOW DO WE PROVE ALL OF THIS WORKS?
```

The final project is therefore:

```text
               BRAND-SPECIFIC
              AI SUPPORT AGENT
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
     INTENT       RETRIEVAL     RISK/
   CLASSIFIER      / RAG       ESCALATION
        │            │            │
        └────────────┼────────────┘
                     ▼
              GROUNDED REPLY
                     │
                     ▼
                EVALUATION
                     │
       ┌─────────────┼─────────────┐
       ▼             ▼             ▼
    Intent         Reply        Escalation
    Metrics        Quality       Metrics
                     │
                     ▼
             HUMAN AGREEMENT
                     │
                     ▼
              FAILURE ANALYSIS
```

The goal is not merely to produce an impressive AI response.

The goal is to build a system where every important response can be
explained, evaluated, and challenged.
