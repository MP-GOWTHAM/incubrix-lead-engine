"""Build the seed-test pack: real drafted sequences re-addressed to test accounts YOU own.

    python scripts/build_seed_test.py

Reads seed_test/test_accounts.json (fill in your own accounts first), takes the top Priority A
leads, renders each channel's 3-step sequence with the engine's own message code, and writes
seed_test/seed_messages.md, seed_messages.csv and an empty reply_log.csv. Nothing is sent:
you schedule and send these yourself, to yourself.
"""

import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from engine import messages  # noqa: E402
from engine.store import Store  # noqa: E402

SEED = os.path.join(ROOT, "seed_test")
LOG_COLS = ["test_id", "channel", "from_account", "to_test_account", "lead_id", "step", "scheduled_for",
            "sent_at", "link_clicked_at", "reply_received_at", "reply_text", "logged_in_crm_at", "evidence_file"]


def main():
    with open(os.path.join(SEED, "test_accounts.json"), encoding="utf-8") as f:
        accounts = json.load(f)
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8-sig") as f:
        cfg = json.load(f)
    store = Store(os.path.join(ROOT, "data", "state.sqlite"))
    pa = sorted((l for l in store.leads() if l["status"] == "Qualified" and l.get("priority") == "A"),
                key=lambda l: -l["lead_score"])
    rows, md = [], ["# Seed test messages", "",
                    "Real drafted sequences for real Priority A leads, re-addressed to test accounts the candidate "
                    "owns. Links are tagged `utm_campaign=seed_test` so clicks never mix with launch data.", ""]
    n = 0
    for i, (ch, acc) in enumerate(accounts.items()):
        lead = next((l for l in pa if l["best_channel"] == ch), pa[i % len(pa)])
        md += [f"## {ch}: `{acc['from']}` → `{acc['to']}`",
               f"Wording generated for {lead['lead_id']} ({lead['show_name']}).", ""]
        for step, (subj, body) in enumerate(messages.steps_for(lead, cfg, ch), 1):
            n += 1
            body = re.sub(r"utm_campaign=[^&\s]+", "utm_campaign=seed_test", body)
            tid = f"S{n:02d}"
            rows.append({"test_id": tid, "channel": ch, "from_account": acc["from"], "to_test_account": acc["to"],
                         "lead_id": lead["lead_id"], "step": step, "send_day": messages.SEND_DAYS[step - 1],
                         "subject": subj or "", "body": body})
            md += [f"### {tid} · step {step} · send day {messages.SEND_DAYS[step - 1]}",
                   f"**Subject:** {subj}" if subj else "", "", "```text", body, "```", ""]
    with open(os.path.join(SEED, "seed_messages.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(SEED, "seed_messages.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    log = os.path.join(SEED, "reply_log.csv")
    if not os.path.exists(log):
        with open(log, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=LOG_COLS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in ("test_id", "channel", "lead_id", "step")} |
                           {"from_account": r["from_account"], "to_test_account": r["to_test_account"]})
    print(f"Wrote {len(rows)} seed messages across {len(accounts)} channels to seed_test/")


if __name__ == "__main__":
    main()
