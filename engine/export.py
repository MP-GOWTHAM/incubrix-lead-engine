"""Writes leads.csv (official workbook columns), evidence/CRM/outreach files and the run report."""

import csv
import json
import os
import re
import time
from collections import Counter

LEAD_COLUMNS = [
    "lead_id", "creator_name", "creator_segment", "country_iso2", "primary_language", "primary_platform",
    "profile_url", "stable_creator_id", "followers_or_subscribers", "last_content_date", "recent_content_url",
    "content_count_30d", "longform_count_60d", "monetization_signal", "monetization_evidence_url",
    "incubrix_need", "need_evidence_url", "best_channel", "channel_handle_or_url", "channel_evidence_url",
    "backup_channel", "personalization_hook", "first_message", "checked_date", "priority", "lead_score",
    "candidate_status", "rejection_reason", "duplicate_check", "completeness_check",
]
# Same fields the workbook's completeness formula requires (column AD)
REQUIRED = ["creator_name", "creator_segment", "country_iso2", "primary_language", "primary_platform",
            "profile_url", "stable_creator_id", "last_content_date", "recent_content_url", "monetization_signal",
            "monetization_evidence_url", "incubrix_need", "need_evidence_url", "best_channel",
            "channel_handle_or_url", "channel_evidence_url", "personalization_hook", "first_message",
            "checked_date", "priority"]
EVIDENCE_COLUMNS = ["lead_id", "stable_creator_id", "show_name", "creator_name", "name_basis", "country_iso2",
                    "country_basis", "country_evidence_url", "genre", "feed_url", "website", "recent_title", "recent_date", "second_title",
                    "second_date", "channel_basis", "backup_channel", "backup_handle_or_url", "backup_evidence_url",
                    "backup_basis", "socials", "monetization_types", "need_types", "avg_minutes", "is_video"]


def completeness(row):
    return "COMPLETE" if all(str(row.get(f, "")).strip() for f in REQUIRED) else "MISSING FIELDS"


def lead_row(l):
    row = {c: l.get(c, "") for c in LEAD_COLUMNS}
    row["candidate_status"] = "Qualified"
    row["rejection_reason"] = ""
    row["duplicate_check"] = "UNIQUE"
    row["completeness_check"] = completeness(row)
    return row


def _write_csv(path, cols, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:50]


def write_all(leads, stats, errors, runtime, cfg, paths, now, seed_keys=()):
    out, outreach = paths["output"], paths["outreach"]
    os.makedirs(out, exist_ok=True)
    os.makedirs(os.path.join(outreach, "priority_a"), exist_ok=True)

    qualified = sorted((l for l in leads if l["status"] == "Qualified"), key=lambda l: l["lead_id"])
    rows = [lead_row(l) for l in qualified]
    ids = Counter(r["stable_creator_id"] for r in rows)
    for r in rows:
        if ids[r["stable_creator_id"]] > 1:  # belt and braces: should be impossible after dedupe
            r["duplicate_check"] = "DUPLICATE"
    _write_csv(os.path.join(out, "leads.csv"), LEAD_COLUMNS, rows)

    ev = []
    for l in qualified:
        e = {c: l.get(c, "") for c in EVIDENCE_COLUMNS}
        e["socials"] = "; ".join(f"{k}: {v['url']}" for k, v in (l.get("socials") or {}).items())
        e["monetization_types"] = "; ".join(l.get("monetization_types") or [])
        e["need_types"] = "; ".join(l.get("need_types") or [])
        ev.append(e)
    _write_csv(os.path.join(out, "leads_evidence.csv"), EVIDENCE_COLUMNS, ev)

    rej = [l for l in leads if l["status"] in ("Rejected", "Reserve")]
    _write_csv(os.path.join(out, "rejected_and_reserve.csv"),
               ["stable_creator_id", "show_name", "creator_name", "country_iso2", "candidate_status",
                "rejection_reason", "profile_url"],
               [{"stable_creator_id": l["key"], "show_name": l.get("show_name", ""),
                 "creator_name": l.get("creator_name", ""), "country_iso2": l.get("country_iso2", ""),
                 "candidate_status": l["status"], "rejection_reason": l.get("rejection_reason", ""),
                 "profile_url": l.get("profile_url", "")} for l in sorted(rej, key=lambda l: l["key"])])

    _write_crm(out, qualified)
    _write_outreach(outreach, qualified)
    write_templates(cfg, outreach)
    _write_csv(os.path.join(out, "errors.csv"), ["time", "stage", "item", "error"], errors)

    countries = Counter(l["country_iso2"] for l in qualified)
    total = len(qualified)
    seed_set = set(seed_keys)
    report = {
        "run_at": now.isoformat(timespec="seconds"),
        "runtime_min": round(runtime / 60, 2),
        "direct_cost_usd": 0.0,
        "input_size": stats.get("input_size", 0),
        "searches": stats.get("searches", 0),
        "searches_from_cache": stats.get("searches_cached", 0),
        "new_candidates": stats.get("new_candidates", 0),
        "duplicates_removed": stats.get("duplicates_removed", 0) + stats.get("creator_duplicates_removed", 0),
        "feeds_fetched": stats.get("feeds_fetched", 0),
        "feeds_from_cache": stats.get("feeds_cached", 0),
        "feed_errors": stats.get("feed_errors", 0),
        "evaluated": len(leads),
        "qualified": total,
        "rejected": sum(1 for l in leads if l["status"] == "Rejected"),
        "reserve_country_cap": sum(1 for l in leads if l["status"] == "Reserve"),
        "priority": dict(Counter(l["priority"] for l in qualified)),
        "segments": dict(Counter(l["creator_segment"] for l in qualified)),
        "countries": dict(countries),
        "country_max_share": round(max(countries.values()) / total, 3) if total else 0,
        "best_channels": dict(Counter(l["best_channel"] for l in qualified)),
        "backup_channels": dict(Counter(l["backup_channel"] or "(none)" for l in qualified)),
        "top_rejection_reasons": dict(Counter(r.split(" (")[0] for l in rej
                                              for r in l.get("rejection_reason", "").split("; ") if r)
                                      .most_common(12)),
        "duplicates_in_export": sum(1 for r in rows if r["duplicate_check"] == "DUPLICATE"),
        "incomplete_in_export": sum(1 for r in rows if r["completeness_check"] != "COMPLETE"),
    }
    if seed_set:
        sl = [l for l in leads if l["key"] in seed_set]
        report["seed_results"] = [{"stable_creator_id": l["key"], "show": l.get("show_name", ""),
                                   "status": l["status"], "lead_id": l.get("lead_id") or "",
                                   "reason": l.get("rejection_reason", "")} for l in sl]
    with open(os.path.join(out, "run_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    runs = os.path.join(out, "runs.csv")
    new = not os.path.exists(runs)
    with open(runs, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["run_at", "mode", "input_size", "qualified", "rejected", "duplicates_removed",
                        "feed_errors", "runtime_min", "direct_cost_usd"])
        w.writerow([report["run_at"], stats.get("mode", ""), report["input_size"], total, report["rejected"],
                    report["duplicates_removed"], report["feed_errors"], report["runtime_min"], 0.0])
    return report


def record_failure(paths, stats, errors, message):
    """A crashed run still leaves a trace in runs.csv and errors.csv, so recovery can be shown."""
    from datetime import datetime, timezone
    out = paths["output"]
    os.makedirs(out, exist_ok=True)
    errors = list(errors) + [{"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "stage": "run", "item": "-", "error": message}]
    _write_csv(os.path.join(out, "errors.csv"), ["time", "stage", "item", "error"], errors)
    runs = os.path.join(out, "runs.csv")
    new = not os.path.exists(runs)
    with open(runs, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["run_at", "mode", "input_size", "qualified", "rejected", "duplicates_removed",
                        "feed_errors", "runtime_min", "direct_cost_usd"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), "failure", stats.get("input_size", 0),
                    "", "", stats.get("duplicates_removed", 0), stats.get("feed_errors", 0),
                    round((time.time() - stats["t0"]) / 60, 2) if stats.get("t0") else "", 0.0])


def _write_crm(out, qualified):
    """HubSpot-style import: one contact per creator, owner fields left for IncuBrix to assign."""
    cols = ["Lead ID", "First Name", "Full Name", "Show / Brand", "Email", "Website", "Country", "Segment",
            "Lead Source", "Lifecycle Stage", "Lead Status", "Priority", "Lead Score", "Best Channel",
            "Best Channel Handle", "Backup Channel", "Backup Handle", "Profile URL", "Latest Episode",
            "Latest Episode Date", "Need Summary", "Monetisation Summary", "Checked Date"]
    rows = [{
        "Lead ID": l["lead_id"], "First Name": l.get("first_name", ""), "Full Name": l["creator_name"],
        "Show / Brand": l["show_name"], "Email": l.get("email", ""), "Website": l.get("website", ""),
        "Country": l["country_iso2"], "Segment": l["creator_segment"], "Lead Source": "IncuBrix lead engine",
        "Lifecycle Stage": "lead", "Lead Status": "NEW", "Priority": l["priority"], "Lead Score": l["lead_score"],
        "Best Channel": l["best_channel"], "Best Channel Handle": l["channel_handle_or_url"],
        "Backup Channel": l.get("backup_channel", ""), "Backup Handle": l.get("backup_handle_or_url", ""),
        "Profile URL": l["profile_url"], "Latest Episode": l.get("recent_title", ""),
        "Latest Episode Date": l.get("recent_date", ""), "Need Summary": l["incubrix_need"],
        "Monetisation Summary": l["monetization_signal"], "Checked Date": l["checked_date"],
    } for l in qualified]
    _write_csv(os.path.join(out, "crm_import_hubspot.csv"), cols, rows)


TEMPLATE_CHANNELS = {
    "Podcaster/Video Podcaster": ["Email", "Instagram", "X", "LinkedIn", "Podcast guest pitch", "Contact form"],
    "YouTuber/Video-First Creator": ["Email", "Instagram", "X", "TikTok", "LinkedIn", "Contact form"],
    "Expert-Led Creator": ["Email", "LinkedIn", "Instagram", "X", "Podcast guest pitch", "Contact form"],
}


def write_templates(cfg, outreach):
    """Segment playbooks rendered by the same code that writes live messages, so they never drift."""
    from . import messages
    d = os.path.join(outreach, "sequences")
    os.makedirs(d, exist_ok=True)
    for seg, chans in TEMPLATE_CHANNELS.items():
        lead = {"key": "{lead_id}", "lead_id": "{lead_id}", "first_name": "{first_name}", "show_name": "{show_name}",
                "creator_segment": seg, "recent_title": "{latest_episode_title}", "recent_date": "",
                "second_title": "{previous_episode_title}", "need_types": ["Repurposing into clips"],
                "avg_minutes": "{avg_minutes}", "socials": {}, "incubrix_need": ""}
        lines = [f"# Outreach sequence: {seg}", "",
                 "Placeholders in `{braces}` are filled per lead by the engine from verified feed data. "
                 "The engine writes the filled versions to `outreach/all_messages.csv` and "
                 "`outreach/priority_a/`.", "",
                 "**Cadence:** step 1 day 0 → step 2 day 4 → step 3 day 10 on the best channel, then one touch "
                 "on the backup channel on day 14. Stop the moment the creator replies or opts out.", "",
                 "**Need line variants** (the engine picks the one backed by that lead's evidence):", ""]
        for nt in ("Stated workflow need", "Video clipping", "Repurposing into clips", "Publishing consistency",
                   "Captions/transcripts"):
            v = dict(lead, need_types=[nt], incubrix_need='Stated workflow need: episode notes say "{quote}"')
            lines.append(f"- *{nt}:* {messages.need_line(v)}")
        lines.append("")
        for ch in chans:
            steps = messages.steps_for(lead, cfg, ch)
            rule = CHANNEL_RULES.get(ch, "")
            lines += [f"## {ch}", "", f"_{rule}_", ""]
            for i, (subj, body) in enumerate(steps, 1):
                lines.append(f"### Step {i} · day {messages.SEND_DAYS[i - 1]}")
                if subj:
                    lines.append(f"**Subject:** {subj}")
                lines += ["", "```text", body, "```", ""]
        name = {"Podcaster/Video Podcaster": "podcasters", "YouTuber/Video-First Creator": "youtubers",
                "Expert-Led Creator": "expert_led"}[seg]
        with open(os.path.join(d, f"{name}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


CHANNEL_RULES = {
    "Email": "Send from a warmed IncuBrix Google Workspace inbox through a sequencer with per-recipient sends, "
             "unsubscribe handling and the physical address (CAN-SPAM). Max 40/day per inbox in week 1.",
    "LinkedIn": "Manual only: connection request with the note (300-char limit), then steps 2-3 as messages "
                "after they accept. No automation tools (LinkedIn User Agreement §8.2). Max 15 requests/day.",
    "Instagram": "Manual DM from the IncuBrix business account. No bulk or automated DMs (Meta Platform Terms). "
                 "Max 20 new DMs/day; follow and engage with one post first.",
    "X": "Manual DM only where their DMs are open; otherwise a public reply to their latest post that mentions "
         "the episode. No automated DMs (X Automation Rules). Max 20/day.",
    "TikTok": "Manual DM only if they accept messages; otherwise comment on their latest post. Max 15/day.",
    "Podcast guest pitch": "Email to the published show contact, from the person who would be the guest. "
                           "Max 10/day; pitches need a real, available guest.",
    "Contact form": "Submit by hand on the creator's website. Never automate form submissions. Max 15/day.",
}


def _write_outreach(outreach, qualified):
    msg_rows = []
    for l in qualified:
        for m in l.get("sequence") or []:
            msg_rows.append({"lead_id": l["lead_id"], "priority": l["priority"], "creator_name": l["creator_name"],
                             "show_name": l["show_name"], "segment": l["creator_segment"], **m})
    _write_csv(os.path.join(outreach, "all_messages.csv"),
               ["lead_id", "priority", "creator_name", "show_name", "segment", "channel", "step", "send_day",
                "to", "subject", "body"], msg_rows)
    pa = os.path.join(outreach, "priority_a")
    keep = set()
    for l in qualified:
        if l["priority"] != "A":
            continue
        name = f"{l['lead_id']}_{_slug(l['show_name'])}.md"
        keep.add(name)
        lines = [f"# {l['lead_id']} · {l['creator_name']} · {l['show_name']}", "",
                 f"- **Segment:** {l['creator_segment']} · **Country:** {l['country_iso2']} · "
                 f"**Score:** {l['lead_score']}",
                 f"- **Profile:** {l['profile_url']}",
                 f"- **Best channel:** {l['best_channel']} → `{l['channel_handle_or_url']}` "
                 f"(evidence: {l['channel_evidence_url']})",
                 f"- **Backup channel:** {l.get('backup_channel') or '—'} → `{l.get('backup_handle_or_url', '')}`",
                 f"- **Hook:** {l['personalization_hook']}",
                 f"- **Why IncuBrix:** {l['incubrix_need']}",
                 f"- **Commercial signal:** {l['monetization_signal']} ({l['monetization_evidence_url']})",
                 f"- **Checked:** {l['checked_date']}", ""]
        for m in l["sequence"]:
            lines.append(f"## Step {m['step']} · {m['channel']} · day {m['send_day']}")
            if m["subject"]:
                lines.append(f"**Subject:** {m['subject']}")
            lines += ["", "```text", m["body"], "```", ""]
        with open(os.path.join(pa, name), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    for old in os.listdir(pa):  # leads that dropped out of Priority A lose their file
        if old.endswith(".md") and old not in keep:
            os.remove(os.path.join(pa, old))
