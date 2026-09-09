"""Final, human-approved intent taxonomy for SpotifyCares.

Derived from inspecting real clustered customer messages — see
scripts/build_intent_dataset.py and data/processed/intent_discovery_clusters.json
(TF-IDF + KMeans, k=30, over the knowledge-split customer messages only).
Full reasoning for every merge/split/addition: docs/intent_definitions.md.

Do not hand-invent categories here without grounding them in that report.
"""

from __future__ import annotations

INTENTS: dict[str, dict] = {
    "playback_technical_issue": {
        "description": (
            "Spotify (the app, web player, or a specific device) isn't working correctly — "
            "playback failures, crashes, connectivity problems, or something that used to work "
            "has stopped."
        ),
        "examples": [
            "@SpotifyCares Premium member can't get online today at all. Stuck in offline mode. "
            "Tried reinstalling, changing proxy and restarting several times. What can I do?",
            "@SpotifyCares hi, the song just keeps cutting off, every couple of seconds it just pauses itself",
            "@SpotifyCares I have a sound touch (Bose) but the spotify app won't connect, it just tells me to try again later",
            "Hey @SpotifyCares why do my songs interrupt when my phone screen is off/locked (Android v7.0)",
        ],
        "boundary_notes": (
            "If the message ALSO reports missing/deleted playlists or library data, prefer "
            "account_data_loss. If it's purely 'please add X to the catalog' with no malfunction, "
            "prefer feature_request_or_missing_content."
        ),
    },
    "account_access_issue": {
        "description": (
            "Customer cannot log in, reset their password, or their account is otherwise "
            "inaccessible (e.g. tied to a Facebook account they lost access to)."
        ),
        "examples": [
            "@SpotifyCares i deleted my Facebook account. i cannot log into my Spotify account and "
            "i can't reset the password. can you help me log in?",
            "@SpotifyCares I'm trying to change my password but no email is coming up in my Spotify "
            "registered email address with the link to change it?",
            "@spotifycares I don't know what email you have on file but it's not any that I remember. Help me!!",
        ],
        "boundary_notes": (
            "If account access is lost specifically because of suspected unauthorized/hacked "
            "activity, prefer account_security_compromise."
        ),
    },
    "account_security_compromise": {
        "description": (
            "Customer reports or suspects unauthorized access to their account — hacking, "
            "unrecognized activity, or a compromise that led to unexpected charges."
        ),
        "examples": [
            "@115888 we got premium and they tampered/hacked our info",
            "@115888 Until your account gets compromised, then charged $16 after reporting it, and "
            "getting you to reply is like pulling teeth.",
        ],
        "boundary_notes": (
            "General login/password-reset requests with no mention of suspected compromise belong "
            "in account_access_issue."
        ),
    },
    "account_data_loss": {
        "description": "Playlists, saved songs, listening history, or other personal library data have disappeared or been deleted.",
        "examples": [
            "All of my playlists have disappeared from my Spotify account and I keep getting an "
            "error code... Might they be in your backup?",
            "@SpotifyCares I'm a Premium member. Recently, all of my playlists got deleted. I'm "
            "gutted - some of them were up to tens years old. Can you do anything to get them back?",
        ],
        "boundary_notes": (
            "If data loss happened alongside a password reset/login event, still classify as "
            "account_data_loss when the disappeared data is the customer's main complaint."
        ),
    },
    "billing_subscription_issue": {
        "description": (
            "Customer was charged an unexpected or incorrect amount, or their account shows the "
            "wrong subscription tier (e.g. Premium not activating, still shows as Free after paying)."
        ),
        "examples": [
            "@SpotifyCares My account got shut off after I corrected the fact that I was being "
            "over-charged for Premium. Supposed to get half off",
            "hi why is my spotify account still on free when i just paid for premium...? @115888 @SpotifyCares",
            "@SpotifyCares I can't upgrade Premium acct to family until Nov8 bc I am paid. U limit "
            "#of users-I should be able to include the users I want",
        ],
        "boundary_notes": (
            "If the customer explicitly asks to cancel or wants their money back, prefer "
            "cancellation_or_refund_request. If the discount in question is specifically the "
            "student plan, prefer student_discount_issue."
        ),
    },
    "cancellation_or_refund_request": {
        "description": "Customer explicitly wants to cancel their subscription/account, or is asking for a refund.",
        "examples": [
            "@SpotifyCares I want to close my spotify account but i no longer have access to my "
            "email account. HELP",
            "@SpotifyCares £99 for a year is hardly a comparison! Especially when apple have just "
            "offered me 3 free months as a trial...... #cancel ?",
        ],
        "boundary_notes": "A billing complaint that does not explicitly ask to cancel or get money back stays in billing_subscription_issue.",
    },
    "student_discount_issue": {
        "description": (
            "Problems specifically with the student premium discount — not applying, charged full "
            "price despite verified enrollment, or eligibility questions."
        ),
        "examples": [
            "You guys charged me 9.99 when I'm on a student plan. @SpotifyCares",
            "@spotifycares i'm a tcc student &amp; it keeps saying that i can't get a student "
            "discount anymore???",
            "@SpotifyCares No it is NOT. My issue still persist and I have been charged a 3rd F'ing "
            "time. I followed the student verification as well.",
        ],
        "boundary_notes": "General billing issues unrelated to student status belong in billing_subscription_issue.",
    },
    "family_plan_issue": {
        "description": (
            "Problems with a Family Premium plan — inviting/adding members, a member unable to "
            "join or log in, or family plan pricing questions."
        ),
        "examples": [
            "@SpotifyCares my friends invited me on spotify family through email. But every time i "
            "fill the address its always said somethings went wrong",
            "@SpotifyCares I'm having problems with my Premium Family account. Two of my family "
            "members have been unable to sign in.",
        ],
        "boundary_notes": "A login problem on an individual (non-family) account belongs in account_access_issue.",
    },
    "feature_request_or_missing_content": {
        "description": (
            "Customer is asking for a new feature, or for specific music/content (a song, album, "
            "or artist) to be added or fixed in the catalog."
        ),
        "examples": [
            "@115888 Please add this song to your app. I beg. Love this soundtrack.",
            "@SpotifyCares Well you're already in cahoots with Genius so maybe add the ability to "
            "search songs via lyrics in the search bar",
            "@115888 Are you not going to put @118062 new album reputation???",
        ],
        "boundary_notes": "If the customer reports something that used to work now failing, that's playback_technical_issue, not a feature request.",
    },
    "customer_service_feedback": {
        "description": (
            "Feedback about the support experience itself — praise for good service, or "
            "complaints about being ignored, no phone number, or slow responses."
        ),
        "examples": [
            "When you need help from @SpotifyCares but there's no phone number for customer service",
            "@115888 Just want to commend you guys for an excellent customer support / service. You guys are amazing!!!",
        ],
        "boundary_notes": "A specific unanswered DM follow-up belongs in dm_followup; this intent is for broader commentary on the support channel/process.",
    },
    "dm_followup": {
        "description": "Customer is following up on a direct message they already sent — asking if it was received, or reporting no response yet.",
        "examples": [
            "@SpotifyCares So far I've sent 3 tweets and two DM's - no response.",
            "Hi? @SpotifyCares I've sent the DM a while ago, has it been received?",
        ],
        "boundary_notes": "A first-time request to be contacted via DM (not yet sent) is not this intent — classify by the underlying issue instead.",
    },
    "acknowledgment_closing": {
        "description": "A short acknowledgment, thanks, or closing remark with no new request — typically the customer's reply after their issue was already addressed.",
        "examples": [
            "@SpotifyCares Thank you! :)",
            "@SpotifyCares thanks i appreciate it",
            "@SpotifyCares Thank you. It's working again!",
        ],
        "boundary_notes": "If the message reports a NEW problem or that the issue is still unresolved, classify by that issue instead (e.g. still not working -> playback_technical_issue).",
    },
}

# Maps a discovery cluster id (fixed-seed TF-IDF+KMeans, k=30, in
# scripts/build_intent_dataset.py) to one of the INTENTS keys above, or
# None to discard a cluster as noise / too mixed to use as a weak label.
#
# account_security_compromise, account_data_loss, and
# cancellation_or_refund_request are grounded in real examples that
# appeared *within* other clusters (see docs/intent_definitions.md) but
# never formed their own dominant cluster at k=30, so no cluster id maps
# to them — they exist for manual golden-set labeling (Phase 5) and the
# LLM classifier (Phase 8), but get no automated weak-label training
# coverage from this clustering pass. Documented, not hidden.
CLUSTER_TO_INTENT: dict[int, str | None] = {
    0: "playback_technical_issue",
    1: "account_access_issue",
    2: None,  # generic "hey"/mixed chatter, no single dominant topic
    3: "account_access_issue",
    4: "billing_subscription_issue",
    5: None,  # largest cluster (10,003) but most generic shared vocabulary; genuinely mixed topics
    6: "billing_subscription_issue",
    7: None,  # generic "need help"/"dm" requests with no specific topic
    8: "playback_technical_issue",
    9: None,  # generic mentions/complaints, no single dominant topic
    10: "playback_technical_issue",
    11: None,  # clustered on the word "don't", topics are a grab-bag
    12: "billing_subscription_issue",
    13: "dm_followup",
    14: "feature_request_or_missing_content",
    15: "playback_technical_issue",
    16: "customer_service_feedback",
    17: "feature_request_or_missing_content",
    18: "playback_technical_issue",
    19: "feature_request_or_missing_content",
    20: "acknowledgment_closing",
    21: "student_discount_issue",
    22: "acknowledgment_closing",
    23: "family_plan_issue",
    24: "acknowledgment_closing",
    25: "playback_technical_issue",
    26: None,  # mostly bare links/mentions, no coherent topic
    27: "playback_technical_issue",
    28: "playback_technical_issue",
    29: None,  # generic mixed mentions
}
