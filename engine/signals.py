"""Evidence extraction from public feed text: contacts, social handles, money signals, needs, country."""

import re
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from urllib.parse import urlparse

EMAIL = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w-])")
BUSINESS_CONTEXT = re.compile(
    r"contact|business|inquir|enquir|sponsor|partner|collab|booking|book me|work with|email (me|us)|"
    r"reach (me|us|out)|get in touch|advertis|press|media kit|pitch|feedback|questions", re.I)

PLACEHOLDER_EMAIL_DOMAINS = {
    "anchor.fm", "spotify.com", "buzzsprout.com", "libsyn.com", "podbean.com", "simplecast.com",
    "megaphone.fm", "acast.com", "transistor.fm", "captivate.fm", "redcircle.com", "spreaker.com",
    "omnystudio.com", "omny.fm", "art19.com", "soundcloud.com", "castos.com", "podomatic.com",
    "blubrry.com", "example.com", "riverside.fm", "squarespace.com", "wix.com", "zencastr.com",
    "podcastpage.io", "fireside.fm", "pinecast.com", "audioboom.com", "whooshkaa.com",
    "rss.com", "sounder.fm", "simplecast.fm", "iono.fm", "hubhopper.com", "podcastics.com",
    "substack.com", "patreon.com", "supercast.com", "podpage.com",
}
PLATFORM_SITES = {
    "apple.com", "spotify.com", "youtube.com", "youtu.be", "linktr.ee", "linktree.com", "beacons.ai", "bio.link",
    "instagram.com", "facebook.com", "fb.me", "twitter.com", "x.com", "tiktok.com", "linkedin.com", "riverside.com",
    "patreon.com", "substack.com", "medium.com", "wordpress.com", "blogspot.com", "wixsite.com", "squarespace.com",
    "podpage.com", "podcastpage.io", "carrd.co", "linkin.bio", "taplink.cc", "lnk.bio", "campsite.bio",
    "google.com", "sites.google.com", "iheart.com", "amazon.com", "audible.com", "pod.link", "podlink.com",
    "podfollow.com", "smartlink.app", "bit.ly", "geni.us", "bandcamp.com", "soundcloud.com", "twitch.tv",
    "discord.gg", "discord.com", "eventbrite.com", "kajabi.com", "mykajabi.com", "teachable.com", "stan.store",
    "gumroad.com", "buymeacoffee.com", "ko-fi.com", "calendly.com", "mailchi.mp", "convertkit.com", "kit.com",
    "flodesk.com", "notion.site", "canva.site", "godaddysites.com", "weebly.com", "webflow.io", "github.io",
}
BAD_LOCALPARTS =re.compile(r"^(no-?reply|donotreply|privacy|legal|abuse|feeds?|rss|podcast-?feed|"
                            r"postmaster|webmaster|dmca|unsubscribe)\b", re.I)

SOCIAL_PATTERNS = {
    "Instagram": re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})", re.I),
    "X": re.compile(r"(?:twitter|x)\.com/([A-Za-z0-9_]{2,15})(?![A-Za-z0-9_])", re.I),
    "LinkedIn": re.compile(r"linkedin\.com/in/([A-Za-z0-9\-_%]{3,100})", re.I),
    "YouTube": re.compile(r"youtube\.com/(@[A-Za-z0-9_.\-]{3,40}|channel/UC[A-Za-z0-9_\-]{22}|c/[A-Za-z0-9_\-]{2,60})", re.I),
    "TikTok": re.compile(r"tiktok\.com/@([A-Za-z0-9_.]{2,30})", re.I),
}
SOCIAL_URL = {
    "Instagram": "https://www.instagram.com/{}/",
    "X": "https://x.com/{}",
    "LinkedIn": "https://www.linkedin.com/in/{}/",
    "YouTube": "https://www.youtube.com/{}",
    "TikTok": "https://www.tiktok.com/@{}",
}
SOCIAL_STOPWORDS = {
    "p", "reel", "reels", "explore", "stories", "accounts", "tv", "intent", "share", "home", "i",
    "search", "hashtag", "watch", "playlist", "about", "privacy", "legal", "help", "login",
    "spotifypodcasts", "spotify", "anchor", "anchorfm", "buzzsprout", "applepodcasts", "apple",
    "patreon", "youtube", "instagram", "twitter", "x", "tiktok", "linkedin", "podbean", "libsyn",
    "riverside_fm", "riversidefm", "acast", "acastpodcasts", "iheartradio", "iheartpodcasts",
    "simplecast", "captivatefm", "transistorfm", "redcircle", "podcasts", "podcast",
}

MONEY = [
    # Offer phrases only: a topic word ("coaching", "the book") in a guest bio is not the host selling something.
    ("Sponsorship", re.compile(r"sponsored by|today'?s sponsor|our sponsors?|thanks? to our (sponsor|partner)s?|"
                               r"(this|today'?s) episode is brought to you by(?! (you|our listeners|listeners))|"
                               r"episode sponsors?|"
                               r"promo code|use (the )?code|discount code|offer code|"
                               r"advertis(e|ing) (on|with) (the|our|this) (show|podcast)", re.I)),
    ("Membership/subscription", re.compile(r"patreon\.com|supercast|become a (patron|member|supporter)|"
                                           r"join (my|our) (paid |private )?(membership|community|club)|"
                                           r"buymeacoffee|ko-fi\.com|ad[- ]free (episodes|access|version|feed)|"
                                           r"bonus episodes|premium (episodes|feed|subscription)|"
                                           r"subscribe on apple podcasts for|"
                                           # Buzzsprout / Spotify listener-subscription links pay the creator
                                           r"buzzsprout\.com/\d+/support|podcasters\.spotify\.com/pod/show/[^/\s]+/support|"
                                           r"creators\.spotify\.com/pod/show/[^/\s]+/support", re.I)),
    ("Course/product", re.compile(r"\b(my|our) (new |online |signature |free )?(course|program|programme|"
                                  r"masterclass|bootcamp|academy|workshop|ebook|book|planner|templates?|toolkit|"
                                  r"mastermind|retreat|membership|certification)\b|"
                                  r"\b(enrol|enroll|register|join|apply)( now| today)? (for|in|to) (my|our|the) "
                                  r"(program|programme|course|mastermind|membership|coaching|cohort)|"
                                  r"pre-?order (my|our|the)|(our|my) merch|merch (store|shop)|"
                                  r"teachable\.com|kajabi|thinkific|gumroad\.com|stan\.store", re.I)),
    ("Service (coaching/consulting)", re.compile(r"work with (me|us)\b|book a (free )?(call|session|consult)|"
                                                 r"discovery call|clarity call|strategy call|"
                                                 r"(my|our) (1[:-]1 |private |group )?(coaching|consulting) "
                                                 r"(program|programme|practice|services?|packages?|offers?)|"
                                                 r"apply (now|here|for coaching|to work)|calendly\.com|hire me|"
                                                 r"speaking (inquiries|enquiries|engagements)|book me to speak", re.I)),
    ("Affiliate", re.compile(r"affiliate (link|code|program)|amzn\.to|earn (a )?commission|we may earn|"
                             r"referral link|my referral", re.I)),
]

NEED_TEXT = re.compile(r"(hiring|looking for|need) (an? )?(video )?(editor|producer|va|virtual assistant)|"
                       r"repurpos|transcript (coming|soon)|clips? (coming|soon)|back ?log|"
                       r"(sorry|apologi[sz]e) for (the )?(delay|late|gap|break|hiatus)|"
                       r"(back|return(ed|ing)?) (from|after) (a |our |my )?(break|hiatus)", re.I)

COUNTRY_FROM_LANG = {"en-us": "US", "en-ca": "CA", "en-gb": "GB", "en-uk": "GB", "en-ie": "IE",
                     "en-au": "AU", "en-nz": "NZ", "en-sg": "SG"}
COUNTRY_TLD = {".co.uk": "GB", ".uk": "GB", ".com.au": "AU", ".au": "AU", ".ca": "CA", ".ie": "IE",
               ".co.nz": "NZ", ".nz": "NZ", ".sg": "SG", ".com.sg": "SG"}
COUNTRY_WORDS = {
    "GB": r"\b(UK|United Kingdom|Britain|British|(?<!New )England|Scotland|(?<!New South )Wales|London|"
          r"Manchester|Glasgow|Edinburgh|Bristol|Leeds|Liverpool)\b",
    "AU": r"\b(Australia|Australian|Aussie|Sydney|Melbourne|Brisbane|Perth|Adelaide|Gold Coast)\b",
    "CA": r"\b(Canada|Canadian|Toronto|Vancouver|Montreal|Calgary|Ottawa|Edmonton)\b",
    "IE": r"\b(Ireland|Irish|Dublin|Cork|Galway)\b",
    "NZ": r"\b(New Zealand|Kiwi|Auckland|Wellington|Christchurch|Aotearoa)\b",
    "SG": r"\b(Singapore|Singaporean)\b",
    "US": r"\b(USA|U\.S\.A?\.|United States|Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|"
          r"Delaware|Florida|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|"
          r"Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|"
          r"New Jersey|New Mexico|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|"
          r"South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Wisconsin|Wyoming|"
          r"Los Angeles|San Francisco|Chicago|Houston|Seattle|Nashville|Atlanta|Dallas|Denver|Brooklyn|"
          r"Philadelphia|San Diego|Silicon Valley|Bay Area|NYC)\b",
}
COUNTRY_RX = {k: re.compile(v) for k, v in COUNTRY_WORDS.items()}
# First-person location statements ("based in Leeds", "here in Texas") are much stronger than a
# bare place name, which may just be a guest or a topic.
SELF_LOC = {k: re.compile(r"\b(based (in|out of)|here in|live in|living in|located in|serving|"
                          r"recorded in|coming to you from|from (beautiful|sunny)?)\s+(the\s+)?(" + v[3:-3] + r")\b")
            for k, v in COUNTRY_WORDS.items()}
SITE_BASED = {k: re.compile(r"\b(based (in|out of)|located in|headquartered in)\s+(the\s+)?(" + v[3:-3] + r")\b"
                            r"(?!,? (Ontario|ON|Kentucky|KY|Ohio|OH|Texas|TX|Arkansas|Connecticut))")
              for k, v in COUNTRY_WORDS.items()}
PHONE_CC ={"GB": re.compile(r"\+44\s?\(?\d"), "AU": re.compile(r"\+61\s?\(?\d"), "NZ": re.compile(r"\+64\s?\(?\d"),
            "IE": re.compile(r"\+353\s?\(?\d"), "SG": re.compile(r"\+65\s?\d{4}")}


def self_location(channel, items):
    """Countries the creator places themselves in, counted across the show and its episode notes."""
    hits = Counter()
    for weight, text in [(2, channel.get("description", ""))] + [(1, it["description"]) for it in items[:15]]:
        for cc, rx in SELF_LOC.items():
            if rx.search(text or ""):
                hits[cc] += weight
        for cc, rx in PHONE_CC.items():
            if rx.search(text or ""):
                hits[cc] += weight
    return hits
# Location words that point outside the approved markets; they veto a guessed country.
FOREIGN_RX = re.compile(r"\b(India|Indian|Nigeria|Nigerian|Kenya|Pakistan|Philippines|Filipino|"
                        r"South Africa|Ghana|Malaysia|Dubai|UAE)\b")

FREE_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
             "me.com", "aol.com", "live.com", "protonmail.com", "proton.me", "yahoo.co.uk",
             "hotmail.co.uk", "btinternet.com", "bigpond.com", "msn.com", "mac.com", "gmx.com"}


def email_domain(e):
    return e.rsplit("@", 1)[-1].lower()


def usable_email(e):
    e = e.strip().strip(".").lower()
    if not EMAIL.fullmatch(e):
        return None
    local, dom = e.rsplit("@", 1)
    if BAD_LOCALPARTS.match(local) or any(dom == d or dom.endswith("." + d) for d in PLACEHOLDER_EMAIL_DOMAINS):
        return None
    if re.search(r"\.(png|jpe?g|gif|webp|svg)$", dom):
        return None
    return e


def site_domain(url):
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


def find_contact_email(channel, items, website):
    """Pick the creator's own business email. Never guessed: it must appear verbatim in the feed.

    Returns (email, basis, evidence_ref) where evidence_ref is 'feed' or an item index.
    """
    site = site_domain(website)
    scored = []
    texts = [("channel", channel.get("description", ""))] + [(i, it["description"]) for i, it in enumerate(items)]
    counts = Counter()
    for ref, text in texts:
        for m in EMAIL.finditer(text or ""):
            e = usable_email(m.group(1))
            if not e:
                continue
            counts[e] += 1
            window = text[max(0, m.start() - 90): m.end() + 30]
            scored.append((e, ref, bool(BUSINESS_CONTEXT.search(window))))
    best = None
    for e, ref, biz in scored:
        dom = email_domain(e)
        owned = ref == "channel" or counts[e] >= 2 or (site and (dom == site or site.endswith("." + dom)))
        if not owned:
            continue  # one-off emails in episode notes are usually guests, not the host
        rank = (2 if biz else 1) + (1 if ref == "channel" else 0)
        if best is None or rank > best[0]:
            basis = "business contact published in show notes" if biz else "email published in show notes"
            best = (rank, e, basis, ref)
    if best:
        return best[1], best[2], best[3]
    owner = usable_email(channel.get("owner_email", "") or "")
    if owner:
        return owner, "podcast owner contact published in the RSS feed (itunes:owner)", "feed"
    ed = EMAIL.search(channel.get("managing_editor", "") or "")
    if ed and usable_email(ed.group(1)):
        return usable_email(ed.group(1)), "managing editor contact published in the RSS feed", "feed"
    return None, None, None


def find_socials(channel, items):
    """Handles the creator links repeatedly (owned), with the newest item index that links each."""
    weight = defaultdict(Counter)
    newest = {}
    sources = [("channel", channel.get("description", "") + " " + " ".join(channel.get("links", [])))]
    sources += [(i, it["description"] + " " + " ".join(it.get("links", []))) for i, it in enumerate(items)]
    for ref, text in sources:
        seen = set()
        for plat, rx in SOCIAL_PATTERNS.items():
            for m in rx.finditer(text):
                h = m.group(1).rstrip(".")
                key = h.lower()
                if key.split("/")[-1].lstrip("@") in SOCIAL_STOPWORDS or (plat, key) in seen:
                    continue
                seen.add((plat, key))
                weight[plat][h] += 3 if ref == "channel" else 1
                if ref != "channel" and (plat, h) not in newest:
                    newest[(plat, h)] = ref
    out = {}
    for plat, c in weight.items():
        h, w = c.most_common(1)[0]
        if w >= 2:
            out[plat] = {"handle": h, "url": SOCIAL_URL[plat].format(h), "weight": w,
                         "newest_item": newest.get((plat, h))}
    return out


LINK_HANDLE = re.compile(r"(?:patreon\.com/(?:c/)?|buymeacoffee\.com/|ko-fi\.com/|calendly\.com/|stan\.store/|"
                         r"gumroad\.com/l?/?|teachable\.com/|kajabi\.com/)([A-Za-z0-9_.\-]+)|"
                         r"([A-Za-z0-9\-]+)\.(?:mykajabi|teachable|thinkific|gumroad)\.com", re.I)


URL = re.compile(r"https?://[^\s<>\"')]+", re.I)
OWNED_KINDS = {"Membership/subscription", "Course/product", "Service (coaching/consulting)"}
MARKETPLACES = {"amazon.com", "amazon.co.uk", "amazon.com.au", "amazon.ca", "amzn.to", "audible.com", "bookshop.org",
                "barnesandnoble.com", "buzzsprout.com", "podcasters.spotify.com", "creators.spotify.com",
                "apple.com", "books.apple.com", "kobo.com", "waterstones.com", "booktopia.com.au", "indigo.ca"}


def money_signals(channel, items, owner_check=None):
    """[(type, evidence_ref, snippet)] — first hit per type, newest item first.

    Link-based evidence (Patreon, Calendly, Kajabi…) only counts when the link is the creator's own:
    show notes routinely link guests' pages too."""
    found = {}
    texts = [(i, it["description"] + " " + " ".join(it.get("links", []))) for i, it in enumerate(items)]
    texts.append(("channel", channel.get("description", "") + " " + " ".join(channel.get("links", []))))
    for ref, text in texts:
        for kind, rx in MONEY:
            if kind in found:
                continue
            for m in rx.finditer(text):
                window = text[max(0, m.start() - 5): m.end() + 60]
                lh = LINK_HANDLE.search(window)
                if lh and owner_check and not owner_check(lh.group(1) or lh.group(2)):
                    continue
                first_person = re.match(r"(my|our|work with (me|us)|hire me|book me)\b", m.group(0), re.I)
                if owner_check and kind in OWNED_KINDS and not lh and not first_person:
                    # "become a member: https://other-org.org" is someone else's offer
                    u = URL.search(window)
                    dom = site_domain(u.group(0)) if u else ""
                    if dom and not any(dom == d or dom.endswith("." + d) for d in MARKETPLACES) \
                            and not owner_check(dom.split(".")[0] if dom.count(".") < 2 else dom.split(".")[-3]):
                        continue
                found[kind] = (kind, ref, text[max(0, m.start() - 40): m.end() + 60].strip())
                break
    if channel.get("has_podcast_ns_funding") and "Membership/subscription" not in found:
        found["Membership/subscription"] = ("Membership/subscription", "feed", "podcast:funding tag in feed")
    return list(found.values())


def activity(items, now, longform_min):
    dates = []
    long60 = n30 = 0
    for it in items:
        if not it["published"]:
            continue
        d = datetime.fromisoformat(it["published"])
        age = (now - d).days
        if age < -2:
            continue  # future-dated (scheduled or broken) items do not count
        dates.append(d)
        if age <= 30:
            n30 += 1
        if age <= 60 and (it["duration_sec"] or 0) >= longform_min * 60:
            long60 += 1
    dates.sort(reverse=True)
    gaps = [(dates[i] - dates[i + 1]).days for i in range(min(len(dates) - 1, 12))]
    durs = [it["duration_sec"] for it in items[:10] if it["duration_sec"]]
    return {
        "count_30d": n30,
        "longform_60d": long60,
        "latest": dates[0] if dates else None,
        "median_gap_days": median(gaps) if gaps else None,
        "max_gap_days": max(gaps) if gaps else None,
        "avg_minutes": round(sum(durs) / len(durs) / 60) if durs else None,
    }


def need_signals(channel, items, socials, act):
    """Concrete, checkable reasons this creator would use IncuBrix (clips, captions, publishing)."""
    recent = items[:10]
    needs = []
    if recent and not any(it["has_transcript"] for it in recent):
        needs.append(("Captions/transcripts", f"none of the last {len(recent)} episodes publish a transcript"))
    shortform = {"Instagram", "TikTok", "YouTube"} & set(socials)
    avg = act.get("avg_minutes")
    if avg and avg >= 20 and not ({"TikTok"} & shortform):
        missing = [p for p in ("YouTube", "Instagram", "TikTok") if p not in socials]
        needs.append(("Repurposing into clips",
                      f"~{avg}-min episodes; no {'/'.join(missing)} clip channel linked in the feed"))
    video = sum(1 for it in recent if it["enclosure_type"].startswith("video"))
    if video:
        needs.append(("Video clipping", f"{video} of the last {len(recent)} episodes are video files"))
    mg, xg = act.get("median_gap_days"), act.get("max_gap_days")
    if mg and xg and xg >= max(21, 3 * mg):
        needs.append(("Publishing consistency", f"gap of {xg} days between episodes vs a usual {mg:g}-day rhythm"))
    for i, it in enumerate(recent):
        m = NEED_TEXT.search(it["description"]) or NEED_TEXT.search(it["title"])
        if m:
            needs.append(("Stated workflow need", f'episode notes say "{m.group(0)}"'))
            break
    return needs


US_ADDR = re.compile(r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|"
                     r"NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY),?\s+\d{5}(-\d{4})?\b")
SITE_RX = {
    "CA": re.compile(r"\b(AB|BC|MB|NB|NL|NS|ON|PE|QC|SK|YT),?\s+[A-Z]\d[A-Z]\s?\d[A-Z]\d\b"),
    "AU": re.compile(r"\b(NSW|VIC|QLD|WA|SA|TAS|ACT|NT),?\s+\d{4}\b|\bA\.?B\.?N\.?:?\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b"),
    "GB": re.compile(r"[Rr]egistered in (England|Scotland|Wales)|\b[A-Z]{1,2}\d[A-Z\d]? \d[A-Z]{2},? "
                     r"(UK|United Kingdom|England|Scotland|Wales)\b|\+44\s?\(?0?\)?\s?\d{2,4}\s?\d{3}"),
    "IE": re.compile(r"\+353\s?\d|\b(Dublin|Cork|Galway|Limerick) D?\d{2}\s?[A-Z0-9]{4}\b"),
    "NZ": re.compile(r"\b\d{4},? New Zealand\b|\+64\s?\d"),
    "SG": re.compile(r"\bSingapore \d{6}\b|\+65\s?[689]\d{3}\s?\d{4}"),
}


def website_country(html):
    """Postal-address / registration / phone evidence on the creator's own homepage."""
    text = re.sub(r"\s+", " ", html_unescape(re.sub(r"<[^>]+>", " ", html or "")))
    hits = {}
    m = US_ADDR.search(text)
    if m:
        hits["US"] = m.group(0)
    for cc, rx in SITE_RX.items():
        m = rx.search(text)
        if m:
            hits[cc] = m.group(0)
    if not hits:
        # an explicit "based in Leeds" on their own site, if it names exactly one country
        for cc, rx in SITE_BASED.items():
            m = rx.search(text)
            if m:
                hits[cc] = m.group(0)
    if "US" in hits and "CA" in hits:
        hits.pop("US")  # a Canadian postal code is more specific than a US-looking state+zip
    if len(hits) == 1:
        cc, snip = next(iter(hits.items()))
        return cc, snip
    return None, ("conflicting: " + ", ".join(hits)) if hits else None


def html_unescape(s):
    import html as _h
    return _h.unescape(s)


def tz_region(items):
    """Where the creator's publishing clock is set, from the offsets written in pubDate."""
    offs = [it.get("tz_offset_min") for it in items[:15] if it.get("tz_offset_min") is not None]
    if len(offs) < 3:
        return None, None
    o = Counter(offs).most_common(1)[0][0]
    if -600 <= o <= -240:  # -0300 in Oct is Atlantic Canada or South America: not usable for US
        return "NA", o
    if o in (570, 600, 630, 660):
        return "AU", o
    if o in (720, 765, 780):
        return "NZ", o
    if o == 60:
        return "UKIE", o
    return "OTHER", o


def _fmt_off(o):
    return f"{'+' if o >= 0 else '-'}{abs(o) // 60:02d}{abs(o) % 60:02d}"


def infer_country(channel, website, email, store_country, items=(), extra_text="", site_info=None):
    """Return (iso2 or None, basis). Uses only signals the creator published; never the store alone."""
    cc, basis = _infer_country(channel, website, email, store_country, items, extra_text)
    if cc is None and site_info and site_info.get("country") and "conflicting" not in basis:
        region, _ = tz_region(list(items))
        fits = {"NA": {"US", "CA"}, "AU": {"AU"}, "NZ": {"NZ"}, "UKIE": {"GB", "IE"}}
        sc = site_info["country"]
        if region in (None, "OTHER") or sc in fits.get(region, ()):
            return sc, f"creator's website {site_info['url']} shows '{site_info['snippet']}'"
    return cc, basis


def _infer_country(channel, website, email, store_country, items=(), extra_text=""):
    lang = (channel.get("language") or "").lower().replace("_", "-")
    text = " ".join([channel.get("description", ""), channel.get("location", ""), channel.get("title", ""),
                     extra_text])
    region, off = tz_region(list(items))
    tz_txt = f"episode timestamps use UTC{_fmt_off(off)}" if off is not None else ""
    hints = {}
    if lang in COUNTRY_FROM_LANG:
        hints["lang"] = COUNTRY_FROM_LANG[lang]
    for src, val in (("website", site_domain(website)), ("email", email_domain(email) if email else "")):
        for tld, cc in sorted(COUNTRY_TLD.items(), key=lambda kv: -len(kv[0])):
            if val.endswith(tld):
                hints[src] = cc
                break
    words = {cc for cc, rx in COUNTRY_RX.items() if rx.search(text)}
    loc = channel.get("location", "")
    if loc:
        for cc, rx in COUNTRY_RX.items():
            if rx.search(loc):
                return cc, f"podcast:location '{loc}'"
    if FOREIGN_RX.search(text) and not words:
        return None, "show description names a location outside approved markets"
    strong = {v for k, v in hints.items() if k in ("website", "email")}
    if len(strong) == 1:
        cc = strong.pop()
        if words and cc not in words:
            return None, f"conflicting signals ({cc} domain vs description mentions {','.join(sorted(words))})"
        return cc, "creator's own domain (" + ", ".join(f"{k}: {hints[k]}" for k in ("website", "email") if k in hints) + ")"
    tz_fits = {"NA": {"US", "CA"}, "AU": {"AU"}, "NZ": {"NZ"}, "UKIE": {"GB", "IE"}}
    if "lang" in hints:
        cc = hints["lang"]
        if words and cc not in words:
            if cc == "US" and len(words) == 1:
                w = next(iter(words))
                if region in (None, "OTHER") or w in tz_fits.get(region, ()):
                    # en-us is a default on many hosts; an explicit place name in the description wins
                    return w, f"show description names it (feed language '{lang}' is a host default)"
            return None, f"conflicting signals (feed language {lang} vs description mentions {','.join(sorted(words))})"
        if cc == "US" and region in ("AU", "NZ", "UKIE"):
            return None, f"conflicting signals (feed language {lang} but {tz_txt})"
        if cc == "US" and region != "NA" and "US" not in words and self_location(channel, items)["US"] < 1:
            # 'en-us' is the default on many hosting platforms, so it needs corroboration
            return None, f"feed language '{lang}' is a common host default and nothing corroborates a US base"
        basis = f"feed language set to '{lang}'" + (f"; {tz_txt}" if region and cc in tz_fits.get(region, ()) else "")
        return cc, basis
    if len(words) == 1:
        w = next(iter(words))
        if region in (None, "OTHER") or w in tz_fits.get(region, ()) or (w == "US" and region == "NA"):
            return w, "show description names the country/city" + (f"; {tz_txt}" if region else "")
        return None, f"conflicting signals (description says {w} but {tz_txt})"
    if not words and region == "NA" and lang in ("en", ""):
        # some hosts default to US Eastern time; a non-US place named across episodes outweighs the clock
        ep_words = Counter(cc for it in list(items)[:15] for cc, rx in COUNTRY_RX.items()
                           if cc != "US" and rx.search(it.get("description", "")))
        if ep_words and ep_words.most_common(1)[0][1] >= 2:
            return None, f"conflicting signals ({tz_txt} but episodes mention {ep_words.most_common(1)[0][0]})"
        return "US", f"{tz_txt} (North America) and no Canadian signal in the show description"
    if not words and region in ("AU", "NZ"):
        return region, f"{tz_txt} ({'Australia' if region == 'AU' else 'New Zealand'})"
    if len(words) > 1 and region:
        fit = [w for w in words if w in tz_fits.get(region, ())]
        if len(fit) == 1:
            return fit[0], f"show description names it and {tz_txt}"
    selfloc = self_location(channel, items)
    if selfloc:
        (cc, n), *rest = selfloc.most_common()
        if n >= 2 and (not rest or rest[0][1] * 3 <= n) and (region in (None, "OTHER") or cc in tz_fits.get(region, ())
                                                             or (cc == "US" and region == "NA")):
            return cc, f"creator states their location in show/episode notes ({n} mentions)"
    return None, f"no creator-published country signal (feed language '{lang or 'missing'}'{', ' + tz_txt if tz_txt else ''})"
