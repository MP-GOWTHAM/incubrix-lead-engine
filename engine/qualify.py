"""Turns a discovered show plus its parsed feed into a lead record with a pass/fail verdict.

Every check from the brief is applied here; a lead is Qualified only if all pass, and each
claim carries the public URL it came from.
"""

import re
from datetime import timedelta

from . import signals as S

EXCLUDE_ENTITY = re.compile(
    r"\b(network|networks|media|studios?|radio|news|broadcast(ing)?|iheart\w*|npr|bbc|wondery|audacy|"
    r"podcastone|sirius\w*|cnn|fox|abc|cbs|nbc|pbs|msnbc|times|magazine|journal|gazette|tribune|"
    r"inc\.?|llc|l\.l\.c\.|ltd\.?|limited|corp\.?|corporation|agency|church|ministr(y|ies)|"
    r"university|college|school|association|foundation|council|government|department|library|"
    r"museum|bank|institute|society|productions?|publishing|entertainment|group|capital|"
    r"management|talent|records|chamber|federation|hospital|clinic)\b", re.I)
EXCLUDE_GENRES = {"News", "Daily News", "Politics", "Government", "Kids & Family", "Stories for Kids",
                  "Education for Kids", "Christianity", "Judaism", "Islam", "Buddhism", "Hinduism",
                  "Religion", "Religion & Spirituality", "News Commentary", "Tech News", "Sports News",
                  "Entertainment News", "Business News"}
EXPERT_GENRES = {"Business", "Careers", "Entrepreneurship", "Management", "Marketing", "Investing",
                 "Non-Profit", "Education", "Self-Improvement", "How To", "Courses", "Language Learning",
                 "Health & Fitness", "Fitness", "Nutrition", "Mental Health", "Medicine",
                 "Alternative Health", "Sexuality", "Relationships", "Parenting", "Personal Journals"}
NAME_PART = r"[A-Z][a-zA-Z'’\-]+"
PERSON = re.compile(rf"^(Dr\.? |Coach )?{NAME_PART}( [A-Z]\.?)?( {NAME_PART}){{1,2}}$")
HOST_PHRASE = re.compile(rf"(?:hosted by|host(?:ed)? with|with (?:your )?host|your host,?|I'?m|I am|my name is)\s+"
                         rf"((?:Dr\.? )?{NAME_PART}(?: {NAME_PART}){{1,2}})")
SPLIT_NAMES = re.compile(r"\s*(?:&|\band\b|,|\+|/|\|)\s*")
NON_NAMES = re.compile(
    r"\b(the|podcast|podcasts|show|pod|cast|talks?|chats?|daily|weekly|hour|club|crew|team|official|project|"
    r"collective|life|living|world|lab|hq|tv|health|care|clinic|therapy|wellness|fitness|nutrition|yoga|"
    r"marketing|sales|business|hacks?|money|finance|wealth|gaming|games|legends|connection|coaching|media|"
    r"history|kitchen|garden|mind|minds|success|growth|leadership|school|women'?s|men'?s|moms?|mums?|dads?|"
    r"girls|guys|ladies|bros|radio|stories|studio|company|co|brand|brands|ventures|solutions|consulting|academy|"
    r"institute|tech|digital|online|global|international|hub|nation|tribe|society|minds|conversations|sessions|"
    r"unplugged|uncut|unfiltered|real|true|simple|smart|happy|healthy|wealthy|wise|bold|brave|mindful|"
    r"content|copywriting|creative|creatives|design|photography|realty|estate|property|properties|law|legal|"
    r"melbourne|sydney|london|toronto|vancouver|dublin|auckland|singapore|australia|canada|ireland|"
    r"fm|support|enterprises|review|independent|wire|brew|travel|medicine|mates|trust|uk|nz|usa|farm|farms|"
    r"confidential|notes|kitchen|cafe|bar|band|records|books|press|guys|girls|sisters|brothers|bros)\b", re.I)
AGENCY_DOMAIN = re.compile(r"agency|management|talent|studios|network|records|publishing|^news$|newscorp|"
                           r"radio|broadcast|podcastnetwork", re.I)
ORG_SHOW = re.compile(r"\b(radio|network|news|university|council|foundation|association|hospital|church|"
                      r"chamber of commerce|institute|society|charity|government)\b", re.I)
TOKEN_STOP = {"the", "podcast", "show", "with", "and", "for", "your", "from", "this", "that", "official", "talk",
              "talks", "radio", "life", "into", "about", "what", "when", "where", "how", "why", "inside", "real"}


def _tokens(*texts):
    out = set()
    for t in texts:
        for w in re.findall(r"[a-z]+", (t or "").lower()):
            if len(w) >= 4 and w not in TOKEN_STOP:
                out.add(w)
    return out


CAMEL_BRAND = re.compile(r"^[A-Z][a-z]{3,}[A-Z]")  # NerdWallet, MediaWorks; but TaShawn, JoAnna, McKenzie are names


def name_corroborated(name, ch, show, items=(), email=""):
    """A listed author only counts as a person if a second source names them in a person's role."""
    parts = name.split()
    first = parts[1] if parts[0].rstrip(".").lower() in ("dr", "coach") and len(parts) > 1 else parts[0]
    if CAMEL_BRAND.match(first) and not re.match(r"^(Mc|Mac|Van|Von)[A-Z]", first):
        return False
    fl = first.lower()
    # independent sources only: an owner name or host tag that differs from the listed name,
    # or a mailbox that reads like a person's ("chris@", "jennifer.smith@"), not a brand inbox
    is_title = _tokens(name) <= _tokens(show) or name.lower() in (show or "").lower()
    owner = (ch.get("owner_name") or "").strip()
    sources = [h for h in (ch.get("hosts") or [])]
    if owner and (owner.lower() != name.lower() or not is_title):
        sources.append(owner)
    if any(fl in s.lower().split() for s in sources):
        return True
    for mail in (ch.get("owner_email") or "", email or ""):
        local = mail.split("@")[0].lower()
        if not is_title and (local == fl or re.match(rf"^{re.escape(fl)}[._-][a-z]", local)):
            return True
    rx = re.compile(rf"(hosted by|your host,?|host|hosts|co-?hosts?|I'?m|I am|my name is)\s+(Dr\.? )?{re.escape(first)}\b"
                    rf"|\b{re.escape(first)}\s+(here|shares (her|his|their)|is joined by|sits down with|chats with)\b", re.I)
    texts = [(ch.get("description") or "").replace(show, " ")] + [it["description"] for it in list(items)[:15]]
    return any(rx.search(t) for t in texts)


def owns_contact(handle, creator_name, show_name):
    """True if an address/handle visibly belongs to this creator or show (not an employer, producer or sponsor)."""
    h = re.sub(r"[^a-z]", "", (handle or "").lower())
    toks = _tokens(creator_name, show_name)
    squashed = re.sub(r"[^a-z]", "", re.sub(r"(?i)\b(the|podcast|show)\b", "", show_name or "").lower())
    if any(t in h for t in toks) or (len(squashed) >= 5 and squashed[:10] in h):
        return True
    initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", show_name or "")).lower()  # "ESG Fitness"
    return len(initials) >= 3 and initials in h
SOCIAL_PREF_EXPERT = ["LinkedIn", "Instagram", "X", "YouTube", "TikTok"]
SOCIAL_PREF_DEFAULT = ["Instagram", "X", "YouTube", "LinkedIn", "TikTok"]
DM_PLATFORMS = {"Instagram", "X", "LinkedIn", "TikTok"}


def is_person(name):
    name = (name or "").strip()
    if not name or NON_NAMES.search(name) or EXCLUDE_ENTITY.search(name):
        return False
    parts = [p for p in SPLIT_NAMES.split(name) if p]
    return 0 < len(parts) <= 3 and all(PERSON.match(p) for p in parts)


SEGMENT_SPLIT = re.compile(r"\s+[|\-–—*•~]\s+|\s*\|\s*|:\s+|,\s+|\s+[–—]\s*|\s*[–—]\s+")
TRAILING_NAME = re.compile(rf"(?:Coach|Expert|Strategist|with|by)\s+((?:Dr\.? )?{NAME_PART}(?: {NAME_PART}){{1,2}})$")


def lead_segment(s):
    """'Kristin Morrison | Pet Business Coach | ...' -> 'Kristin Morrison'."""
    return SEGMENT_SPLIT.split((s or "").strip(), 1)[0].strip(" ,;.-")


def creator_identity(cand, ch):
    for n in (cand.get("artistName"), ch.get("author"), ch.get("owner_name")):
        head = lead_segment(n)
        if is_person(head):
            return head, "listed author"
        m = TRAILING_NAME.search(head)
        if m and is_person(m.group(1)):
            return m.group(1), "listed author"
    for h in ch.get("hosts") or []:
        if is_person(h):
            return h, "podcast:person host tag in feed"
    m = HOST_PHRASE.search(ch.get("description", ""))
    if m and is_person(m.group(1)):
        return m.group(1), "named host in show description"
    return None, None


def first_name(creator_name):
    first = SPLIT_NAMES.split(creator_name)[0].replace("Dr. ", "Dr ").split()
    if first and first[0] in ("Dr", "Dr.", "Coach") and len(first) > 1:
        return "Dr " + first[-1] if first[0].startswith("Dr") else first[1]
    return first[0] if first else "there"


def _ref_url(ref, items, feed_url):
    if isinstance(ref, int) and 0 <= ref < len(items):
        link = items[ref].get("link") or ""
        if link.startswith("http"):
            return link
    return feed_url


def clean_profile_url(u):
    return re.sub(r"\?uo=\d+$", "", u or "")


def evaluate(cand, parsed, now, cfg, site_info=None):
    q = cfg["qualify"]
    ch, items = parsed["channel"], parsed["items"]
    feed_url = cand["feedUrl"]
    reasons = []
    lead = {
        "key": cand["key"],
        "show_name": cand.get("collectionName") or ch.get("title"),
        "primary_platform": "Apple Podcasts",
        "profile_url": clean_profile_url(cand.get("collectionViewUrl")),
        "stable_creator_id": cand["key"],
        "followers_or_subscribers": "",
        "feed_url": feed_url,
        "genre": cand.get("primaryGenreName", ""),
        "store_country": cand.get("_store", ""),
        "checked_date": now.date().isoformat(),
    }

    # Real and relevant: an individual creator in an approved segment, not a brand/network
    name, name_basis = creator_identity(cand, ch)
    # judge the publisher by the name part of each field, not by taglines like "founder of X LLC"
    heads = [lead_segment(x) for x in (cand.get("artistName"), ch.get("author"), ch.get("owner_name")) if x]
    if any(EXCLUDE_ENTITY.search(h) for h in heads if not is_person(h)):
        reasons.append("Organisation/network/publication, not an individual creator")
    elif any(re.search(r"\b(iheart\w*|npr|bbc|wondery|audacy|podcastone|sirius\w*|cnn|fox news|abc news|"
                       r"cbs news|nbc news|pbs|msnbc)\b", h, re.I) for h in heads):
        reasons.append("Organisation/network/publication, not an individual creator")
    if cand.get("primaryGenreName") in EXCLUDE_GENRES:
        reasons.append(f"Excluded genre ({cand.get('primaryGenreName')})")
    if not name:
        reasons.append("No identifiable individual creator (possible brand)")
    lead["creator_name"] = name or (cand.get("artistName") or "")
    lead["name_basis"] = name_basis or ""
    show = lead["show_name"] or ""

    # English
    lang = (ch.get("language") or "").lower()
    titles = " ".join(it["title"] for it in items[:10])
    ascii_ratio = sum(c.isascii() for c in titles) / max(1, len(titles))
    if (lang and not lang.startswith("en")) or (not lang and ascii_ratio < 0.97):
        reasons.append(f"Recent content not mainly English (language '{lang or 'missing'}')")
    lead["primary_language"] = "English"

    # Active
    act = S.activity(items, now, q["longform_minutes"])
    lead["content_count_30d"] = act["count_30d"]
    lead["longform_count_60d"] = act["longform_60d"]
    lead["last_content_date"] = act["latest"].date().isoformat() if act["latest"] else ""
    lead["avg_minutes"] = act["avg_minutes"]
    if not (act["count_30d"] >= q["active_items_30d"] or act["longform_60d"] >= q["longform_items_60d"]):
        reasons.append(f"Not active enough ({act['count_30d']} items/30d, {act['longform_60d']} long-form/60d)")
    dated = [it for it in items if it["published"] and S.datetime.fromisoformat(it["published"]) <= now + timedelta(days=2)]
    dated.sort(key=lambda it: it["published"], reverse=True)
    if dated:
        lead["recent_title"] = dated[0]["title"]
        lead["recent_date"] = dated[0]["published"][:10]
        lead["recent_content_url"] = dated[0]["link"] if dated[0]["link"].startswith("http") else lead["profile_url"]
    else:
        lead.update(recent_title="", recent_date="", recent_content_url="")
    if len(dated) > 1:
        lead["second_title"], lead["second_date"] = dated[1]["title"], dated[1]["published"][:10]
    else:
        lead["second_title"], lead["second_date"] = "", ""

    # Website (creator's own domain, not the podcast host's)
    website = ch.get("link") or ""
    wd = S.site_domain(website)
    if any(wd == d or wd.endswith("." + d) for d in S.PLACEHOLDER_EMAIL_DOMAINS | S.PLATFORM_SITES):
        website = ""  # a hosting/link-in-bio/social page shows the platform's address, not the creator's
    lead["website"] = website

    # An author field can hold a brand ("NerdWallet Travel", "Morning Brew") or a character ("Mary Alice"),
    # so a listed author needs a second, independent source naming that person as host.
    if name and name_basis == "listed author" and not name_corroborated(name, ch, show, items,
                                                                         ch.get("owner_email", "")):
        reasons.append("Listed author not confirmed as a person by any second source (possible brand)")

    # Commercial
    own_labels = {re.sub(r"[^a-z]", "", d.split(".")[0]) for d in
                  (S.site_domain(ch.get("link") or ""), S.email_domain(ch.get("owner_email") or "x@"))
                  if d and d not in S.FREE_MAIL and not any(d.endswith(p) for p in S.PLACEHOLDER_EMAIL_DOMAINS)}
    own_labels.discard("")

    def owned(h):
        hl = re.sub(r"[^a-z]", "", (h or "").lower())
        return owns_contact(h, lead["creator_name"], show) or any(len(o) >= 4 and o in hl for o in own_labels)

    money = S.money_signals(ch, items, owner_check=owned)
    lead["monetization_types"] = [m[0] for m in money]
    if money:
        kind, ref, snippet = money[0]
        where = f"episode '{items[ref]['title'][:70]}'" if isinstance(ref, int) else "show description/feed"
        lead["monetization_signal"] = f"{kind}: \"{snippet[:120]}\" ({where})"
        lead["monetization_evidence_url"] = _ref_url(ref, items, feed_url)
    else:
        lead["monetization_signal"] = lead["monetization_evidence_url"] = ""
        reasons.append("No public monetisation evidence")

    # Reachable
    email, email_basis, email_ref = S.find_contact_email(ch, items, website)
    socials = S.find_socials(ch, items)
    # LinkedIn profiles are personal: the handle must carry the creator's name, or it is a guest's
    if "LinkedIn" in socials and not any(t in socials["LinkedIn"]["handle"].lower()
                                         for t in _tokens(lead["creator_name"])):
        del socials["LinkedIn"]
    # other socials must visibly be the show's/creator's, or be linked from the show description itself
    for p in [p for p in socials if p != "LinkedIn"]:
        if not owns_contact(socials[p]["handle"], lead["creator_name"], show):
            del socials[p]  # sponsors and guests get linked often too; only the show's/creator's own handle counts
    lead["socials"] = socials
    if ORG_SHOW.search(show):
        reasons.append("Organisation/network/publication, not an individual creator (show name)")
    if email and AGENCY_DOMAIN.search(S.email_domain(email).split(".")[0]):
        reasons.append(f"Contact belongs to an agency/management firm ({S.email_domain(email)})")
    elif email and S.email_domain(email) not in S.FREE_MAIL and not owns_contact(email, lead["creator_name"], show):
        # a company address unrelated to the creator or show is an employer/producer inbox, not theirs
        lead["unowned_email"] = email
        email, email_basis, email_ref = None, None, None
    lead["email"] = email or ""

    # Needs IncuBrix
    needs = S.need_signals(ch, items, socials, act)
    lead["need_types"] = [n[0] for n in needs]
    # keep the creator's own words separately: the need summary is truncated to 3 items
    stated = next((v for k, v in needs if k == "Stated workflow need"), "")
    lead["need_quote"] = stated.split('notes say "', 1)[-1].rstrip('"') if stated else ""
    if needs:
        lead["incubrix_need"] = "; ".join(f"{k}: {v}" for k, v in needs[:3])
        lead["need_evidence_url"] = feed_url
    else:
        lead["incubrix_need"] = lead["need_evidence_url"] = ""
        reasons.append("No evidence of a content-workflow need")

    # Country
    cc, cc_basis = S.infer_country(ch, website, email, cand.get("_store"), items,
                                   extra_text=" ".join(filter(None, [cand.get("artistName"), ch.get("author")])),
                                   site_info=site_info)
    lead["country_evidence_url"] = site_info["url"] if site_info and cc_basis.startswith("creator's website") \
        else feed_url
    lead["country_iso2"] = cc or "Other"
    lead["country_basis"] = cc_basis
    if cc not in cfg["countries"]["approved"]:
        reasons.append(f"Country not verified as approved market ({cc_basis})")

    # Segment
    expert = bool({"Service (coaching/consulting)", "Course/product"} & set(lead["monetization_types"])) and (
        cand.get("primaryGenreName") in EXPERT_GENRES or set(cand.get("genres", [])) & EXPERT_GENRES)
    lead["creator_segment"] = "Expert-Led Creator" if expert else "Podcaster/Video Podcaster"
    lead["is_video"] = any(it["enclosure_type"].startswith("video") for it in items[:10])

    _pick_channels(lead, email, email_basis, email_ref, socials, items, feed_url, now, q, reasons)

    lead["status"] = "Qualified" if not reasons else "Rejected"
    lead["rejection_reason"] = "; ".join(reasons)
    lead["lead_score"] = score(lead, money, needs, act, email_basis, socials)
    return lead


def _social_fresh(s, items, now, days):
    ref = s.get("newest_item")
    if not isinstance(ref, int) or not items[ref]["published"]:
        return False
    return (now - S.datetime.fromisoformat(items[ref]["published"])).days <= days


def _pick_channels(lead, email, email_basis, email_ref, socials, items, feed_url, now, q, reasons):
    days = q["channel_active_days"]
    pref = SOCIAL_PREF_EXPERT if lead["creator_segment"] == "Expert-Led Creator" else SOCIAL_PREF_DEFAULT
    # Only platforms with direct messages can be a first-touch channel; YouTube is listing-only
    fresh = [p for p in pref if p in socials and p in DM_PLATFORMS and _social_fresh(socials[p], items, now, days)]
    ordered = [p for p in pref if p in socials and p in DM_PLATFORMS]  # a backup must be something we can message
    free_mail = bool(email) and S.email_domain(email) in S.FREE_MAIL

    def social(p):
        s = socials[p]
        return p, s["url"], _ref_url(s["newest_item"], items, feed_url), \
            f"{p} profile the creator linked in episode notes within the last {days} days"

    best = backup = None
    # UK/IE personal mailboxes count as "individual subscribers" under PECR: lead with a social DM there
    if email and not (lead["country_iso2"] in ("GB", "IE") and free_mail and fresh):
        best = ("Email", email, _ref_url(email_ref, items, feed_url), email_basis)
        if ordered:
            backup = social(ordered[0])
    elif fresh:
        best = social(fresh[0])
        if email:
            backup = ("Email", email, _ref_url(email_ref, items, feed_url), email_basis)
        elif len(ordered) > 1:
            backup = social([p for p in ordered if p != fresh[0]][0])
    if best is None:
        reasons.append("No verifiable public business contact channel")
        best = ("", "", "", "")
    if backup is None and lead["website"]:
        backup = ("Contact form", lead["website"], lead["website"], "creator website linked from the feed")
    if backup is None and best[0] == "Email" and lead["creator_segment"] == "Podcaster/Video Podcaster":
        # same verified inbox, different offer: pitch an IncuBrix guest spot on their show
        backup = ("Podcast guest pitch", email, best[2], "guest pitch to the published show contact")
    lead["best_channel"], lead["channel_handle_or_url"], lead["channel_evidence_url"], lead["channel_basis"] = best
    b = backup or ("", "", "", "")
    lead["backup_channel"], lead["backup_handle_or_url"], lead["backup_evidence_url"], lead["backup_basis"] = b
    # Feed freshness is our evidence that the published contact is in current use
    latest = lead["last_content_date"]
    if best[0] == "Email" and latest and (now.date() - S.datetime.fromisoformat(latest).date()).days > days:
        reasons.append(f"Contact channel not shown active in last {days} days")


def score(lead, money, needs, act, email_basis, socials):
    s = min(20, act["count_30d"] * 3 + act["longform_60d"] * 2)
    s += min(25, 9 * len(money))
    s += min(25, 8 * len(needs))
    if lead.get("best_channel") == "Email":
        s += 15 if email_basis and "business" in email_basis else 9
    elif lead.get("best_channel"):
        s += 10
    s += min(10, 4 * len(socials))
    if lead.get("is_video"):
        s += 5
    return min(100, int(s))
