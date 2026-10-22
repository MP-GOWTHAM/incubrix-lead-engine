"""Market facts computed from the verified lead list (used in tab 01 opportunities and the launch kit).

    python scripts/lead_stats.py   -> prints and writes output/lead_stats.json
"""

import csv
import json
import os
from collections import Counter
from statistics import median

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")


def main():
    leads = list(csv.DictReader(open(os.path.join(OUT, "leads.csv"), encoding="utf-8")))
    ev = {r["lead_id"]: r for r in csv.DictReader(open(os.path.join(OUT, "leads_evidence.csv"), encoding="utf-8"))}
    n = len(leads)
    need = Counter(t for r in ev.values() for t in r["need_types"].split("; ") if t)
    money = Counter(t for r in ev.values() for t in r["monetization_types"].split("; ") if t)
    socials = [r["socials"] for r in ev.values()]
    mins = [int(r["avg_minutes"]) for r in ev.values() if r["avg_minutes"]]
    no_short = sum(1 for s in socials if "TikTok" not in s and "YouTube" not in s and "Instagram" not in s)
    pct = lambda k: round(100 * k / n, 1)
    s = {
        "qualified": n,
        "countries": dict(Counter(r["country_iso2"] for r in leads).most_common()),
        "segments": dict(Counter(r["creator_segment"] for r in leads)),
        "priority": dict(Counter(r["priority"] for r in leads)),
        "best_channel": dict(Counter(r["best_channel"] for r in leads).most_common()),
        "backup_channel": dict(Counter(r["backup_channel"] or "(none)" for r in leads).most_common()),
        "pct_no_transcripts": pct(need["Captions/transcripts"]),
        "pct_repurposing_gap": pct(need["Repurposing into clips"]),
        "pct_no_shortform_linked": pct(no_short),
        "pct_publishing_gap": pct(need["Publishing consistency"]),
        "pct_video": pct(sum(1 for r in ev.values() if r["is_video"] == "True")),
        "median_episode_minutes": median(mins) if mins else None,
        "pct_sponsorship": pct(money["Sponsorship"]),
        "pct_membership": pct(money["Membership/subscription"]),
        "pct_course_product": pct(money["Course/product"]),
        "pct_service": pct(money["Service (coaching/consulting)"]),
        "pct_affiliate": pct(money["Affiliate"]),
        "median_items_30d": median(int(r["content_count_30d"]) for r in leads),
        "email_best_pct": pct(sum(1 for r in leads if r["best_channel"] == "Email")),
    }
    with open(os.path.join(OUT, "lead_stats.json"), "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
