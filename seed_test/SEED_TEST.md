# Seed Test: Proving Scheduling, Tracking and Reply Logging on 3 Channels

**Rule from the brief:** outreach goes only to test accounts you own. No real creator is contacted.

**Channels:** Email, Instagram DM, X DM. **Messages:** 9 (3 steps × 3 channels), taken from real Priority A sequences.

## 1. Accounts (about 20 minutes)

| Channel | Sender (yours) | Receiver (yours) | Notes |
|---|---|---|---|
| Email | Gmail inbox A | Gmail inbox B | Two personal Gmail accounts are fine for a test |
| Instagram | IG account A (switch it to a free Business/Creator profile) | IG account B | Instagram allows several accounts per person |
| X | X account A | X account B | Let B accept DMs from anyone, or follow A from B |

LinkedIn is **not** used for the seed test because its terms allow one account per person. It stays in the launch plan as a manual channel.

Enter the handles in `seed_test/test_accounts.json`, then run:

```bash
python scripts/build_seed_test.py
```

This writes `seed_messages.md` (copy-ready), `seed_messages.csv` and a blank `reply_log.csv`.

## 2. Tracking links

1. Create a free short-link account (Bitly or Dub).
2. Shorten each message's `incubrix.com/?utm_…&utm_campaign=seed_test…` link. That gives 9 links, one per test ID (`S01`–`S09`).
3. Swap each long link in the message for its short link. The UTM tags stay inside it, so IncuBrix analytics would also see the visit.

## 3. Scheduling (compressed cadence: day 0 / 4 / 10 become +0 / +30 / +60 minutes)

- **Email:** in Gmail A, compose S01–S03 to inbox B and use **Schedule send** at T, T+30 and T+60 min. A sequencer such as Mailmeteor or GMass also proves stop-on-reply. Either is fine; note which one you used.
- **Instagram and X:** platforms don't allow scheduled or automated DMs, so scheduling is done as **CRM tasks**. Import `output/crm_import_hubspot.csv` into a free HubSpot account. On the chosen lead's record, create tasks "IG S04" at T, "IG S05" at T+30 and so on. Send each DM by hand when its task fires. This is exactly how the launch works.

## 4. Run it

For each message:

1. It arrives at the scheduled time (screenshot the inbox or DM thread with timestamps).
2. Click its short link from the receiving account (screenshot the click count in Bitly/Dub).
3. Reply from the receiving account to step 1 of each channel ("yes, send the clips"). For email, also reply "no thanks" to one message to test the opt-out path.
4. Log every event in `reply_log.csv`: `scheduled_for`, `sent_at`, `link_clicked_at`, `reply_received_at`, `reply_text`, `logged_in_crm_at`. Log each reply in HubSpot as well (email via BCC/log, DMs as a logged note).
5. Save screenshots to `seed_test/evidence/` as `S01_sent.png`, `S01_click.png` and so on, and put the filename in `evidence_file`.

## 5. Pass criteria (all must hold)

| Check | Pass when |
|---|---|
| Scheduling | 9/9 messages sent within 5 min of the scheduled time (email by scheduler, DMs by CRM task) |
| Tracking | 9/9 short links show ≥1 click with the correct `utm_content` |
| Reply logging | 3/3 replies logged in `reply_log.csv` and in the CRM within 15 min |
| Stop on reply | No further step was sent on a channel after its reply |
| Opt-out | The "no thanks" reply marked that contact as do-not-contact in the CRM |

When everything passes, set **04_SELF_CHECK C11 = Yes** and link this folder.
