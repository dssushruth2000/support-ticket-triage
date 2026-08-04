"""Seed knowledge-base documents for RAG ingest.

Starts from the same policy/FAQ content the in-memory keyword matcher uses,
plus a few extra entries so vector search has a slightly richer corpus.
"""

from __future__ import annotations

SEED_DOCUMENTS: list[dict[str, str]] = [
    {
        "title": "Duplicate charge refund policy",
        "content": (
            "If a customer is charged more than once for the same subscription "
            "within 24 hours, the duplicate charge is eligible for an automatic "
            "refund. Refunds post within 5-7 business days."
        ),
    },
    {
        "title": "How to reset your password",
        "content": (
            "Users can reset their password via the 'Forgot password' link on the "
            "sign-in page. A reset link is emailed and expires after 60 minutes."
        ),
    },
    {
        "title": "Service outage troubleshooting",
        "content": (
            "If the app fails to load, first check the status page. Transient "
            "errors usually resolve within minutes; persistent issues should be "
            "escalated to the on-call engineer."
        ),
    },
    {
        "title": "Cancellation policy",
        "content": (
            "Subscriptions can be cancelled anytime. Cancellations take effect at "
            "the end of the current billing period; no partial-period refunds."
        ),
    },
    {
        "title": "Support business hours",
        "content": (
            "Live support is available Monday through Friday, 9:00 AM to 6:00 PM "
            "Eastern Time. Outside those hours, submit a ticket and we will "
            "respond on the next business day."
        ),
    },
    {
        "title": "Account email change",
        "content": (
            "Customers can update their account email from Settings > Profile. "
            "A confirmation link is sent to both the old and new addresses. "
            "The change completes after both links are confirmed."
        ),
    },
    {
        "title": "Pro plan features",
        "content": (
            "The Pro subscription includes priority support, advanced analytics, "
            "and up to 10 team seats. Annual plans receive two months free "
            "compared with month-to-month billing."
        ),
    },
    {
        "title": "Failed payment retry",
        "content": (
            "If a card payment fails, we retry automatically after 3 days and "
            "again after 7 days. After three failed attempts the subscription "
            "is paused until a valid payment method is on file."
        ),
    },
]
