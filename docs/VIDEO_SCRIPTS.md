# Video Scripts

The brief asks for two **unedited** videos. Record each in one take, screen plus voice. These scripts are a run sheet, not lines to read word for word. Say it in your own words: the live review checks that you can explain your own decisions.

---

## Video A: Product walkthrough (≤ 5 minutes)

**Goal:** show you used IncuBrix Creator Studio and connect what you saw to the outreach plan.

**Before recording:** log in to Creator Studio with the access from your invitation email. Have one 30–60 min podcast episode you're allowed to use (your own, or Creative Commons) ready to upload.

| Time | On screen | What to say (in your words) |
|---|---|---|
| 0:00–0:30 | incubrix.com homepage | What IncuBrix is: one recording becomes clips, captions and posts for every platform. Who it's for: podcasters, YouTubers, coaches. |
| 0:30–1:30 | Upload the episode → clips found | Time how long it takes. "Every outreach message offers 3 free clips from the creator's latest episode, so this step is the offer." Comment on clip quality. |
| 1:30–2:15 | Open a clip → captions, style | Caption accuracy and styling. "73% of my 1,048 creators publish no transcripts at all." |
| 2:15–3:00 | Transcript edit: delete a sentence | Does the cut look clean? This is the "fix a flubbed line" claim in follow-up 2. |
| 3:00–3:45 | Publishing screen: connect a platform, schedule | Which platforms connect, any friction. |
| 3:45–4:30 | Anything unavailable (e.g. Content Performance "coming soon") | Say what's missing, with the date. The brief says to record unavailable features rather than work around them. |
| 4:30–5:00 | Recap | Your top observation and the biggest opportunity (from tab 01). |

These 5 moments are also your **5 observations for tab 01**: screenshot each one as you go.

---

## Video B: Technical demo (≤ 8 minutes)

**Goal:** what the brief asks for: one normal run, a refresh on new input, recovery from one simple failure. Plus show that someone else can run it from the README.

### Before recording (2 minutes, off camera)

```bash
python scripts/make_demo_seed.py demo/video_input.txt "dog trainer" "pilates instructor" "business coach uk" "money coach australia" "career coach" "speaker" "nutrition coach" "creative business"
```

```bash
python scripts/make_demo_seed.py demo/video_input_2.txt "therapist" "fitness coach canada" "marketing coach" "photography business"
```

```bash
python scripts/make_demo_seed.py demo/video_input_3.txt "yoga teacher uk" "real estate coach" "parenting coach" "author interviews"
```

These give you three lists of real, recently active shows the engine has never seen, so the runs are genuinely new and take seconds instead of minutes. Open a terminal in the project folder at a readable font size.

### Run sheet

| Time | Do | Say |
|---|---|---|
| 0:00–0:45 | Show `README.md`: "Run it" section and the checks table | "One command, Python standard library only, no keys, no installs, $0." |
| 0:45–1:15 | `python -m unittest discover -s tests -v` | "28 offline tests, including every error I found while auditing my own sample." |
| 1:15–2:30 | **Normal run:** `python -m engine run --seed demo/video_input.txt --only-seed` | While it runs: find → read feed → check every rule → dedupe → score → pick channel → draft → export. When it ends, read 2–3 seed verdicts aloud, one Qualified and one Rejected with its reason. |
| 2:30–3:15 | Open `output/runs.csv` and `demo/run1_normal.log` | "The full-scale run: 154,699 search and chart hits, 20,000+ shows, 1,048 qualified, 7.7 minutes, $0. The repeat run on the same input gave identical IDs and 0 new duplicates." |
| 3:15–4:15 | Trace one new Qualified lead: find its `lead_id` in `output/leads.csv`, open its `channel_evidence_url` and `monetization_evidence_url` in the browser | "Every claim has a public link. Here's the published email and here's the sponsor read I quoted." |
| 4:15–5:15 | **Refresh on new input:** `python -m engine run --seed demo/video_input_2.txt --only-seed` | "New creators get new IDs. Existing ones keep theirs. The country cap re-balances automatically." |
| 5:15–6:30 | **Failure:** `python -m engine run --seed demo/video_input_3.txt --only-seed --simulate-failure 5` → it stops. Show `output/errors.csv`. **Recover:** run the same command without `--simulate-failure` and point at the line "fetching N feeds (5 already fresh in cache)" | "It crashes after 5 feeds. State is saved every 100 feeds and at the crash, and the rerun only fetches what's left. One bad feed never stops a run: it's logged and retried next time." |
| 6:30–7:15 | `outreach/priority_a/` → open one file | "Personalised first message, 2 follow-ups and a backup touch, with sender identity, opt-out and a tracked link." |
| 7:15–8:00 | `launch_kit/LAUNCH_KIT.md` §3 | "What IncuBrix does on Monday." Name one decision you would change, because the live review asks for one. |

### A decision you could name honestly

- The 55% country cap holds back 73 qualified US creators. Shipping 60% would add them, but leave no margin.
- Country inference trusts a North-American time zone as US. A Canadian creator who never mentions Canada could be mislabelled, and I'd add a YouTube/website check to tighten it.
- Creator *names* from Apple's author field are sometimes a brand ("Third Eye Insights"). A first-name dictionary would fix the last of those.

### If something goes wrong on camera

That's fine; the video is meant to be unedited. If the network drops, the run logs the error and the rerun recovers, which is itself a demo of the failure handling.
