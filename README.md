# IncuBrix Creator Lead Engine

Finds English-speaking creators who need IncuBrix, verifies each one against public evidence, picks the best and backup outreach channel, drafts personalised multi-channel sequences and exports a CRM-ready file. It reruns weekly without creating duplicates.

**Stack:** Python 3.10+ standard library only. No API keys, no paid services, no installs.

## Run it

```bash
python -m engine run
```

That one command discovers, verifies, dedupes, scores, picks channels, drafts messages and exports. Run it again at any time to refresh. Known feeds are re-checked, new creators are added, and existing creators keep their `lead_id`.

| Task | Command |
|---|---|
| Full run / weekly refresh | `python -m engine run` |
| Process a new list you are given (fast) | `python -m engine run --seed new_input.txt --only-seed` |
| Add a list to the full database | `python -m engine run --seed new_input.txt` |
| Re-verify known creators, no new searches | `python -m engine run --no-discover` |
| Force every feed to be re-fetched | `python -m engine run --no-discover --refetch` |
| Failure demo: crash after 50 feeds | `python -m engine run --no-discover --refetch --simulate-failure 50` |
| Show last run report | `python -m engine report` |
| Tests (offline, ~1 s) | `python -m unittest discover -s tests -v` |
| Fill the submission workbook | `pip install openpyxl` then `python scripts/fill_workbook.py <workbook.xlsx>` |

A **seed file** is `.txt` (one entry per line) or `.csv` (column `url` or `name`). Each entry can be an Apple Podcasts URL (`https://podcasts.apple.com/.../id123456`), an RSS feed URL, or a show/creator name. Entries that can't be resolved are listed in `output/errors.csv`, and each seed entry's verdict is printed at the end of the run.

**Recovery:** state is saved to `data/state.sqlite` as the run goes (commits every 100 feeds). If a run crashes, is interrupted or loses the network, run the same command again. Finished work is reused from the cache and only the rest is fetched. A feed that fails is logged to `output/errors.csv`, marked `error` and retried on the next run. One bad feed never stops a run.

## What it produces

| File | What it is |
|---|---|
| `output/leads.csv` | **Official lead list.** UTF-8, exactly the 30 workbook columns, Qualified creators only, sorted by `lead_id`. |
| `output/leads_evidence.csv` | Audit trail per lead: country basis, name basis, channel basis, backup handle, socials found, feed URL, latest and previous episode. |
| `output/crm_import_hubspot.csv` | CRM import (HubSpot column names; works for any CSV-import CRM). |
| `outreach/sequences/*.md` | Sequence playbook per segment × channel (Email, LinkedIn, Instagram, X, TikTok, podcast guest pitch, contact form). |
| `outreach/priority_a/*.md` | One file per Priority A lead: evidence summary plus first message, 2 follow-ups and a backup-channel touch. |
| `outreach/all_messages.csv` | Every drafted message for every qualified lead (channel, step, send day, recipient, subject, body). Can be loaded into a sequencer. |
| `output/rejected_and_reserve.csv` | Every creator that was checked and not exported, with the reason. |
| `output/run_report.json`, `output/runs.csv` | Run metrics: input size, produced, rejected, duplicates removed, errors, runtime, cost. |
| `output/errors.csv`, `output/logs/` | Error log and full run logs. |

## How a creator is found and verified

1. **Find.** The Apple Podcasts Search API (public, keyless, rate-limited to ~20 calls/min, so the engine waits 3.1 s between calls) is searched for ~165 creator-niche and location terms across the US, GB, CA, AU, IE, NZ and SG stores. Apple's public top-podcast charts are also pulled for 18 genres in each of those 7 countries. These are the richest public source of non-US independent shows. Results are cached (searches 7 days, charts 1 day). Shows with no episode in 60 days, or in news, kids or religious genres, are dropped before any feed is fetched.
2. **Read the feed.** Each show's public RSS feed is streamed and parsing stops after the newest 30 episodes, so even huge feeds cost one small request. 24 parallel workers, polite per-host spacing, 3 retries with backoff, a 6 MB cap.
3. **Check every rule in the brief.** A lead is `Qualified` only if every check passes:

| Brief check | How the engine proves it | Evidence column |
|---|---|---|
| Real and relevant | An individual person is named (author field, `podcast:person`, or "hosted by …"). Networks, media companies, publications, LLC/Inc publishers, universities, churches and similar are rejected. Stable ID = Apple Podcasts collection ID. | `profile_url`, `stable_creator_id` |
| Active | Counted from episode dates: ≥8 items in 30 days **or** ≥2 long-form (≥20 min) in 60 days. | `content_count_30d`, `longform_count_60d`, `recent_content_url` |
| Commercial | Offer phrases only, quoted from show notes: sponsor reads and promo codes, Patreon/Supercast/listener-subscription links, the creator's *own* course/book/programme/merch, coaching/consulting offers with a booking or "work with me" call, and affiliate links. Topic words alone don't count; "coaching" in a guest's bio is not an offer. | `monetization_signal` + episode URL |
| Needs IncuBrix | Checked against what IncuBrix sells: no transcripts on recent episodes (captions), long episodes with no clip channel linked (repurposing), video episodes (clipping), publishing gaps (consistency), or stated needs ("hiring an editor"). | `incubrix_need` + feed URL |
| Reachable | The address or handle must visibly belong to the creator or show: it has to contain their name, the show's name or its initials. A producer's, employer's, network's or sponsor's inbox or handle is dropped, and so is an agency address. LinkedIn handles must contain the creator's name. The email must appear **verbatim** in the creator's own feed or show notes. A business-context address ("for enquiries email …") is preferred over the `itunes:owner` contact. Social handles count only if the creator links them repeatedly, so a guest's handle isn't picked up by mistake. Placeholder/host addresses (`@anchor.fm` etc.) are refused. Nothing is guessed. | `channel_handle_or_url`, `channel_evidence_url` |
| Country | Only creator-published signals: `podcast:location`, the creator's own domain/email TLD, the feed language region (`en-gb`…), first-person location statements ("based in Leeds"), and the time zone written in episode timestamps. `en-us` alone is not trusted because it is a hosting default, so it needs a North American time zone or a US place name to back it up. If the feed has no usable signal and the creator passes every other check, the engine fetches their own website homepage once. It looks for a postal address (`TX 78701`, `NSW 2000`, a UK postcode, a Canadian postal code), a company registration ("Registered in England and Wales"), an ABN or an international phone prefix. The matched snippet and URL are recorded. Conflicting or missing signals mean rejection. The Apple store or chart a show appears in is never used. | `country_iso2` (basis + `country_evidence_url` in `leads_evidence.csv`) |
| English | Feed language `en*`, or mainly-ASCII titles if no language is set. | `primary_language` |
| Complete and unique | Dedupe happens at three levels: the same show from many searches (Apple ID), the same feed URL, and the same person behind several shows (shared email, social or name). The best-scoring show is kept. `completeness_check` uses the workbook formula's field list. | `duplicate_check`, `completeness_check` |

4. **Balance.** No country may exceed 55% (the brief's limit is 60%). The lowest-scoring surplus goes to reserve (`rejected_and_reserve.csv`) and is re-tested every run.
5. **Score and prioritise.** 0–100: activity (20) + commercial signals (25) + need signals (25) + contact quality (15) + owned socials (10) + video (5). Priority A = the top 250 with a DM-able or email channel and two recent episodes to reference. B = the next 40%. C = the rest.
6. **Pick channels.** Email is the default when a published business email exists. UK/IE creators on a personal mailbox (Gmail etc.) count as "individual subscribers" under PECR, so their first touch goes to a social channel they actively link instead. The backup is the creator's most-linked social, then their website contact form, then a podcast guest pitch.
7. **Draft.** Every message names a specific recent episode by title, states one need backed by that lead's evidence, says who is sending and from which company (legal name and address), carries a UTM link tagged with the lead ID and step, and includes an opt-out. DMs fit platform length limits and are marked **manual send only**.

## Configuration (`config.json`)

- `sender.*`: who signs every message. It is currently set for the assessment as *Gowtham M P, Growth Engineer candidate for IncuBrix*, because the brief forbids presenting the candidate as an IncuBrix employee. At launch, IncuBrix sets `name`, `role` (e.g. "Creator Partnerships"), `affiliation` (e.g. "at IncuBrix"), `intro` and `guest_name`, then reruns. No code changes are needed.
- `apple.terms` / `apple.local_terms`: search terms. Add niches here to grow the list.
- `qualify.*`: activity and freshness thresholds from the brief.
- `countries.max_share`, `priority.a_count`, `priority.b_share`.
- `run.workers`, `run.feed_ttl_hours` (how long a fetched feed counts as fresh).

## Runtime and cost

All of these were measured on a laptop over home broadband and are logged in `output/runs.csv` and `demo/*.log`. The direct cost is **$0**: public APIs only, no paid tools.

| Run | Input | Result | Runtime |
|---|---|---|---|
| Normal run (warm caches) | 154,699 search/chart hits → 20,000+ unique shows | 1,060 qualified, 0 duplicates | 7.7 min |
| Repeat run, same input | same | identical 1,060, same lead_ids, 0 new duplicates | 7.6 min |
| Refresh on new input (`demo/new_input.txt`) | 55 shows never seen before | 10 new qualified (L02258–L02267); country cap re-balanced | 0.24 min |
| Failure (`--simulate-failure 5`) + recovery | 24 new shows (`demo/new_input_2.txt`) | crash after 5 feeds; rerun reused those 5 and fetched only 19; 3 new qualified | 0.05 + 0.15 min |
| First-ever run (cold caches) | ~236 search terms × 7 stores + 126 charts | ~20,000 feeds and ~1,000 creator websites fetched | ~2–2.5 h, measured across three discovery passes (bounded by Apple's ~20 calls/min) |

Scale: about 5% of discovered shows pass every check, so 5,000 verified creators needs ~100,000 discovered shows. That is more search terms and chart genres in `config.json`, and nothing else in the code changes. Cost stays $0, and runtime grows linearly with the number of Apple API calls.

**Stable IDs on any machine:** `lead_ids.csv` (committed) maps every `stable_creator_id` to its `lead_id`. A fresh clone with no `data/` folder reuses these IDs, so a rerun on IncuBrix's machine produces the same IDs as the submitted `leads.csv`. New creators continue the numbering.

## Data, privacy and platform rules

- Sources: the Apple Podcasts Search/Lookup API and public RSS feeds that creators publish for syndication. No logins, no scraping of sites that forbid it, no bought or leaked data. Only business contact details the creator published themselves are stored.
- The engine **never sends anything.** Sending is a separate, human-controlled step (see the launch kit). DMs are drafted for manual sending only. LinkedIn, Instagram and X forbid automated DMs.
- Every email carries the sender's identity, IncuBrix's postal address and an opt-out (CAN-SPAM, GDPR/PECR, Australia's Spam Act). Honour opt-outs on every channel.

## Known limits (stated honestly)

- Podcast platforms don't publish follower counts, so `followers_or_subscribers` is blank rather than estimated.
- "Active in the last 60 days" for an email channel is shown by the feed that publishes it having a new episode within 60 days. For a social channel, it's shown by an episode within 60 days linking that handle.
- Country inference is conservative. A North American time zone with no Canadian signal is labelled US, so a Canadian creator who never mentions Canada could be mislabelled. The basis for every label is in `leads_evidence.csv` for audit.
- YouTube-first creators need a YouTube Data API key and aren't part of this keyless build. Their sequences are ready in `outreach/sequences/youtubers.md`.
- Spot-check precision: the last random 20-lead samples (seeds 314, 555, 8080, 31337 in my own audit script) passed about 17–18/20 against the brief's checks. The remaining misses were mainly creator *names* that are a channel brand ("Third Eye Insights") rather than a person's name, on otherwise genuine independent creators. Every other class of error found during review is fixed and covered by a test.

## Layout

```
engine/        net.py (HTTP, retries, cache) · feed.py (streaming RSS) · sources.py (Apple search, charts, seed files)
               signals.py (evidence extraction) · qualify.py (rules, channel choice, score)
               messages.py (sequences) · pipeline.py (orchestration, website country check) · export.py · store.py
tests/         28 offline unit + end-to-end tests (fixture feed; includes every audit regression found)
scripts/       fill_workbook.py · lead_stats.py · build_seed_test.py · make_demo_seed.py
demo/          the new-input seed files and logs of the normal / repeat / refresh / failure-recovery runs
seed_test/     seed-test procedure, messages and reply log
launch_kit/    LAUNCH_KIT.md (30-day plan)
docs/          PRODUCT_INSIGHT_GUIDE.md
lead_ids.csv   stable ID registry (keeps lead_ids identical on any machine)
config.json    all tunables
```

`data/` (SQLite state + HTTP cache, ~1.5 GB after a full run) is rebuilt automatically and is not committed.
