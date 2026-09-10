# Failure Analysis

Five real failure modes, drawn directly from Phase 13's full-pipeline run
over the 229-example golden set (`artifacts/predictions/golden_predictions.jsonl`)
and Phase 8's classifier predictions (`artifacts/predictions/ai_classifier_predictions.jsonl`).
None of these are manufactured — every example below is a real golden-set
message and the system's real recorded output.

---

## 1. Wrong escalation: rule gaps in `HIGH_RISK_INTENTS` and the repeated-complaint regex

This is the single largest failure category by volume — 68 of 229 golden
examples (see Phase 13's decision log entry for the full breakdown) — and
the most consequential, since it's the dangerous error direction (a case
that should have gone to a human was auto-handled).

**Example — `gold_0007`:**
- Customer message: *"@115888 just lost all my saved songs and i have no idea why... SO annoying!!!"*
- Predicted: intent `account_data_loss` (confidence 1.00), retrieval similarity 0.87 → **AUTO_HANDLE**
- Expected: `account_data_loss`, **ESCALATE**
- What went wrong: every signal the escalation engine checks (confidence,
  similarity, high-risk-intent membership, regex) looked fine in
  isolation — the classifier was *right* and *confident*, retrieval found
  *strong* matches. The system auto-handled a case a human explicitly
  labeled unsafe to auto-handle.
- Hypothesis: `src/escalation/decision.py`'s `HIGH_RISK_INTENTS` set
  contains only `account_security_compromise`. `account_data_loss` was
  deliberately left out in Phase 11 because the golden-labeling rubric
  treats it *conditionally* (lost downloads with a known fix pattern were
  auto-handled; lost playlists/libraries were escalated) — but the current
  rule set has no way to represent that distinction, so it defaults to
  never escalating on intent alone here.
- Possible fix: a sub-signal distinguishing "downloaded songs" from
  "playlists/library" within `account_data_loss` (e.g. keyword matching on
  "playlist"/"library" vs "downloaded"/"offline"), calibrated on a
  held-out validation sample — not on golden failures directly (see below).

**Example — `gold_0023`:**
- Customer message: *"Hello #Spotify. 26 Sept I reported a bug, what's the status? I still can't drag playing #songs to #playlists :((((  isn't this a big issue?"*
- Predicted: `playback_technical_issue` (confidence 0.85), similarity 0.77 → **AUTO_HANDLE**
- Expected: `playback_technical_issue`, **ESCALATE**
- What went wrong: this is textbook repeated-unresolved-complaint
  language — a bug reported weeks earlier, still broken. The escalation
  engine has a regex specifically for this
  (`_REPEATED_COMPLAINT_RE`), but it requires words like "again",
  "repeatedly", "several times", or an ordinal ("3rd time"). This message
  says "I still can't" — a real, common way of expressing the same thing
  that the hand-written pattern doesn't cover.
- Hypothesis: hand-written regexes have poor recall on paraphrases of the
  concept they're meant to catch — an inherent limitation of keyword
  matching for something that's fundamentally about meaning, not exact
  wording.
- Possible fix: replace or supplement the regex with a small LLM-based
  classification step ("does this message indicate a prior unresolved
  attempt?"), or at minimum expand the pattern list using a proper
  validation-set word-frequency analysis instead of hand-guessed terms.

**Example — `gold_0041`:**
- Customer message: *"Hello. The email address I think is associated with my account no longer exists. cannot access account (Still Being Charged)"*
- Predicted: `account_access_issue` (confidence 0.85), similarity 0.88 → **AUTO_HANDLE**
- Expected: `account_access_issue`, **ESCALATE**
- What went wrong: this message compounds two problems — can't access
  the account (self-service reset impossible, since the email is gone)
  **and** is still being charged. Either alone might be routine; together
  they mean the customer is paying for something they can't use and can't
  fix themselves. No single signal in the escalation engine represents
  "compounding problems," so it's invisible to the rule set.
- Hypothesis: the escalation engine evaluates independent signals in
  isolation; it has no notion of *interaction* between a routine intent
  and a routine-looking retrieval match when the specific combination of
  circumstances (locked out + billed) is what actually makes a case risky.
- Possible fix: a dedicated financial-harm sub-signal (keyword-matching
  "charged"/"billed"/"payment" *combined with* an access-issue intent),
  not just a generic intent category.

---

## 2. Ambiguous intent boundary: cancellation vs. billing complaint

**Example — `gold_0248`:**
- Customer message: *"Help! I have an old account which I thought was cancelled that I'm still being charged £9.99 a month for?"*
- Predicted: `billing_subscription_issue` (classifier's own reasoning: *"The customer is complaining about unexpected ongoing charges for an account they thought was cancelled."*)
- Expected: `cancellation_or_refund_request`
- What went wrong: the message genuinely straddles both categories — it's
  a billing complaint (unexpected charge) about a cancellation that
  apparently didn't take effect. Both labels are defensible reads of the
  same text.
- Hypothesis: this reflects a real ambiguity in the intent taxonomy
  itself, not a classifier weakness — `docs/intent_definitions.md`'s
  boundary note for `billing_subscription_issue` says exactly this case
  ("a billing complaint that does not explicitly ask to cancel or get
  money back stays in billing") is the dividing line, but "I thought it
  was cancelled" sits right on that line.
- Possible fix: none needed at the taxonomy level — this is an inherent,
  acceptable rate of boundary disagreement between two genuinely close
  categories. Worth tracking whether this specific pair recurs often
  enough in a larger sample to justify merging them or adding a more
  explicit boundary rule.

**Example — `gold_0262`:** *"Y'all charged me four times because I tried to get the student but canceled and re-tried it four times but my card never went through :/ how do I fix?"* — predicted `billing_subscription_issue`, expected `cancellation_or_refund_request`. Same pattern: a billing/payment problem narrated through a cancel-and-retry sequence. Same conclusion as above.

---

## 3. Missing context: a single message can't disambiguate what "it" refers to

**Example — `gold_0240`:**
- Customer message (as sampled for the golden set — a single tweet, no thread context retained): *"Or pictures disappear. Very frustrating!!"*
- Predicted: `account_data_loss` (classifier's reasoning: *"pictures (artwork or profile images) disappearing... falls under missing personal library data"*)
- My own golden label (Phase 5): `playback_technical_issue`, explicitly flagged at labeling time as a **hard/low-context case** — the real conversation (visible in `context` at labeling time) was about PS3 album-art display, not data loss.
- What went wrong: the message alone, without its preceding turns, is
  genuinely ambiguous — "pictures disappear" could mean lost photos, lost
  album art, or a UI rendering bug. The classifier only receives the
  single `customer_message` string, not the full `context` array Phase 3
  preserved.
- Hypothesis: intent classification only looking at the isolated message
  (not the conversation context available in the golden set's `context`
  field) throws away real disambiguating information for follow-up-style
  messages.
- Possible fix: pass `context` into the classifier prompt when it's
  non-empty — a natural Phase 8/12 extension not implemented here because
  the golden set's `customer_message` field was treated as the complete
  query, matching how a brand-new incoming message would actually arrive
  in production (no prior context exists for a first contact). This is a
  real trade-off, not an oversight: for genuinely first-contact messages
  there's no context to use; for mid-thread messages like this one, the
  system is at a structural disadvantage until context is wired in.

---

## 4. Corrupted evidence → malformed generation (not hallucination, but just as unsafe to send)

**Example — `gold_0034`:**
- Customer message: *"I can't listen to my music offline when your app repeatedly deletes my music and makes me redownload it twice a week"*
- Generated draft reply: **`"@583775 2: at https://t.co/38J7tFlIBF. They should help with this /SY"`**
- Grounding note (from the generator itself): *"The reply directly mirrors the exact phrasing and link provided in the historical case for this exact customer message."*
- What went wrong: the reply is grammatically broken and starts mid-sentence
  with a stray `"2:"` fragment. The generator did exactly what it's
  supposed to do — ground its reply in retrieved evidence — but the
  evidence (`case_1970802`'s `brand_response`) is itself only the second
  half of a two-part historical tweet ("1/2" / "2/2"), a known
  Phase 3 data-reconstruction limitation (multi-part brand replies aren't
  stitched together — see Phase 3's decision log).
- Hypothesis: this is not a hallucination in the usual sense (the
  generator didn't invent anything) — it's a garbage-in/garbage-out
  failure one layer upstream, in the historical data itself.
- Possible fix: detect and either stitch or discard multi-part
  brand-response fragments during Phase 3's conversation reconstruction
  (cases whose `brand_response` starts with a bare "N:" or "N/M" pattern
  are a cheap heuristic to flag candidates), or add a generation-time
  sanity check that rejects a draft reply starting with an orphaned
  fragment marker.

**This is a recurring pattern, not a one-off** — confirmed by another
real instance found while manually scoring the Phase 14 human-agreement
sample, plus one important **self-correction**:

- `gold_0089` ("...FB profile that doesn't use my [university email]")
  drew a draft reply that is itself cut off mid-sentence: *"...as long as
  you're currently enrolled in an accredited college or..."* Checked
  against the full retrieved evidence (not just the reply text): the
  top-matched historical case (`case_1101316`, an exact duplicate of this
  customer's message) has the *identical* truncated fragment as its real
  historical `brand_response` — confirming this is a genuine orphaned
  multi-part-reply artifact in the source data, the same failure class as
  `gold_0034`, not a generation error.
- **Self-correction:** an earlier draft of this document also flagged
  `gold_0243` ("2nd mo. in a row... my playlist disappear" → drew a reply
  citing the "Downloads unexpectedly removed" help article) as a
  downloads-vs-playlists evidence mismatch. That assessment was made
  without the retrieved cases' actual text (a symptom of the same
  evidence-stripping bug documented in `DECISION_LOG.md`'s Phase 14
  entry). With the full evidence visible, multiple retrieved cases —
  including one whose customer message is literally *"why have all of my
  playlists disappeared????"* — genuinely do point to that same help
  article, meaning this is SpotifyCares' actual consistent historical
  practice, not a mismatch the generator introduced. Reported here rather
  than silently dropped, because getting this wrong on a first pass and
  correcting it once better evidence was available is itself the kind of
  finding this section exists to surface honestly.

**A positive counter-example worth noting alongside these:** `gold_0017`
("message songs to friends") also drew on a two-part historical case
(`case_2017301`/`case_2017303`, a "1:"/"2:" split, the same shape of
fragmentation as `gold_0034`), but this time the generator successfully
synthesized a single coherent reply from both halves rather than
reproducing a raw fragment. The failure mode isn't universal — sometimes
the model recovers from fragmented evidence, sometimes it doesn't, and
neither this analysis nor the current pipeline can yet predict which.

---

## 5. Multi-intent message: a technical complaint bundled with a cancellation threat

**Example — `gold_0261`:**
- Customer message: *"how do I turn off the autolaunch? Every time I get in my car your app takes over! I don't pay to get frustrated!!! I will cancel my family subscription if this isn't resolved."*
- Predicted: `playback_technical_issue` (confidence 0.85) — the classifier
  picked the surface technical question ("how do I turn off the
  autolaunch") over the trailing cancellation threat.
- Expected: `cancellation_or_refund_request` (my Phase 5 label prioritized
  the explicit threat as the dominant signal).
- What went wrong / notable nuance: the intent was misclassified, but the
  **final action was still correctly ESCALATE** — not because the system
  recognized the cancellation threat, but because retrieval similarity for
  this message happened to fall below the 0.70 threshold (0.64) anyway.
  The escalation layer's independent similarity check acted as an
  accidental safety net here.
- Hypothesis: single-label intent classification structurally cannot
  represent a message that genuinely contains two intents; whichever one
  is textually more prominent (here, the specific technical question) wins,
  even when the *emotionally* dominant content (the threat) is what a
  human would prioritize.
- Possible fix: this is a real limitation of the single-intent-label
  design, not a bug — properly addressing it means either multi-label
  classification or a dedicated "contains a churn/cancellation signal"
  side-check independent of the primary intent, run regardless of what
  the top intent came back as.

---

## What these five failures have in common

Four of the five are failures of the **escalation layer's rule
completeness**, not the underlying intent classifier (which is 84.7%
accurate) or the retriever (0.86 mean similarity) — both of the core AI
components are working about as well as their headline numbers suggest.
The system's weakest point is specifically the hand-written rules meant
to catch what those components' raw outputs (confidence, similarity)
can't see on their own: compounding circumstances, paraphrased
repeated-complaint language, and taxonomy-boundary judgment calls. This
matches — and gives concrete, real evidence for — the finding already
recorded in Phase 13's decision log: escalation accuracy (60.3%) is the
metric that actually predicts deployment safety, and it lags well behind
the more impressive-looking intent accuracy.
