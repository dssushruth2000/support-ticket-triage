"""Clear cache rows for misclassified tickets so they can be re-run."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "evals" / "results" / "cache_gemini_gemini-flash-lite-latest.jsonl"


def main() -> None:
    rows = [
        json.loads(line)
        for line in CACHE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    keep: list[dict] = []
    drop = 0
    for row in rows:
        gold = row.get("gold_category")
        pred = row.get("pred_category")
        if row.get("error") or not pred or gold != pred:
            drop += 1
            continue
        keep.append(row)
    CACHE.write_text("".join(json.dumps(r) + "\n" for r in keep), encoding="utf-8")
    print(f"kept_correct={len(keep)} cleared_wrong_or_error={drop}")


if __name__ == "__main__":
    main()
