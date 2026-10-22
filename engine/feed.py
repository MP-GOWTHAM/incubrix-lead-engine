"""Streaming RSS parser: reads channel metadata plus the newest N items, then stops."""

import html
import re
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

from . import net

NS = {
    "itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "podcast": "https://podcastindex.org/namespace/1.0",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "atom": "http://www.w3.org/2005/Atom",
}
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_text(s):
    if not s:
        return ""
    s = html.unescape(_TAG.sub(" ", s))
    return _WS.sub(" ", s).strip()


def raw_links(s):
    """hrefs survive tag stripping only if we pull them out first."""
    return re.findall(r'href=["\']([^"\']+)["\']', s or "", re.I)


def parse_date(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s.strip())
    except (TypeError, ValueError, IndexError):
        return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


_TZ_NAMES = {"EST": -300, "EDT": -240, "CST": -360, "CDT": -300, "MST": -420, "MDT": -360,
             "PST": -480, "PDT": -420, "AEST": 600, "AEDT": 660, "BST": 60}


def tz_offset_minutes(s):
    """Offset as written in the pubDate (before UTC conversion); None for GMT/UTC/missing."""
    m = re.search(r"([+-])(\d{2}):?(\d{2})\s*$", (s or "").strip())
    if m:
        v = int(m.group(2)) * 60 + int(m.group(3))
        v = -v if m.group(1) == "-" else v
        return v or None
    m = re.search(r"\b([A-Z]{3,4})\s*$", (s or "").strip())
    return _TZ_NAMES.get(m.group(1)) if m else None


def parse_duration(s):
    """itunes:duration -> seconds. Accepts 'HH:MM:SS', 'MM:SS' or raw seconds."""
    if not s:
        return None
    s = s.strip()
    try:
        if ":" in s:
            parts = [float(p) for p in s.split(":")]
            secs = 0.0
            for p in parts:
                secs = secs * 60 + p
            return int(secs)
        return int(float(s))
    except ValueError:
        return None


def _local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _ns(tag):
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def parse_stream(fp, max_items=30):
    """Parse an RSS byte stream. Returns a dict, or raises ET.ParseError."""
    channel = {"title": "", "description": "", "link": "", "language": "", "author": "",
               "owner_name": "", "owner_email": "", "managing_editor": "", "categories": [],
               "location": "", "has_podcast_ns_funding": False, "funding_urls": [], "links": []}
    items = []
    stack = []
    try:
        _walk(ET.iterparse(fp, events=("start", "end")), channel, items, stack, max_items)
    except ET.ParseError:
        # A feed cut off by the size cap (or broken late) is still usable if items were read.
        if not items:
            raise
    return {"channel": channel, "items": items}


def _walk(it, channel, items, stack, max_items):
    depth_item = 0
    for event, el in it:
        tag = el.tag
        if event == "start":
            stack.append(tag)
            if _local(tag) == "item":
                depth_item += 1
            continue
        stack.pop()
        name, ns = _local(tag), _ns(tag)
        if name == "item":
            depth_item -= 1
            items.append(_item(el))
            el.clear()
            if len(items) >= max_items:
                return
            continue
        if depth_item:
            continue
        parent = _local(stack[-1]) if stack else ""
        text = (el.text or "").strip()
        if parent == "channel":
            if name == "title" and not ns:
                channel["title"] = clean_text(text)
            elif name == "description" and not ns:
                channel["links"] += raw_links(text)
                channel["description"] = clean_text(text)
            elif name == "summary" and ns == NS["itunes"] and not channel["description"]:
                channel["description"] = clean_text(text)
            elif name == "link" and not ns:
                channel["link"] = text
            elif name == "language":
                channel["language"] = text.lower()
            elif name == "author" and ns == NS["itunes"]:
                channel["author"] = clean_text(text)
            elif name == "managingEditor":
                channel["managing_editor"] = text
            elif name == "category" and ns == NS["itunes"]:
                if el.get("text"):
                    channel["categories"].append(el.get("text"))
            elif name == "location" and ns == NS["podcast"]:
                channel["location"] = clean_text(text)
            elif name == "person" and ns == NS["podcast"]:
                if (el.get("role") or "host").lower() == "host" and text:
                    channel.setdefault("hosts", []).append(clean_text(text))
            elif name == "funding" and ns == NS["podcast"]:
                channel["has_podcast_ns_funding"] = True
                if el.get("url"):
                    channel["funding_urls"].append(el.get("url"))
        elif parent == "owner" and ns == NS["itunes"]:
            if name == "name":
                channel["owner_name"] = clean_text(text)
            elif name == "email":
                channel["owner_email"] = text.strip()
        elif parent == "category" and name == "category" and el.get("text"):
            channel["categories"].append(el.get("text"))


def _item(el):
    def find(path):
        x = el.find(path, NS)
        return x.text if x is not None and x.text else ""

    desc_raw = find("content:encoded") or find("description") or find("itunes:summary")
    enc = el.find("enclosure")
    enclosure_type = enc.get("type", "") if enc is not None else ""
    raw_pub = find("pubDate")
    pub = parse_date(raw_pub)
    return {
        "title": clean_text(find("title")),
        "link": find("link").strip(),
        "guid": find("guid").strip(),
        "published": pub.isoformat() if pub else None,
        "tz_offset_min": tz_offset_minutes(raw_pub),
        "duration_sec": parse_duration(find("itunes:duration")),
        "enclosure_type": enclosure_type,
        "has_transcript": el.find("podcast:transcript", NS) is not None,
        "has_chapters": el.find("podcast:chapters", NS) is not None,
        "description": clean_text(desc_raw)[:4000],
        "links": raw_links(desc_raw)[:60],
        "episode_type": find("itunes:episodeType"),
    }


def fetch_feed(url, max_items=30, limiter=None):
    try:
        with net.open_url(url, timeout=25, limiter=limiter) as resp:
            return parse_stream(net.CappedReader(resp), max_items=max_items)
    except ET.ParseError as e:
        raise net.FetchError(f"Bad XML in {url}: {e}") from e
