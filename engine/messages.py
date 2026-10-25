"""Personalised outreach sequences. Every message names a specific recent episode, says who is
sending, carries a tracked link and an opt-out, and stays inside each platform's length limits."""

import re
from datetime import date
from urllib.parse import urlencode

DM_LIMITS = {"LinkedIn": 300, "Instagram": 1000, "X": 1000, "TikTok": 500}
SEND_DAYS = (0, 4, 10)
BACKUP_DAY = 14

SEGMENT_LINE = {
    "Podcaster/Video Podcaster": "For podcasters it means one episode becomes a week of clips, quotes and posts.",
    "YouTuber/Video-First Creator": "For YouTubers it means your back catalogue becomes a Shorts and Reels library.",
    "Expert-Led Creator": "For coaches and educators it means every session insight becomes content that finds new clients.",
}
AUDIENCE_NOUN = {
    "Podcaster/Video Podcaster": "episode",
    "YouTuber/Video-First Creator": "video",
    "Expert-Led Creator": "episode",
}


def short(title, n=60):
    title = (title or "").strip().strip('"')
    return title if len(title) <= n else title[: n - 1].rsplit(" ", 1)[0] + "…"


def short_show(name):
    """'EAT SLEEP WINE REPEAT: A Wine Podcast Exploring…' -> 'EAT SLEEP WINE REPEAT'."""
    s = re.split(r"\s*(?:[:|–—]|\s-\s|\(|\[)\s*", (name or "").strip(), maxsplit=1)[0].strip()
    s = re.sub(r"[®™©]", "", s).strip()
    return s if len(s) >= 3 else (name or "").strip()


def clean_episode(title):
    """Drop 'Ep 279 –' / '#12:' / 'Episode 5 -' prefixes for natural reading."""
    t = re.sub(r"^\s*(ep(isode)?\.?\s*#?\d+|#\d+|s\d+\s*e\d+)\s*[:\-–—|.]?\s*", "", title or "", flags=re.I)
    return t.strip() or (title or "").strip()


def pretty_date(iso):
    try:
        d = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"{d.strftime('%b')} {d.day}"


def tracking_link(cfg, lead, channel, step):
    t = cfg["tracking"]
    q = {"utm_source": channel.lower().replace(" ", "_"), "utm_medium": "outreach",
         "utm_campaign": t["campaign"], "utm_content": f"{lead.get('lead_id') or lead['key']}-s{step}"}
    return t["base_url"] + "?" + urlencode(q)


def need_line(lead):
    """One honest sentence tied to the evidence we actually hold for this creator."""
    types = lead.get("need_types") or []
    socials = lead.get("socials") or {}
    mins = lead.get("avg_minutes")
    noun = AUDIENCE_NOUN.get(lead["creator_segment"], "episode")
    quote = lead.get("need_quote") or ""
    if not quote and 'notes say "' in (lead.get("incubrix_need") or ""):
        quote = lead["incubrix_need"].split('notes say "', 1)[-1].split('"', 1)[0]
    if "Stated workflow need" in types and quote:
        return f'Your show notes mention "{quote}", which is exactly the work IncuBrix takes off a creator\'s plate.'
    if "Video clipping" in types:
        return f"Since you already record on video, the clips in each {noun} are basically shot; they just need cutting and captioning."
    if "Repurposing into clips" in types and mins:
        missing = [p for p in ("YouTube Shorts", "Instagram Reels", "TikTok")
                   if p.split()[0] not in socials]
        where = " or ".join(missing[:2]) if missing else "short-form"
        return (f"At ~{mins} minutes per {noun}, there are easily ten clips in each one, and I didn't see a "
                f"{where} channel linked from the show.")
    if "Publishing consistency" in types:
        return "I noticed a few longer gaps in the feed, and a bank of ready-made clips is a simple way to keep channels moving through busy weeks."
    if "Captions/transcripts" in types:
        return f"I couldn't find a transcript or captioned cut of it, which is usually the easiest reach a show leaves on the table."
    return f"It's the kind of {noun} that travels well as short clips."


def signature(cfg):
    """Full sign-off. Role/affiliation come from config so nobody is presented as staff they aren't."""
    s = cfg["sender"]
    return f"{s['name']}\n{s['role']} {s.get('affiliation', 'for IncuBrix')} ({s['company_legal']}, {s['address']})"


def short_sign(cfg):
    s = cfg["sender"]
    return f"{s['name']} ({s.get('affiliation', 'for IncuBrix')})"


def intro(cfg):
    return cfg["sender"].get("intro", "I'm helping launch IncuBrix")


def guest(cfg):
    return cfg["sender"].get("guest_name") or "someone from the IncuBrix team"


def optout_email():
    return 'Not for you? Reply "no thanks" and I won\'t email you again.'


def optout_dm():
    return "If it's not relevant, just say so and I won't message again."


def _ctx(lead, cfg):
    return {
        "first": lead.get("first_name") or "there",
        "show": short_show(lead["show_name"]),
        "ep": short(clean_episode(lead.get("recent_title")), 90),
        "ep_short": short(clean_episode(lead.get("recent_title")), 48),
        "ep_date": pretty_date(lead.get("recent_date")),
        "ep2": short(clean_episode(lead.get("second_title")), 70),
        "need": need_line(lead),
        "seg": SEGMENT_LINE.get(lead["creator_segment"], SEGMENT_LINE["Podcaster/Video Podcaster"]),
        "noun": AUDIENCE_NOUN.get(lead["creator_segment"], "episode"),
        "sender": short_sign(cfg),
        "name": cfg["sender"]["name"],
        "intro": intro(cfg),
        "sig": signature(cfg),
    }


def email_steps(lead, cfg, channel="Email"):
    c = _ctx(lead, cfg)
    ep_when = f" ({c['ep_date']})" if c["ep_date"] else ""
    later = (f'Your earlier {c["noun"]}, "{c["ep2"]}", would work just as well. '
             if c["ep2"] else "")
    s1 = (f'"{c["ep_short"]}" as clips?',
          f'Hi {c["first"]},\n\n'
          f'I came across "{c["ep"]}" from {c["show"]}{ep_when}. {c["need"]}\n\n'
          f"IncuBrix is a creator studio that turns one recording into captioned clips, quote posts and "
          f"platform-sized versions, then schedules them to YouTube, Instagram, LinkedIn and Spotify from one "
          f"screen. {c['seg']}\n\n"
          f'If it helps, I can run "{c["ep_short"]}" through it and send you three ready-to-post clips. '
          f"No call and no card needed. Would that be useful?\n\n"
          f"{c['sig']}\n{tracking_link(cfg, lead, channel, 1)}\n\n{optout_email()}")
    s2 = (f'Re: "{c["ep_short"]}" as clips?',
          f'Hi {c["first"]}, a quick follow-up on my note about "{c["ep_short"]}". {later}'
          f"IncuBrix picks out the strongest moments, adds word-by-word captions in your own fonts and colours, "
          f"and lets you fix a flubbed line by editing the transcript instead of re-recording.\n\n"
          f"Happy to send the three sample clips. Just reply \"yes\".\n\n"
          f"{c['sender']}\n{tracking_link(cfg, lead, channel, 2)}\n\n{optout_email()}")
    s3 = (f"Closing the loop, {c['show']}",
          f"Hi {c['first']}, last note from me. If clipping and captioning {c['show']} isn't a priority right now, "
          f"no problem at all. If it becomes one, you can start free (no card) here: "
          f"{tracking_link(cfg, lead, channel, 3)}\n\nThanks for making the show.\n\n{c['sender']}\n\n"
          f"{optout_email()}")
    return [s1, s2, s3]


def dm_steps(lead, cfg, platform):
    c = _ctx(lead, cfg)
    link = tracking_link(cfg, lead, platform, 1)
    if platform == "LinkedIn":
        s1 = (f'Hi {c["first"]}, I came across "{c["ep_short"]}" from {c["show"]}. {c["intro"]}, which turns '
              f"one episode into captioned clips and posts for every platform. Would be glad to connect. "
              f"- {c['name']}")
    else:
        s1 = (f'Hi {c["first"]}! Just found "{c["ep_short"]}" from {c["show"]}. {c["need"]} '
              f"I'm {c['name']}. {c['intro']}, which turns one recording into captioned, ready-to-post clips. "
              f"Want me to send 3 free sample clips from that {c['noun']}? {optout_dm()}")
    s2 = (f"Thanks, {c['first']}. Here's what I meant: IncuBrix finds the best moments in "
          f'"{c["ep_short"]}", adds captions in your style, and schedules them to YouTube, Instagram, '
          f"LinkedIn and Spotify from one screen. Free to start: {link} {optout_dm()}")
    s3 = (f"Last nudge from me, {c['first']}. If sample clips from {c['show']} would ever be useful, "
          f"just reply and I'll send them. Otherwise, all the best with the show! - {c['sender']}")
    return [(None, _fit(s, DM_LIMITS.get(platform, 1000))) for s in (s1, s2, s3)]


def guest_pitch_steps(lead, cfg):
    c = _ctx(lead, cfg)
    g = guest(cfg)
    s1 = (f"Guest idea for {c['show']}: one episode, a week of content",
          f'Hi {c["first"]},\n\nI enjoyed seeing "{c["ep"]}" come through the {c["show"]} feed. '
          f"I'd like to suggest {g} as a guest. Possible angles for your listeners:\n"
          f"1. How solo creators turn one recording into 10+ short clips without an editor\n"
          f"2. What actually gets reach on Shorts, Reels and LinkedIn for long-form shows in 2026\n"
          f"3. Captions, transcripts and voice-cloned fixes: where AI saves creators hours, and where it doesn't\n\n"
          f"Happy to fit your format and schedule.\n\n{c['sig']}\n{tracking_link(cfg, lead, 'Podcast guest pitch', 1)}"
          f"\n\n{optout_email()}")
    s2 = (f"Re: Guest idea for {c['show']}",
          f"Hi {c['first']}, following up on the guest idea. If a different angle would fit {c['show']} better, "
          f"I'm glad to shape it around your audience.\n\n{c['sender']}\n\n{optout_email()}")
    s3 = (f"Re: Guest idea for {c['show']}",
          f"Hi {c['first']}, I'll leave it here. If you ever want a guest on content workflow or repurposing, "
          f"the offer stands.\n\n{c['sender']}\n\n{optout_email()}")
    return [s1, s2, s3]


def _fit(text, limit):
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def steps_for(lead, cfg, channel):
    if channel in ("Email", "Contact form"):
        return email_steps(lead, cfg, channel)
    if channel == "Podcast guest pitch":
        return guest_pitch_steps(lead, cfg)
    if channel in DM_LIMITS:
        return dm_steps(lead, cfg, channel)
    return []


def first_message(lead, cfg):
    steps = steps_for(lead, cfg, lead["best_channel"])
    if not steps:
        return ""
    subj, body = steps[0]
    return f"Subject: {subj}\n\n{body}" if subj else body


def sequence(lead, cfg):
    """Full multi-channel sequence: 3 touches on the best channel, then 1 on the backup."""
    out = []
    for i, (subj, body) in enumerate(steps_for(lead, cfg, lead["best_channel"])):
        out.append({"channel": lead["best_channel"], "step": i + 1, "send_day": SEND_DAYS[i],
                    "to": lead["channel_handle_or_url"], "subject": subj or "", "body": body})
    if lead.get("backup_channel") and lead["backup_channel"] != lead["best_channel"]:
        b = steps_for(lead, cfg, lead["backup_channel"])
        if b:
            subj, body = b[0]
            out.append({"channel": lead["backup_channel"], "step": 4, "send_day": BACKUP_DAY,
                        "to": lead["backup_handle_or_url"], "subject": subj or "", "body": body})
    return out
