"""
KYC Prioritization Queue
========================
Generates a ranked top-50 KYC backlog across desks using a weighted scoring
model with P0 escalation and per-desk capacity caps.

Usage:
    python kyc_prioritization.py                  # run with sample data
    python kyc_prioritization.py --csv input.csv  # run with your own data

Input CSV columns (if providing your own data):
    desk, client, type, revenue_k, age_days, reg_risk, is_p0
    is_p0 should be True/False or 1/0

Weights (adjustable via CLI flags or by editing DEFAULTS below):
    --w-revenue     float  0-1   weight for client revenue tier     (default 0.40)
    --w-age         float  0-1   weight for age of item in days     (default 0.30)
    --w-reg         float  0-1   weight for regulatory risk score   (default 0.20)
    --w-complexity  float  0-1   weight for KYC complexity          (default 0.10)
    --desk-cap      int    %     max % of top-50 slots per desk     (default 40)
    --top-n         int          number of items to output          (default 50)
"""

import argparse
import csv
import io
import sys
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS = {
    "w_revenue": 0.40,
    "w_age": 0.30,
    "w_reg": 0.20,
    "w_complexity": 0.10,
    "desk_cap_pct": 40,
    "top_n": 50,
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class KYCItem:
    desk: str
    client: str
    kyc_type: str
    revenue_k: float        # annual revenue in $k
    age_days: int           # days since item was opened
    reg_risk: float         # regulatory risk score 1-10
    complexity: float       # KYC complexity score 1-10
    is_p0: bool = False

    # computed fields
    score: float = field(default=0.0, init=False)
    rank: Optional[int] = field(default=None, init=False)


# ---------------------------------------------------------------------------
# Sample data generator
# ---------------------------------------------------------------------------

def generate_sample_data() -> List[KYCItem]:
    """Returns a realistic synthetic dataset matching the scenario discussed:
    Rates (15 items), FX (7), Credit (6), Equities (8)."""

    raw = [
        # desk,        client,           type,               rev,  age, reg, cplx, p0
        ("Rates",  "Blackrock",       "Periodic Review",    900,  120,  8,   6,  True),
        ("Rates",  "Vanguard",        "EDD",                850,   45,  9,   8,  True),
        ("Rates",  "Citadel",         "Onboarding",         700,   30,  7,   7, False),
        ("Rates",  "Bridgewater",     "Periodic Review",    650,   90,  6,   5, False),
        ("Rates",  "AQR Capital",     "Re-papering",        500,  150,  5,   4, False),
        ("Rates",  "Two Sigma",       "Sanctions Check",    480,   10,  9,   3, False),
        ("Rates",  "DE Shaw",         "Onboarding",         460,   60,  6,   6, False),
        ("Rates",  "Man Group",       "Periodic Review",    430,  100,  5,   5, False),
        ("Rates",  "Millennium",      "EDD",                410,   75,  8,   7, False),
        ("Rates",  "Renaissance",     "Re-papering",        400,  180,  7,   4, False),
        ("Rates",  "Point72",         "Onboarding",         380,   20,  6,   5, False),
        ("Rates",  "Baupost",         "Periodic Review",    360,  130,  5,   4, False),
        ("Rates",  "Pershing Sq",     "EDD",                340,   55,  7,   6, False),
        ("Rates",  "Third Point",     "Sanctions Check",    300,    8,  8,   3, False),
        ("Rates",  "Och-Ziff",        "Re-papering",        280,  160,  5,   4, False),

        ("FX",     "JPMorgan",        "Periodic Review",    950,   95,  7,   6,  True),
        ("FX",     "Goldman",         "EDD",                880,   40,  8,   8, False),
        ("FX",     "PIMCO",           "Onboarding",         600,   25,  6,   5, False),
        ("FX",     "Schroders",       "Re-papering",        420,  110,  5,   4, False),
        ("FX",     "Amundi",          "Sanctions Check",    390,   15,  9,   3, False),
        ("FX",     "Invesco",         "Periodic Review",    350,   70,  5,   4, False),
        ("FX",     "T Rowe Price",    "EDD",                310,   85,  6,   6, False),

        ("Credit", "Winton",          "Onboarding",         470,   35,  7,   6, False),
        ("Credit", "Brevan Howard",   "Periodic Review",    440,  140,  6,   5, False),
        ("Credit", "Nuveen",          "EDD",                400,   50,  8,   7, False),
        ("Credit", "Putnam",          "Re-papering",        320,  170,  5,   4, False),
        ("Credit", "Wellington",      "Sanctions Check",    290,   12,  9,   3, False),
        ("Credit", "Dimensional",     "Periodic Review",    270,  105,  5,   4, False),

        ("Equities", "Arrowstreet",   "Onboarding",         510,   28,  7,   6, False),
        ("Equities", "Fidelity",      "EDD",                780,   65,  8,   8, False),
        ("Equities", "State Street",  "Periodic Review",    560,  125,  6,   5, False),
        ("Equities", "Norges Bank",   "Re-papering",        490,  155,  5,   4, False),
        ("Equities", "CalPERS",       "Sanctions Check",    450,   18,  9,   3, False),
        ("Equities", "Ontario Teachers","EDD",              420,   80,  7,   7, False),
        ("Equities", "GIC Singapore", "Onboarding",         380,   42,  8,   6, False),
        ("Equities", "CPPIB",         "Periodic Review",    360,  115,  5,   4, False),
    ]

    return [
        KYCItem(
            desk=r[0], client=r[1], kyc_type=r[2],
            revenue_k=r[3], age_days=r[4], reg_risk=r[5],
            complexity=r[6], is_p0=r[7]
        )
        for r in raw
    ]


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------

def load_from_csv(path: str) -> List[KYCItem]:
    items = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            try:
                items.append(KYCItem(
                    desk=row["desk"].strip(),
                    client=row["client"].strip(),
                    kyc_type=row.get("type", "Unknown").strip(),
                    revenue_k=float(row["revenue_k"]),
                    age_days=int(row["age_days"]),
                    reg_risk=float(row["reg_risk"]),
                    complexity=float(row.get("complexity", 5)),
                    is_p0=str(row.get("is_p0", "False")).strip().lower() in ("true", "1", "yes"),
                ))
            except (KeyError, ValueError) as e:
                print(f"  Warning: skipping row {i} — {e}", file=sys.stderr)
    return items


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_field(items: List[KYCItem], attr: str) -> dict:
    """Returns a dict mapping item id -> normalized value [0, 1]."""
    values = [getattr(item, attr) for item in items]
    lo, hi = min(values), max(values)
    if hi == lo:
        return {id(item): 1.0 for item in items}
    return {id(item): (getattr(item, attr) - lo) / (hi - lo) for item in items}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_items(
    items: List[KYCItem],
    w_revenue: float,
    w_age: float,
    w_reg: float,
    w_complexity: float,
) -> None:
    """Assigns a score [0, 100] to each item in-place."""
    # Renormalize weights in case they don't sum to 1
    total = w_revenue + w_age + w_reg + w_complexity
    if total == 0:
        raise ValueError("All weights are zero — at least one must be positive.")
    wr, wa, wrg, wc = w_revenue/total, w_age/total, w_reg/total, w_complexity/total

    rev_n   = normalize_field(items, "revenue_k")
    age_n   = normalize_field(items, "age_days")
    reg_n   = normalize_field(items, "reg_risk")
    cplx_n  = normalize_field(items, "complexity")

    for item in items:
        item.score = round(
            (rev_n[id(item)]  * wr
           + age_n[id(item)]  * wa
           + reg_n[id(item)]  * wrg
           + cplx_n[id(item)] * wc) * 100, 1
        )


# ---------------------------------------------------------------------------
# Queue builder
# ---------------------------------------------------------------------------

def build_queue(
    items: List[KYCItem],
    desk_cap_pct: int,
    top_n: int,
) -> List[KYCItem]:
    """
    Returns the prioritized top-N list:
    1. P0 items first (sorted by score desc) — they always cut the line.
    2. Remaining items sorted by score desc, subject to per-desk cap.
    3. If cap leaves slots unfilled, backfill without cap.
    """
    max_per_desk = max(1, round(top_n * desk_cap_pct / 100))

    p0_items = sorted([i for i in items if i.is_p0],     key=lambda x: -x.score)
    queue    = sorted([i for i in items if not i.is_p0], key=lambda x: -x.score)

    result = list(p0_items)
    desk_count: dict = {}

    # First pass — respect desk cap
    for item in queue:
        if len(result) >= top_n:
            break
        count = desk_count.get(item.desk, 0)
        if count < max_per_desk:
            result.append(item)
            desk_count[item.desk] = count + 1

    # Second pass — backfill if cap left gaps
    if len(result) < top_n:
        queued_ids = {id(i) for i in result}
        for item in queue:
            if len(result) >= top_n:
                break
            if id(item) not in queued_ids:
                result.append(item)

    # Assign ranks
    for rank, item in enumerate(result, start=1):
        item.rank = rank

    return result[:top_n]


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_queue(queue: List[KYCItem]) -> None:
    COL = {
        "rank":       4,
        "desk":       9,
        "client":     20,
        "type":       18,
        "revenue":    10,
        "age":         8,
        "reg":         5,
        "score":       6,
        "status":      8,
    }

    sep = "-" * (sum(COL.values()) + len(COL) * 3)
    header = (
        f"{'#':>{COL['rank']}}  "
        f"{'Desk':<{COL['desk']}}  "
        f"{'Client':<{COL['client']}}  "
        f"{'Type':<{COL['type']}}  "
        f"{'Revenue':>{COL['revenue']}}  "
        f"{'Age(d)':>{COL['age']}}  "
        f"{'Reg':>{COL['reg']}}  "
        f"{'Score':>{COL['score']}}  "
        f"{'Status':<{COL['status']}}"
    )

    print()
    print("  KYC PRIORITIZATION QUEUE")
    print(sep)
    print(header)
    print(sep)

    for item in queue:
        status = "[ P0 ]" if item.is_p0 else "queue"
        print(
            f"{item.rank:>{COL['rank']}}  "
            f"{item.desk:<{COL['desk']}}  "
            f"{item.client:<{COL['client']}}  "
            f"{item.kyc_type:<{COL['type']}}  "
            f"${item.revenue_k:>{COL['revenue']-1},.0f}k  "
            f"{item.age_days:>{COL['age']}}  "
            f"{item.reg_risk:>{COL['reg']}.0f}  "
            f"{item.score:>{COL['score']}.1f}  "
            f"{status:<{COL['status']}}"
        )

    print(sep)


def print_summary(queue: List[KYCItem], all_items: List[KYCItem]) -> None:
    from collections import Counter
    desk_counts = Counter(i.desk for i in queue)
    p0_count    = sum(1 for i in queue if i.is_p0)
    avg_score   = sum(i.score for i in queue) / len(queue) if queue else 0

    print()
    print("  SUMMARY")
    print(f"  Total items in backlog : {len(all_items)}")
    print(f"  Items in top-{queue[-1].rank if queue else 0:<2}         : {len(queue)}")
    print(f"  P0 escalations         : {p0_count}")
    print(f"  Average score          : {avg_score:.1f}")
    print()
    print("  Desk breakdown:")
    for desk, count in sorted(desk_counts.items(), key=lambda x: -x[1]):
        pct = count / len(queue) * 100
        bar = "█" * count
        print(f"    {desk:<12} {count:>3} items  ({pct:.0f}%)  {bar}")
    print()


def export_csv(queue: List[KYCItem], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank","desk","client","type","revenue_k","age_days","reg_risk","complexity","score","is_p0"])
        for item in queue:
            writer.writerow([
                item.rank, item.desk, item.client, item.kyc_type,
                item.revenue_k, item.age_days, item.reg_risk,
                item.complexity, item.score, item.is_p0
            ])
    print(f"  Exported to: {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="KYC backlog prioritization — generates a ranked top-N queue.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--csv",         metavar="FILE",  help="Path to input CSV file")
    parser.add_argument("--export",      metavar="FILE",  help="Export top-N queue to CSV")
    parser.add_argument("--w-revenue",   type=float, default=DEFAULTS["w_revenue"],    help="Weight for revenue")
    parser.add_argument("--w-age",       type=float, default=DEFAULTS["w_age"],        help="Weight for age")
    parser.add_argument("--w-reg",       type=float, default=DEFAULTS["w_reg"],        help="Weight for regulatory risk")
    parser.add_argument("--w-complexity",type=float, default=DEFAULTS["w_complexity"], help="Weight for KYC complexity")
    parser.add_argument("--desk-cap",    type=int,   default=DEFAULTS["desk_cap_pct"], help="Max %% of slots per desk")
    parser.add_argument("--top-n",       type=int,   default=DEFAULTS["top_n"],        help="Number of items to output")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    # Load data
    if args.csv:
        print(f"\n  Loading data from {args.csv}...")
        items = load_from_csv(args.csv)
        print(f"  Loaded {len(items)} items.")
    else:
        print("\n  No CSV provided — using sample data.")
        items = generate_sample_data()

    if not items:
        print("  Error: no items to process.", file=sys.stderr)
        sys.exit(1)

    # Print config
    total_w = args.w_revenue + args.w_age + args.w_reg + args.w_complexity
    print(f"\n  Weights  →  revenue {args.w_revenue:.0%}  |  age {args.w_age:.0%}  |  reg {args.w_reg:.0%}  |  complexity {args.w_complexity:.0%}  (sum {total_w:.0%})")
    print(f"  Desk cap →  max {args.desk_cap}% of top-{args.top_n} per desk  ({round(args.top_n * args.desk_cap / 100)} slots)")

    # Score & build queue
    score_items(items, args.w_revenue, args.w_age, args.w_reg, args.w_complexity)
    queue = build_queue(items, args.desk_cap, args.top_n)

    # Output
    print_queue(queue)
    print_summary(queue, items)

    if args.export:
        export_csv(queue, args.export)


if __name__ == "__main__":
    main()