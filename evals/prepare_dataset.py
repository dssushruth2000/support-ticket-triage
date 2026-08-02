"""Build a frozen labeled eval set (~250 tickets) from HuggingFace Bitext.

Ground-truth labels come from the dataset (option a) — not from Gemini — so the
agent under test is never graded against itself. A small handcrafted technical
slice fills the gap Bitext does not cover (ecommerce-only categories).

Usage:
  python -m evals.prepare_dataset
  python -m evals.prepare_dataset --n 250 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "eval_tickets.jsonl"

# Bitext intent/category -> our schema. refund/cancellation are first-class so
# the Phase 2 guardrails can be scored for missed/false escalations.
INTENT_TO_CATEGORY: dict[str, str] = {
    # password / account
    "recover_password": "password_reset",
    "registration_problems": "account",
    "create_account": "account",
    "delete_account": "account",
    "edit_account": "account",
    "switch_account": "account",
    # money / lifecycle (always escalate)
    "cancel_order": "cancellation",
    "check_cancellation_fee": "cancellation",
    "get_refund": "refund",
    "track_refund": "refund",
    "check_refund_policy": "refund",
    "payment_issue": "billing",
    "check_payment_methods": "billing",
    "check_invoice": "billing",
    "get_invoice": "billing",
    # low-risk FAQ-ish
    "complaint": "faq",
    "review": "faq",
    "contact_customer_service": "faq",
    "contact_human_agent": "faq",
    "delivery_options": "faq",
    "delivery_period": "faq",
    "newsletter_subscription": "faq",
    "change_shipping_address": "faq",
    "set_up_shipping_address": "faq",
    "change_order": "faq",
    "place_order": "faq",
    "track_order": "faq",
}

# Per-category targets for a balanced ~250-ticket set.
TARGETS: dict[str, int] = {
    "billing": 40,
    "refund": 40,
    "cancellation": 35,
    "password_reset": 30,
    "account": 35,
    "faq": 40,
    "technical": 30,
}

# Synthetic technical tickets — Bitext has no technical/outage class. Labeled
# here by hand (not by Gemini) so the answer key stays independent of the model.
TECHNICAL_SEED: list[dict[str, str]] = [
    {
        "subject": "Dashboard won't load",
        "body": "The app dashboard spins forever and never finishes loading. Started about an hour ago.",
    },
    {
        "subject": "API returning 500 errors",
        "body": "Our integration is getting HTTP 500 from /v1/orders. Is there an outage?",
    },
    {
        "subject": "App keeps crashing on launch",
        "body": "The mobile app crashes immediately after the splash screen on Android 14.",
    },
    {
        "subject": "Login page is down",
        "body": "Going to the sign-in URL shows a blank page / gateway error.",
    },
    {
        "subject": "Slow search performance",
        "body": "Product search takes 20+ seconds and often times out. This is a regression from last week.",
    },
    {
        "subject": "Webhook delivery failing",
        "body": "Our webhook endpoint stopped receiving events around 09:00 UTC. Status page looks green.",
    },
    {
        "subject": "Export CSV hangs",
        "body": "Clicking Export report freezes the UI and never downloads the CSV.",
    },
    {
        "subject": "2FA codes not arriving",
        "body": "SMS two-factor codes never arrive. Email codes work. Possible SMS provider outage?",
    },
    {
        "subject": "Upload button broken",
        "body": "Uploading attachments fails with 'network error' even on a stable connection.",
    },
    {
        "subject": "Notifications delayed",
        "body": "In-app notifications arrive hours late. Push notifications seem completely down.",
    },
    {
        "subject": "Graph charts not rendering",
        "body": "Analytics charts show blank canvases. Browser console shows a JS error.",
    },
    {
        "subject": "SSO login fails",
        "body": "SAML SSO redirects fail with an Invalid Assertion error after our IdP upgrade.",
    },
    {
        "subject": "Background jobs stuck",
        "body": "Queued jobs stay in 'processing' for hours. Sync is completely stuck.",
    },
    {
        "subject": "Mobile offline mode broken",
        "body": "Offline mode no longer syncs changes when we reconnect. Data is lost.",
    },
    {
        "subject": "Rate limit false positives",
        "body": "API calls that used to work now return 429 even well under our documented limit.",
    },
    {
        "subject": "Search index stale",
        "body": "New products don't appear in search for hours. Looks like indexing is broken.",
    },
    {
        "subject": "Realtime chat disconnects",
        "body": "Support chat websocket disconnects every few minutes with code 1006.",
    },
    {
        "subject": "PDF generation error",
        "body": "Generating invoices as PDF throws 'renderer failed'. Started after today's deploy.",
    },
    {
        "subject": "Timezone display wrong",
        "body": "All timestamps show UTC instead of the user's local timezone after the update.",
    },
    {
        "subject": "Dark mode CSS broken",
        "body": "In dark mode, text is unreadable (black on black) on the settings page.",
    },
    {
        "subject": "Image CDN 404s",
        "body": "Product images return 404 from the CDN even though they exist in the catalog.",
    },
    {
        "subject": "Email deliverability drop",
        "body": "Transactional emails suddenly go to spam. SPF/DKIM look fine on our side.",
    },
    {
        "subject": "Calendar sync failing",
        "body": "Google Calendar sync stopped updating events. Last successful sync was yesterday.",
    },
    {
        "subject": "Checkout spinner stuck",
        "body": "Checkout hangs on 'Processing payment…' and never completes or errors.",
    },
    {
        "subject": "Admin role permissions broken",
        "body": "Admins suddenly cannot access the users page — getting 403 Forbidden.",
    },
    {
        "subject": "Memory leak on long sessions",
        "body": "Browser tab memory climbs until the page freezes after ~2 hours of use.",
    },
    {
        "subject": "Webhook signature mismatch",
        "body": "Webhook HMAC verification started failing after the secret rotation this morning.",
    },
    {
        "subject": "Mobile push token invalid",
        "body": "All iOS devices report invalid push tokens after the latest app update.",
    },
    {
        "subject": "Database timeouts",
        "body": "Many pages fail with 'statement timeout'. Feels like a DB performance issue.",
    },
    {
        "subject": "Feature flag not applying",
        "body": "We enabled a flag in the console but the new UI never appears for any users.",
    },
]

_PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}")


def _fill_placeholders(text: str, ticket_idx: int) -> str:
    """Replace Bitext {{Entity}} slots with deterministic fake values."""
    replacements = {
        "Order Number": f"ORD-{10000 + ticket_idx}",
        "Invoice Number": f"INV-{20000 + ticket_idx}",
        "Refund Amount": f"${(ticket_idx % 50) + 10}.00",
        "Money Amount": f"${(ticket_idx % 80) + 5}.00",
        "Account Type": "Pro",
        "Profile": "profile",
        "Online Order Interaction": "the order page",
        "Online Payment Interaction": "checkout",
        "Online Navigation Step": "settings",
        "Online Customer Support Channel": "email",
        "Website URL": "https://example.com",
        "Customer Support Email": "support@example.com",
        "Customer Support Phone Number": "1-800-555-0100",
        "Client First Name": "Alex",
        "Client Last Name": "Rivera",
        "Salutation": "Hi",
        "Date": "2026-07-01",
        "Date Range": "last month",
        "Delivery City": "Austin",
        "Delivery Country": "US",
        "Shipping Cut-off Time": "3pm",
        "Account Category": "business",
        "Account Change": "upgrade",
        "Upgrade Account": "Pro plan",
        "Program": "loyalty program",
        "Store Location": "online store",
        "Live Chat Support": "live chat",
        "Online Company Portal Info": "the customer portal",
        "Settings": "account settings",
        "Profile Type": "personal",
    }

    def repl(match: re.Match[str]) -> str:
        key = match.group(0)[2:-2].strip()
        return replacements.get(key, "N/A")

    return _PLACEHOLDER_RE.sub(repl, text)


def _subject_from_body(body: str, intent: str) -> str:
    clean = " ".join(body.strip().split())
    if len(clean) <= 72:
        return clean
    return clean[:69].rstrip() + "..."


def _expected_action(category: str) -> str:
    from app.agent.guardrails import (
        AUTO_RESPOND,
        DRAFT_FOR_REVIEW,
        ESCALATE_TO_HUMAN,
        HIGH_RISK_CATEGORIES,
        AUTO_RESPOND_CATEGORIES,
    )

    if category in HIGH_RISK_CATEGORIES:
        return ESCALATE_TO_HUMAN
    if category in AUTO_RESPOND_CATEGORIES:
        # Gold assumes a competent agent will clear the 0.9 confidence bar on
        # these low-risk categories; the scorer also tracks safety separately.
        return AUTO_RESPOND
    return DRAFT_FOR_REVIEW


def _customer_id_for(category: str, idx: int) -> str | None:
    if category in {"billing", "refund", "cancellation"}:
        return "CUST-1001" if idx % 2 == 0 else "CUST-1002"
    return f"CUST-{3000 + (idx % 200)}"


def _load_bitext_buckets() -> dict[str, list[dict]]:
    from datasets import load_dataset

    ds = load_dataset(
        "bitext/Bitext-customer-support-llm-chatbot-training-dataset", split="train"
    )
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in ds:
        intent = str(row["intent"])
        category = INTENT_TO_CATEGORY.get(intent)
        if category is None:
            continue
        buckets[category].append(
            {
                "instruction": str(row["instruction"]),
                "intent": intent,
                "source_category": str(row["category"]),
            }
        )
    return buckets


def build_eval_set(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    buckets = _load_bitext_buckets()

    # Scale targets if the user asks for a different N while keeping ratios.
    base_total = sum(TARGETS.values())
    scaled = {
        cat: max(1, round(target * n / base_total)) for cat, target in TARGETS.items()
    }
    # Fix rounding drift.
    while sum(scaled.values()) > n:
        cat = max(scaled, key=scaled.get)
        scaled[cat] -= 1
    while sum(scaled.values()) < n:
        cat = min(scaled, key=scaled.get)
        scaled[cat] += 1

    tickets: list[dict] = []
    idx = 0

    for category, count in scaled.items():
        if category == "technical":
            pool = list(TECHNICAL_SEED)
            rng.shuffle(pool)
            chosen = (pool * ((count // len(pool)) + 1))[:count]
            for item in chosen:
                idx += 1
                tickets.append(
                    {
                        "id": f"eval-{idx:04d}",
                        "subject": item["subject"],
                        "body": item["body"],
                        "customer_id": _customer_id_for(category, idx),
                        "gold_category": category,
                        "gold_action": _expected_action(category),
                        "source": "handcrafted_technical",
                        "source_intent": None,
                    }
                )
            continue

        pool = list(buckets.get(category, []))
        if not pool:
            raise RuntimeError(f"No Bitext rows mapped to category={category}")
        rng.shuffle(pool)
        chosen = (pool * ((count // len(pool)) + 1))[:count]
        for item in chosen:
            idx += 1
            body = _fill_placeholders(item["instruction"], idx)
            # Capitalize lightly so it reads like a ticket body.
            body = body[0].upper() + body[1:] if body else body
            tickets.append(
                {
                    "id": f"eval-{idx:04d}",
                    "subject": _subject_from_body(body, item["intent"]),
                    "body": body,
                    "customer_id": _customer_id_for(category, idx),
                    "gold_category": category,
                    "gold_action": _expected_action(category),
                    "source": "bitext",
                    "source_intent": item["intent"],
                }
            )

    rng.shuffle(tickets)
    # Re-number after shuffle for stable ids in run order.
    for i, t in enumerate(tickets, start=1):
        t["id"] = f"eval-{i:04d}"
    return tickets


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the Phase 3 eval ticket set.")
    parser.add_argument("--n", type=int, default=250, help="Number of tickets (default 250).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    tickets = build_eval_set(args.n, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for t in tickets:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    from collections import Counter

    counts = Counter(t["gold_category"] for t in tickets)
    print(f"Wrote {len(tickets)} tickets -> {args.out}")
    for cat, c in sorted(counts.items()):
        print(f"  {cat:16s} {c}")


if __name__ == "__main__":
    main()
