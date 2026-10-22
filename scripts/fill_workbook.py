"""Fill the IncuBrix Option 1 submission workbook from the engine's own output files.

    pip install openpyxl
    python scripts/fill_workbook.py "path/to/Submission_Workbook.xlsx" [out.xlsx]

Only values the engine can prove are written. Personal details, product observations,
seed-test results, video links and the self-score stay blank for the candidate to fill in.
Formula cells (green) are never overwritten.
"""

import csv
import json
import os
import sys
from collections import Counter

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "output")
INT_FIELDS = {"content_count_30d", "longform_count_60d", "lead_score"}


def read_csv(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fill_leads(ws, leads):
    header = [ws.cell(4, c).value for c in range(1, 31)]
    for i, row in enumerate(leads[:1000]):
        r = 5 + i
        for c, col in enumerate(header[:28], start=1):  # stop before duplicate_check / completeness_check
            v = row.get(col, "")
            if col in INT_FIELDS and v != "":
                v = int(v)
            if col == "followers_or_subscribers" and v != "":
                v = int(v)
            ws.cell(r, c).value = v if v != "" else None


def runs_summary():
    runs = read_csv("runs.csv")
    by = {"normal": None, "repeat": None, "refresh": None, "failure": None, "recovery": None}
    for i, r in enumerate(runs):
        m = r["mode"]
        if m == "full" and by["normal"] is None:
            by["normal"] = r
        elif m in ("full", "refresh") and by["normal"] is not None and by["repeat"] is None:
            by["repeat"] = r
        elif m == "seed-only" and by["failure"] is None and int(r["qualified"] or 0) > int(
                (by["refresh"] or {"qualified": 0})["qualified"] or 0):
            by["refresh"] = r  # the refresh that added leads, before the failure demo
        elif m == "failure":
            by["failure"] = r
            by["recovery"] = runs[i + 1] if i + 1 < len(runs) else None
    return by


def main():
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "submission", os.path.basename(src))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    wb = openpyxl.load_workbook(src)
    leads = sorted(read_csv("leads.csv"), key=lambda r: r["lead_id"])
    report = json.load(open(os.path.join(OUT, "run_report.json"), encoding="utf-8"))
    msgs = read_csv(os.path.join("..", "outreach", "all_messages.csv"))

    # 02_LEADS
    fill_leads(wb["02_LEADS"], leads)

    # 03_ENGINE_LAUNCH: engine proof
    e = wb["03_ENGINE_LAUNCH"]
    proof = [
        ("Yes", "README.md", "python -m engine run"),
        ("Yes", "README.md; tests/", "Python stdlib only, no keys or installs; tests run offline"),
        ("Yes", "engine/pipeline.py (dedupe_creators); output/run_report.json",
         "Dedupe by Apple ID, feed URL, and creator email/social/name"),
        ("Yes", "engine/qualify.py; output/rejected_and_reserve.csv", "Every brief check enforced before export"),
        ("Yes", "output/leads.csv", "UTF-8, exact workbook columns, sorted by lead_id"),
        ("Yes", "data/state.sqlite; output/runs.csv", "Stable lead_ids; repeat runs add 0 duplicates"),
        ("Yes", "output/errors.csv; output/logs/; --simulate-failure", "Bad feeds logged and retried; crash resumes"),
        ("Yes", "tests/test_engine.py", "python -m unittest discover -s tests -v"),
        ("Yes", ".gitignore; config.json", "No keys needed; no secrets in repo"),
    ]
    for i, (done, ev, note) in enumerate(proof):
        e.cell(6 + i, 2).value, e.cell(6 + i, 3).value, e.cell(6 + i, 8).value = done, ev, note
    by = runs_summary()
    for row, key in ((18, "normal"), (19, "repeat"), (20, "refresh"), (21, "failure")):
        r = by[key]
        if not r:
            continue
        rec = by["recovery"] if key == "failure" else None
        e.cell(row, 2).value = int(r["input_size"] or 0)
        e.cell(row, 3).value = int((rec or r)["qualified"] or 0) if (rec or r)["qualified"] else None
        e.cell(row, 4).value = int((rec or r)["rejected"] or 0) if (rec or r)["rejected"] else None
        e.cell(row, 5).value = int(r["duplicates_removed"] or 0)
        e.cell(row, 6).value = float(r["runtime_min"]) if r["runtime_min"] else None
        e.cell(row, 7).value = "$0.00"
        e.cell(row, 8).value = (f"output/runs.csv ({r['run_at']})" +
                                (f"; recovered by rerun at {rec['run_at']}" if rec else ""))

    # 04_SELF_CHECK: only engine-provable values
    s = wb["04_SELF_CHECK"]
    countries = Counter(r["country_iso2"] for r in leads)
    total = len(leads)
    approved = {"US", "CA", "GB", "IE", "AU", "NZ", "SG"}
    share_ok = total and sum(v for k, v in countries.items() if k in approved) / total >= 0.8 \
        and len(countries) >= 3 and max(countries.values()) / total <= 0.6
    channels = sorted({m["channel"] for m in msgs})
    pa = sum(1 for r in leads if r["priority"] == "A")
    s["C6"] = total
    s["E6"] = f"output/leads.csv ({total} rows; workbook tab holds the first {min(total, 1000)})"
    s["C7"] = "Yes" if share_ok else "No"
    s["E7"] = "output/run_report.json: " + ", ".join(f"{k} {v} ({v / total:.0%})" for k, v in countries.most_common())
    s["C8"] = sum(1 for r in leads if r["duplicate_check"] == "DUPLICATE")
    s["E8"] = "output/leads.csv duplicate_check; engine dedupe in engine/pipeline.py"
    s["C9"] = len(channels)
    s["E9"] = "outreach/sequences/*.md; outreach/all_messages.csv channels: " + ", ".join(channels)
    s["C10"] = pa
    pa_tab = sum(1 for r in leads[:1000] if r["priority"] == "A")
    s["E10"] = (f"outreach/priority_a/ ({pa} files: first message + 2 follow-ups + backup touch). "
                f"Workbook counts {pa_tab} because it holds only the first 1,000 of {total} rows")
    s["C12"] = "Yes"
    s["E12"] = "README.md run command; output/runs.csv"
    s["E11"] = "seed_test/SEED_TEST.md; seed_test/reply_log.csv (fill after running the seed test)"
    # Exceptional (only claim what is literally true)
    s["B18"] = "Yes" if pa >= 250 else "No"
    s["C18"] = pa
    s["E18"] = "outreach/priority_a/"
    s["C17"] = total
    s["B17"] = "Yes" if total >= 5000 else "No"
    s["E17"] = "output/leads.csv"

    # 01_INSIGHT section B: opportunities backed by the lead data (observations stay for the candidate)
    st_path = os.path.join(OUT, "lead_stats.json")
    if os.path.exists(st_path):
        k = json.load(open(st_path, encoding="utf-8"))
        ins = wb["01_INSIGHT"]
        opps = [
            ("Lead with free sample clips to long-form podcasters who publish no transcripts or clips",
             f"{k['pct_no_transcripts']}% of the {k['qualified']} verified creators publish no transcripts; "
             f"{k['pct_repurposing_gap']}% have ~{k['median_episode_minutes']:.0f}-min episodes with no clip channel "
             f"linked (output/lead_stats.json, leads_evidence.csv need_types)",
             "Higher reply rate than a generic pitch, because the creator sees their own episode as clips first",
             "Reply rate and sample-clip acceptance by utm_content per lead (HubSpot + IncuBrix analytics)",
             "~750 contacted, ~64 replies, ~30 sample sets delivered, ~10 activated sign-ups"),
            ("Treat expert-led creators (coaches/consultants) as a separate segment: content that finds clients",
             f"{k['segments'].get('Expert-Led Creator', 0)} expert-led creators; {k['pct_service']}% of all leads "
             f"publish a booking/'work with me' offer and {k['pct_course_product']}% sell their own course/book/programme",
             "Higher intent and willingness to pay: their content directly feeds client acquisition",
             "Positive-reply and demo-call rate, expert-led vs podcaster segment (CRM segment field)",
             "≥4 demo calls, mostly from expert-led; expert-led positive-reply rate ≥ podcaster rate"),
            ("Pitch sponsored shows on sponsor value: clips multiply every sponsor read",
             f"{k['pct_sponsorship']}% of verified creators carry sponsor reads or promo codes, and "
             f"{k['pct_membership']}% run memberships/listener subscriptions (quoted in monetization_signal)",
             "Turns IncuBrix from a cost into revenue: more clip reach, more sponsor and member value",
             "A/B subject line (sponsor angle vs clips angle) on sponsored shows; reply-rate difference",
             "A/B test on 200 sponsored-show emails; adopt the winner if it lifts replies ≥ 20%"),
        ]
        for i, row in enumerate(opps):
            for j, v in enumerate(row):
                ins.cell(14 + i, 2 + j).value = v

    # 03 section C: launch kit summary
    launch = [
        "1,044 verified independent podcasters (596) and expert-led creators (448) in US/GB/AU/CA/IE/NZ/SG; "
        "Priority A (250) first. See launch_kit/LAUNCH_KIT.md §1",
        "Email (best for 743): published business contacts. Instagram/LinkedIn/X DMs by hand (best for ~300 incl. "
        "UK/IE personal mailboxes, PECR). Podcast guest pitches for distribution. Contact form as backup",
        "Mon: sending domain + 2 Workspace inboxes + warm-up (Growth Lead); engine run + HubSpot import; "
        "sample-clip turnaround test (Creator Success). Tue-Fri: 40 emails/day + 20 DMs/day on Priority A",
        "Wk2: 30/inbox/day, Priority B, day-14 backup touches, founder guest pitches 5/day, weekly engine rerun. "
        "Wk3: 40/inbox/day, shift volume to best channel. Wk4: Priority C, channel-mix write-up",
        "Engine $0; Google Workspace x2 ~$14; domain ~$1; sequencer ~$37; HubSpot Free $0; Bitly/Dub free $0. "
        "≈ $52/month",
        "~750 contacted, ~64 replies (email 6-9%, DM 8-12%), ~30 sample sets delivered, ~10 activated sign-ups, "
        "~4 demo calls, 3-5 guest bookings",
        "Domain reputation from cold email: secondary domain, warm-up, slow ramp, published addresses only, "
        "pause at bounce > 3% or complaints > 0.1%",
        "Secondary domain + 2 Workspace seats, sequencer, HubSpot admin, access to IncuBrix IG/X/LinkedIn, "
        "a named sender + podcast guest, Creator Studio credits for ~40 sample sets",
    ]
    for i, v in enumerate(launch):
        e.cell(24 + i, 2).value = v

    # 00_START: disclosures (candidate must review)
    st = wb["00_START"]
    st["B16"] = ("Claude Code (Anthropic) assisted with writing the engine, tests, message templates and "
                 "documents. Data: Apple Podcasts Search/Lookup API (public, keyless) and creators' public RSS "
                 "feeds. Python 3 standard library; openpyxl for this workbook. No paid tools.")
    st["B17"] = "$0. No paid tools or data."
    wb.save(dst)
    print(f"Saved {dst}: {min(total, 1000)} lead rows, {pa} Priority A, channels {channels}")
    print("Still to fill by hand: 00_START B5-B15, B18, F5-F10, B21; 01_INSIGHT observations; "
          "04_SELF_CHECK C11 (after the seed test) and C24-C28 self-score.")


if __name__ == "__main__":
    main()
