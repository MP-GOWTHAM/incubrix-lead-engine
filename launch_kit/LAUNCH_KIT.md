# IncuBrix Creator Outreach: 30-Day Launch Kit

**Starts:** the first Monday after approval · **Owner:** Growth Lead · **Budget:** about $75 in month 1 · **Inputs:** `output/leads.csv`, `outreach/`, `output/crm_import_hubspot.csv`

## 0. The plan in one paragraph

Start with the 1,048 verified creators in `leads.csv`: independent podcasters and expert-led creators (coaches, consultants, educators) in seven English-speaking markets. They publish long episodes regularly (median 40 minutes, about 4 in the last 30 days), every one already makes money from their show, and most leave reach on the table: 73% publish no transcripts, and 86% have long episodes with no clip channel linked. That is exactly the gap Creator Studio fills. Every first message offers **three free, ready-to-post clips from their latest episode**, so the creator sees the product working on their own content before being asked to sign up. Email does the volume. Instagram, X and LinkedIn DMs (sent by hand) cover the creators who live there and every UK/IE personal mailbox. Podcast guest pitches turn the best podcasters into distribution. The engine is rerun every Monday to add fresh creators and re-verify old ones.

## 1. Who we target first

| Group | Creators | Why first |
|---|---|---|
| **Podcasters / video podcasters** | 598 | Long episodes (median 40 min) are the raw material for clips. 45% already carry sponsor reads, so more reach is directly worth money to them. |
| **Expert-led creators** (coaches, consultants, educators who podcast) | 450 | They sell coaching, courses or services (33% have a booking or "work with me" offer), so content that finds clients pays for itself. This matches IncuBrix's "Coaches / Thought Leaders" positioning. |

| Country | US | GB | AU | CA | IE | NZ | SG |
|---|---|---|---|---|---|---|---|
| Creators | 576 (55%) | 205 | 146 | 76 | 22 | 22 | 1 |

All 1,048 pass every check in the brief, each with a public evidence URL. Rejected candidates are listed with their reasons in `output/rejected_and_reserve.csv`. A further 70+ US creators who qualify are held in reserve by the country cap. They can be released as non-US volume grows.

**Sequence order:** Priority A first (the top 250 by score, each with a full hand-checkable sequence in `outreach/priority_a/`), then B, then C. Within each priority, the newest episode goes first, so the hook is always fresh.

## 2. Channels and why

| Channel | Used for | Why | Safe daily volume (per sender) |
|---|---|---|---|
| **Email** (best channel for 743 leads, 71%) | First touch plus 2 follow-ups | Every address is published by the creator in their own feed or show notes. Email is where podcasters receive sponsor and guest enquiries. | Week 1: 20 · Week 2: 30 · Weeks 3–4: 40 per inbox (2 inboxes) |
| **Instagram DM** (best for 226; backup for ~280) | First touch where no business email exists, or for UK/IE personal mailboxes; backup touch on day 14 | Each handle is one the creator links from their own episode notes within the last 60 days | 20 new DMs/day, manual |
| **X DM / reply** | Backup touch | Cheap, fast replies from tech, business and comedy podcasters | 20/day, manual |
| **LinkedIn** | Backup for expert-led creators (coaches, consultants) | Their buyers, and their attention, are on LinkedIn | 15 connection requests/day (~80/week), manual |
| **Podcast guest pitch** | Top 30 podcasters by score, from week 2 | One episode about repurposing reaches every listener who is a creator. This is a distribution win, not a single sale. | 5–10/day from the founder's inbox |
| **Contact form** | Backup where no social is linked | The creator's own site | 15/day, manual |

**Compliance built in:** every message names the sender, IncuBrix Pte. Ltd. and its address, and includes an opt-out. Emails go to business contacts the creator published themselves (CAN-SPAM, plus GDPR legitimate interest for UK/IE business addresses). UK/IE personal mailboxes get a DM instead of email (PECR). DMs are never automated (LinkedIn, Meta and X terms). An opt-out on any channel stops all channels for that creator.

## 3. Week 1: setup and first sends

| Day | Action | Owner | Tool | Volume / output |
|---|---|---|---|---|
| Mon | Buy a secondary sending domain (e.g. `getincubrix.com`). Set up 2 Google Workspace inboxes with SPF, DKIM and DMARC. Start warm-up. | Growth Lead | Google Workspace, domain registrar | 2 inboxes live |
| Mon | Replace the assessment sender in `config.json` with the real IncuBrix sender (`name`, `role`, `affiliation`, `intro`, `guest_name`). Run `python -m engine run`. Import `output/crm_import_hubspot.csv` into HubSpot Free. | Growth Lead | Engine, HubSpot | Fresh list, every contact in CRM |
| Mon | Create a "Sample clips" workspace in Creator Studio. Time how long 3 clips take for one Priority A lead's latest episode. | Creator Success | IncuBrix | Turnaround measured (target < 15 min) |
| Tue | Load the Priority A email sequences (`outreach/all_messages.csv`, filter `channel=Email`, `priority=A`) into the sequencer, with stop-on-reply on. | Growth Lead | Sequencer (Instantly or similar) | 3-step sequences queued |
| Tue–Fri | Send Priority A emails. | Sequencer | — | 20/inbox/day = 40/day, ~160 in week 1 |
| Tue–Fri | Send Priority A DMs (first-touch Instagram/X leads), by hand, after engaging with one recent post. | Creator Partnerships | Instagram, X | 20/day each |
| Daily | Triage replies within 4 working hours. A "yes" gets 3 sample clips within 24 h. Log the outcome in HubSpot. | Creator Partnerships + Creator Success | HubSpot, IncuBrix | 100% of replies logged |
| Fri | Review: deliverability (bounce < 3%, spam complaints < 0.1%), reply rate by channel, and sample-clip turnaround. | Growth Lead | Sequencer stats, HubSpot | Go/no-go for the week 2 volume step-up |

## 4. Weeks 2–4

- **Week 2:** raise email to 30/inbox/day and start Priority B. Start backup-channel touches (day 14) for week 1 non-responders. The founder sends 5 guest pitches/day to the top 30 podcasters. Rerun the engine Monday (`python -m engine run`) and import new leads.
- **Week 3:** email at 40/inbox/day. Shift volume toward whichever channel or segment had the best positive-reply rate in weeks 1–2 (track it in HubSpot by `Best Channel` and `Segment`). Add 20 search terms in the best-performing niches to `config.json` and rerun.
- **Week 4:** finish Priority B and start C. Write up the channel-mix result: reply rate, sample-clip acceptance and sign-ups per channel. Decide whether to add a third inbox and a YouTube Data API key (to open the YouTube-first segment) for month 2.
- **Every Monday:** rerun the engine. Lead IDs are stable, so the CRM import updates existing contacts instead of duplicating them. Remove anyone marked opted-out before loading sequences.

## 5. Tools and monthly cost

| Tool | Purpose | Cost / month |
|---|---|---|
| Lead engine (this repo) | Find, verify, score, draft, export | $0 |
| Google Workspace × 2 inboxes | Sending | ~$14 |
| Secondary domain | Protects incubrix.com's reputation | ~$1 (≈$12/yr) |
| Sequencer (e.g. Instantly Growth) | Scheduling, stop-on-reply, warm-up | ~$37 |
| HubSpot Free CRM | Contacts, tasks for manual DMs, reply logging | $0 |
| Bitly/Dub free + IncuBrix analytics | Click tracking (UTMs are already in every link) | $0 |
| Creator Studio | Making the free sample clips | Internal |
| **Total** | | **≈ $52/month, plus ~$20 one-off setup buffer** |

Prices are list prices as of October 2026. Check them at purchase. No tool is locked in: any sequencer that imports CSV and supports stop-on-reply will work.

## 6. Targets after 30 days and the reasoning behind them

| Metric | Target | Reasoning |
|---|---|---|
| Creators contacted (first touch, all channels) | **~750** | Email ramp: 2 inboxes × (20×4 + 30×5 + 40×10 days) ≈ 1,260 send slots. Each email lead uses up to 3 sends, so that covers ~450 email first touches. Plus the ~300 DM-first leads (Instagram 226, LinkedIn 66, X 12) at 20/day by hand. |
| Reply rate (any reply), email | **6–9%** | Cold email to creators averages low single digits. These messages reference a specific recent episode and offer free work rather than a meeting, which typically lifts replies 2–3×. Validate on week 1's 160 sends. |
| Reply rate, Instagram/X DM | **8–12%** | DMs to creators who actively link that account. Lower volume, higher intent. |
| Positive replies ("yes, send clips") | **50% of replies** | The ask is low-friction: no call, no card. |
| Replies (all channels) | **~64** | 450 emails × 7.5% ≈ 34, plus 300 DMs × 10% = 30. |
| Sample clips delivered | **~30** | ~32 positive replies × 90% delivered within 24 h. |
| Activated sign-ups (created a project) | **~10** | ~35% of creators who receive clips sign up to edit or publish them. |
| Demo calls / meetings booked | **~4** | ~10% of positive repliers ask for a call (mainly expert-led creators and podcasters with teams). |
| Podcast guest bookings | **3–5** | 30 pitches × 10–15% acceptance, typical for a relevant, specific guest offer. |
| Deliverability | Bounce < 3%, spam complaints < 0.1% | Published addresses plus a warm-up. Pause any inbox that crosses either line. |

These are estimates to be replaced by week 1 data. The Friday review in section 3 recalculates them.

## 7. Risks and how to handle them

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Domain reputation damage from cold email** (biggest risk) | Medium | Secondary domain, warm-up, a slow ramp, published addresses only, plain-text emails with one link, a stop rule at bounce > 3% or complaints > 0.1%. |
| Sample-clip demand outpaces the team | Medium | Cap at 15 sample requests/day per Creator Success person. Beyond that, reply with a self-serve link and a 10-minute walkthrough video. |
| Platform restriction on DM accounts | Low–medium | Manual sends only, under the daily caps, warm the account first, and spread volume across the week. |
| Mislabelled country or segment in a few leads | Low | Every label has its basis in `leads_evidence.csv`. Sender spot-checks Priority A before sending. The engine re-verifies weekly. |
| Opt-out not honoured across channels | Low | One HubSpot property `do_not_contact` is checked before every send on every channel. The engine's next import never re-adds opted-out contacts to sequences. |
| Message fatigue: creators see the same template | Low | Every message cites their own episode and evidence. Rotate subject lines in week 3 based on open and reply data. |

## 8. What IncuBrix must provide

- A secondary sending domain plus 2 Google Workspace seats (about $26 to start).
- A sequencer subscription (about $37/month) and a HubSpot Free account, with admin access for the Growth Lead.
- Access to the IncuBrix Instagram, X and LinkedIn accounts (or named team accounts) for manual DMs.
- A named sender (name and role for `config.json`) and a named guest for podcast pitches.
- A Creator Studio workspace with enough credits to make ~40 sets of sample clips (30 targeted, plus buffer).
- Sign-off on the opt-out and data-retention policy: delete non-responders' data after 12 months.

## 9. Monday checklist

- [ ] Sending domain bought, inboxes created, SPF, DKIM and DMARC passing
- [ ] `config.json` sender fields set → `python -m engine run`
- [ ] HubSpot import done, `do_not_contact` property created
- [ ] Sequencer loaded with Priority A email steps, stop-on-reply on
- [ ] Sample-clip turnaround tested on one lead
- [ ] First 40 emails and 20 DMs sent
