# SpotifyCares Intent Definitions

12 intents, discovered from real customer messages (not invented ahead of
time, and not Banking77's 77 labels). Methodology, full taxonomy reasoning,
and how to reproduce this: below.

## Methodology

1. Loaded only `split == "knowledge"` customer messages from
   `data/processed/support_cases.jsonl` (36,723 messages) — `golden_pool`
   is never touched during intent discovery, so category definitions can't
   be shaped around examples that will later be used for evaluation.
2. No LLM API key is configured for this project, so clustering assists
   discovery instead: TF-IDF (unigrams+bigrams, English stopwords,
   `min_df=5`, 5000 features) + KMeans, `k=30`, fixed seed — see
   `src/intents/discovery.py` and `scripts/build_intent_dataset.py`.
3. Read all 30 clusters' top TF-IDF terms and 8 example messages each
   (`data/processed/intent_discovery_clusters.json`) and, by hand: merged
   clusters that were really the same intent under different device/OS
   vocabulary (e.g. iOS bug reports, Android connectivity complaints, and
   generic "app not working" all became one `playback_technical_issue`),
   discarded clusters that were genuinely mixed/generic rather than one
   topic, and added 3 intents that were clearly present as real, recurring
   examples *within* other clusters but never dominated a cluster of their
   own at k=30 (`account_security_compromise`, `account_data_loss`,
   `cancellation_or_refund_request`).
4. The resulting cluster → intent mapping
   (`CLUSTER_TO_INTENT` in `src/intents/labels.py`) is applied to every
   knowledge-split message to produce weak (unverified) intent labels —
   used only to train the Phase 7 TF-IDF+LogisticRegression baseline, never
   to build the golden set (which Phase 5 labels by hand, independently).

## Why 12, and why these specific ones

Started from 30 raw clusters. Device/OS-specific technical clusters (app
crashes, iOS bug reports, Android connectivity, phone/download issues,
Apple Watch support) all shared the same underlying customer intent —
"something is broken, please fix it" — and the same actual resolution
pattern observed in Phase 1/3 sampling (ask for device/OS/version, suggest
a restart), so they were merged into one `playback_technical_issue`. This
single intent ends up being the largest by far (7,490 of 18,100 weakly
labeled messages, 41%) — a real, honest signal about this support
account's traffic, not an artifact of a bad taxonomy; it's flagged again
in `DECISION_LOG.md` as something to interrogate under Phase 16 ("what is
misleading about my headline number?").

Several clusters (ids 2, 5, 7, 9, 11, 26, 29 — 18,623 messages, just over
half the knowledge split) were discarded as too generic/mixed to serve as
a reliable weak-label source: their top TF-IDF terms were dataset-wide
common words ("spotify", "https", "help", "don't") rather than a specific
topic, and their example messages span unrelated subjects. Forcing a label
onto these would inject substantial noise into Phase 7's training data.
This does **not** mean half of all customer messages are uncategorizable —
a human labeling the golden set by hand (Phase 5) can and will assign a
real intent to messages that fell into a noise cluster here; it only means
automated clustering isn't a reliable *training-label* source for them.

## The 12 intents

### playback_technical_issue
Spotify (the app, web player, or a specific device) isn't working
correctly — playback failures, crashes, connectivity problems, or
something that used to work has stopped.

> "Premium member can't get online today at all. Stuck in offline mode.
> Tried reinstalling, changing proxy and restarting several times."

> "the song just keeps cutting off, every couple of seconds it just pauses itself"

**Boundary:** if the message also reports missing/deleted playlists or
library data, prefer `account_data_loss`. Pure "please add X to the
catalog" with no malfunction is `feature_request_or_missing_content`.

### account_access_issue
Customer cannot log in, reset their password, or their account is
otherwise inaccessible (e.g. tied to a Facebook account they lost access to).

> "i deleted my Facebook account. i cannot log into my Spotify account and
> i can't reset the password. can you help me log in?"

**Boundary:** if access was lost specifically because of suspected
unauthorized/hacked activity, prefer `account_security_compromise`.

### account_security_compromise
Customer reports or suspects unauthorized access to their account —
hacking, unrecognized activity, or a compromise that led to unexpected
charges.

> "we got premium and they tampered/hacked our info"

**Boundary:** general login/password-reset requests with no suspected
compromise belong in `account_access_issue`. *(No dedicated cluster —
grounded in examples found within clusters 1 and 16; no automated
weak-label coverage, see Methodology.)*

### account_data_loss
Playlists, saved songs, listening history, or other personal library data
have disappeared or been deleted.

> "All of my playlists have disappeared from my Spotify account and I
> keep getting an error code... Might they be in your backup?"

**Boundary:** if data loss happened alongside a password reset/login
event, still classify as `account_data_loss` when the disappeared data is
the main complaint. *(No dedicated cluster — grounded in examples found
within clusters 1 and 15; no automated weak-label coverage.)*

### billing_subscription_issue
Customer was charged an unexpected or incorrect amount, or their account
shows the wrong subscription tier (e.g. Premium not activating, still
shows as Free after paying).

> "hi why is my spotify account still on free when i just paid for
> premium...?"

**Boundary:** explicit cancel/refund requests go to
`cancellation_or_refund_request`; student-discount-specific billing goes
to `student_discount_issue`.

### cancellation_or_refund_request
Customer explicitly wants to cancel their subscription/account, or is
asking for a refund.

> "I want to close my spotify account but i no longer have access to my
> email account. HELP"

**Boundary:** a billing complaint that doesn't explicitly ask to cancel or
get money back stays in `billing_subscription_issue`. *(No dedicated
cluster — grounded in examples found within clusters 1, 4, and 6; no
automated weak-label coverage.)*

### student_discount_issue
Problems specifically with the student premium discount — not applying,
charged full price despite verified enrollment, or eligibility questions.

> "You guys charged me 9.99 when I'm on a student plan."

**Boundary:** general billing issues unrelated to student status belong in
`billing_subscription_issue`.

### family_plan_issue
Problems with a Family Premium plan — inviting/adding members, a member
unable to join or log in, or family plan pricing questions.

> "I'm having problems with my Premium Family account. Two of my family
> members have been unable to sign in."

**Boundary:** a login problem on an individual (non-family) account
belongs in `account_access_issue`.

### feature_request_or_missing_content
Customer is asking for a new feature, or for specific music/content (a
song, album, or artist) to be added or fixed in the catalog.

> "Please add this song to your app. I beg. Love this soundtrack."

**Boundary:** something that used to work now failing is
`playback_technical_issue`, not a feature request.

### customer_service_feedback
Feedback about the support experience itself — praise for good service, or
complaints about being ignored, no phone number, or slow responses.

> "When you need help from @SpotifyCares but there's no phone number for
> customer service"

**Boundary:** a specific unanswered DM follow-up is `dm_followup`; this
intent is for broader commentary on the support channel/process.

### dm_followup
Customer is following up on a direct message they already sent — asking
if it was received, or reporting no response yet.

> "So far I've sent 3 tweets and two DM's - no response."

**Boundary:** a first-time request to be contacted via DM (not yet sent)
is not this intent — classify by the underlying issue instead.

### acknowledgment_closing
A short acknowledgment, thanks, or closing remark with no new request —
typically the customer's reply after their issue was already addressed.

> "Thank you. It's working again!"

**Boundary:** if the message reports a new problem or that the issue is
still unresolved, classify by that issue instead.

## Weak-label distribution (knowledge split, for Phase 7 training)

From `data/processed/intent_distribution.json` — 18,100 of 36,723
knowledge messages (49%) received a weak label; the rest fell into
discarded/noise clusters (see Methodology).

| intent | weak-labeled count |
|---|---:|
| playback_technical_issue | 7,490 |
| billing_subscription_issue | 2,919 |
| account_access_issue | 2,252 |
| feature_request_or_missing_content | 1,714 |
| acknowledgment_closing | 1,161 |
| family_plan_issue | 1,024 |
| student_discount_issue | 894 |
| dm_followup | 420 |
| customer_service_feedback | 226 |
| account_security_compromise | 0 (no dedicated cluster — see above) |
| account_data_loss | 0 (no dedicated cluster — see above) |
| cancellation_or_refund_request | 0 (no dedicated cluster — see above) |

## Reproduce

```bash
python -m scripts.build_intent_dataset
```
