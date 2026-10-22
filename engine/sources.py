"""Discovery sources. Apple Podcasts Search/Lookup API is public and key-free; seed files let anyone
feed in their own list (Apple URLs, RSS feed URLs or show names)."""

import csv
import logging
import re
from datetime import datetime, timedelta, timezone

from . import net

log = logging.getLogger("engine.sources")
SEARCH = "https://itunes.apple.com/search"
LOOKUP = "https://itunes.apple.com/lookup"
APPLE_ID = re.compile(r"podcasts\.apple\.com/.*/id(\d+)|^id?(\d{6,12})$")


def _norm(r, store, term):
    if r.get("kind") != "podcast" or not r.get("feedUrl") or not r.get("collectionId"):
        return None
    out = {k: r.get(k) for k in ("collectionId", "artistName", "collectionName", "collectionViewUrl", "feedUrl",
                                 "primaryGenreName", "genres", "releaseDate", "trackCount", "country")}
    out["key"] = f"apple_podcasts:{r['collectionId']}"
    out["_store"] = store
    out["_term"] = term
    return out


def apple_search(term, store, cfg, cache, limiter):
    url = net.with_query(SEARCH, term=term, media="podcast", entity="podcast", country=store,
                         limit=cfg["apple"]["limit"])
    data, cached = net.get_json(url, cache=cache, ttl_sec=cfg["apple"]["cache_days"] * 86400, limiter=limiter)
    return [c for c in (_norm(r, store, term) for r in data.get("results", [])) if c], cached


def apple_lookup(ids, cache, limiter, store="us"):
    out = []
    for i in range(0, len(ids), 150):
        url = net.with_query(LOOKUP, id=",".join(map(str, ids[i:i + 150])), entity="podcast", country=store)
        data, _ = net.get_json(url, cache=cache, ttl_sec=86400, limiter=limiter)
        out += [c for c in (_norm(r, store, "seed") for r in data.get("results", [])) if c]
    return out


def apple_chart(store, genre, cache, limiter):
    """Apple's public top-podcast chart for one store+genre (200 shows), resolved via Lookup for feed URLs."""
    url = f"https://itunes.apple.com/{store}/rss/toppodcasts/limit=200/genre={genre}/json"
    data, cached = net.get_json(url, cache=cache, ttl_sec=86400, limiter=limiter)
    entries = data.get("feed", {}).get("entry", []) or []
    if isinstance(entries, dict):
        entries = [entries]
    ids = [int(e["id"]["attributes"]["im:id"]) for e in entries if e.get("id", {}).get("attributes", {}).get("im:id")]
    cands = apple_lookup(ids, cache, limiter, store=store) if ids else []
    for c in cands:
        c["_term"] = f"chart:{store}:{genre}"
    return cands, cached


def recent_enough(cand, now, max_age_days):
    try:
        d = datetime.fromisoformat(cand["releaseDate"].replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    return now - d <= timedelta(days=max_age_days)


def read_seed(path):
    """Seed file: .txt (one entry per line) or .csv (first column, or a column named url/name)."""
    rows = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        if path.lower().endswith(".csv"):
            r = csv.DictReader(f)
            col = next((c for c in (r.fieldnames or []) if c.lower() in ("url", "profile_url", "feed_url", "name",
                                                                       "creator", "show")), None)
            for row in r:
                v = (row.get(col) if col else next(iter(row.values()), "")) or ""
                if v.strip():
                    rows.append(v.strip())
        else:
            rows = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    return rows


def resolve_seed(entries, cfg, cache, limiter, now):
    """Turn seed entries into candidates. Unresolvable entries come back as (entry, reason)."""
    cands, failed, ids = [], [], []
    for e in entries:
        m = APPLE_ID.search(e)
        if m:
            ids.append(int(m.group(1) or m.group(2)))
        elif e.startswith("http") and not re.search(r"apple\.com|spotify\.com|youtube\.com", e):
            # treat as RSS feed URL; key on the feed until Apple metadata is known
            key = "rss:" + re.sub(r"^https?://", "", e).rstrip("/").lower()
            cands.append({"key": key, "feedUrl": e, "collectionName": "", "artistName": "",
                          "collectionViewUrl": e, "primaryGenreName": "", "genres": [], "releaseDate": None,
                          "trackCount": None, "_store": "", "_term": "seed"})
        elif e.startswith("http"):
            failed.append((e, "Unsupported URL (use an Apple Podcasts or RSS URL; Spotify/YouTube need an API key)"))
        else:
            try:
                hits, _ = apple_search(e, "us", cfg, cache, limiter)
            except net.FetchError as ex:
                failed.append((e, f"search failed: {ex}"))
                continue
            exact = [h for h in hits if (h["collectionName"] or "").lower() == e.lower()
                     or (h["artistName"] or "").lower() == e.lower()]
            if exact or hits:
                cands.append(dict((exact or hits)[0], _term="seed"))
            else:
                failed.append((e, "No Apple Podcasts match"))
    if ids:
        found = apple_lookup(ids, cache, limiter)
        got = {c["collectionId"] for c in found}
        cands += found
        failed += [(str(i), "Apple ID not found") for i in ids if i not in got]
    return cands, failed
