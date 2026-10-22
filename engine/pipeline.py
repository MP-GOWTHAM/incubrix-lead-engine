"""find -> check -> dedupe -> score -> pick channel -> draft -> export, resumable and refreshable."""

import logging
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from . import export, feed, messages, net, qualify, signals, sources
from .store import Store

log = logging.getLogger("engine")
SITE_CHECK_VERSION = 5  # bump when website_country() changes so cached sites are re-read


class SimulatedFailure(RuntimeError):
    pass


def _host(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


class Pipeline:
    def __init__(self, cfg, paths, now=None, fetch_feed=None, search=None):
        self.cfg, self.paths = cfg, paths
        self.now = now or datetime.now(timezone.utc)
        self.store = Store(paths["db"])
        if paths.get("registry"):
            self.store.load_registry(paths["registry"])
        self.cache = net.JsonCache(paths["cache"])
        self.apple_limiter = net.RateLimiter(cfg["apple"]["min_interval_sec"])
        self.host_limiters = defaultdict(lambda: net.RateLimiter(cfg["run"]["per_host_interval_sec"]))
        self._fetch_feed = fetch_feed or self._default_fetch
        self._search = search or (lambda term, store: sources.apple_search(term, store, cfg, self.cache,
                                                                           self.apple_limiter))
        self.stats = Counter()
        self.errors = []

    # ------------------------------------------------------------------ discovery
    def _prefilter(self, c):
        if c.get("primaryGenreName") in qualify.EXCLUDE_GENRES:
            return False
        if c.get("releaseDate") and not sources.recent_enough(c, self.now, self.cfg["qualify"]["channel_active_days"]):
            return False
        return True

    def discover(self, terms=None, stores=None):
        terms = terms or (self.cfg["apple"]["terms"] + self.cfg["apple"].get("local_terms", []))
        stores = stores or self.cfg["apple"]["stores"]
        now_iso = self.now.isoformat()
        for term in terms:
            for st in stores:
                try:
                    hits, cached = self._search(term, st)
                except net.FetchError as e:
                    self._error("search", f"{term}/{st}", str(e))
                    continue
                self.stats["searches"] += 1
                self.stats["searches_cached"] += int(cached)
                self.stats["input_size"] += len(hits)
                for c in hits:
                    if not self._prefilter(c):
                        self.stats["prefiltered_out"] += 1
                        continue
                    if self.store.upsert_candidate(c, now_iso):
                        self.stats["new_candidates"] += 1
                    else:
                        self.stats["duplicates_removed"] += 1
            self.store.commit()
            log.info("search '%s' done: %d candidates so far", term, self.store.candidate_count())
        self.discover_charts()

    def discover_charts(self):
        """Top charts per country and genre: the richest public source of non-US independent shows."""
        a = self.cfg["apple"]
        for st in a.get("chart_stores", []):
            for g in a.get("chart_genres", []):
                try:
                    hits, cached = self._chart(st, g)
                except (net.FetchError, KeyError, ValueError) as e:
                    self._error("chart", f"{st}/{g}", str(e))
                    continue
                self.stats["input_size"] += len(hits)
                for c in hits:
                    if not self._prefilter(c):
                        self.stats["prefiltered_out"] += 1
                    elif self.store.upsert_candidate(c, self.now.isoformat()):
                        self.stats["new_candidates"] += 1
                    else:
                        self.stats["duplicates_removed"] += 1
            self.store.commit()
            log.info("charts '%s' done: %d candidates so far", st, self.store.candidate_count())

    def _chart(self, store, genre):
        return sources.apple_chart(store, genre, self.cache, self.apple_limiter)

    def add_seed(self, path):
        entries = sources.read_seed(path)
        self.stats["input_size"] += len(entries)
        cands, failed = sources.resolve_seed(entries, self.cfg, self.cache, self.apple_limiter, self.now)
        for e, why in failed:
            self._error("seed", e, why)
        keys = []
        for c in cands:
            if self.store.upsert_candidate(c, self.now.isoformat()):
                self.stats["new_candidates"] += 1
            else:
                self.stats["duplicates_removed"] += 1
            keys.append(c["key"])
        self.store.commit()
        log.info("seed %s: %d entries -> %d candidates, %d unresolved", path, len(entries), len(cands), len(failed))
        return keys

    # ------------------------------------------------------------------ feeds
    def _default_fetch(self, url):
        return feed.fetch_feed(url, max_items=self.cfg["run"]["items_per_feed"], limiter=self.host_limiters[_host(url)])

    def _feed_fresh(self, url):
        f = self.store.feed(url)
        return f and f["status"] == "ok" and time.time() - f["fetched_at"] < self.cfg["run"]["feed_ttl_hours"] * 3600

    def fetch_feeds(self, cands, fail_after=None, force=False):
        todo = [c for c in cands if force or not self._feed_fresh(c["feedUrl"])]
        todo = todo[: self.cfg["run"]["max_feeds_per_run"]]
        self.stats["feeds_cached"] += len(cands) - len(todo)
        log.info("fetching %d feeds (%d already fresh in cache)", len(todo), len(cands) - len(todo))
        done = 0
        with ThreadPoolExecutor(max_workers=self.cfg["run"]["workers"]) as pool:
            futs = {pool.submit(self._fetch_feed, c["feedUrl"]): c for c in todo}
            for fut in as_completed(futs):
                c = futs[fut]
                try:
                    data = fut.result()
                    self.store.put_feed(c["feedUrl"], "ok", data)
                    self.stats["feeds_fetched"] += 1
                except Exception as e:  # one bad feed must never stop the run
                    self.store.put_feed(c["feedUrl"], "error", error=str(e)[:300])
                    self._error("feed", c["feedUrl"], str(e)[:300])
                    self.stats["feed_errors"] += 1
                done += 1
                if done % 100 == 0:
                    self.store.commit()
                    log.info("feeds: %d/%d", done, len(todo))
                if fail_after and done >= fail_after:
                    self.store.commit()
                    for f in futs:
                        f.cancel()
                    raise SimulatedFailure(f"simulated crash after {done} feeds (rerun to recover)")
        self.store.commit()

    # ------------------------------------------------------------------ evaluate
    def evaluate(self, cands):
        now_iso = self.now.isoformat()
        for c in cands:
            f = self.store.feed(c["feedUrl"])
            if not f:
                continue
            if f["status"] != "ok":
                lead = {"key": c["key"], "status": "Rejected", "show_name": c.get("collectionName", ""),
                        "rejection_reason": f"Feed unavailable: {f['error']}", "profile_url": c.get("collectionViewUrl")}
            else:
                try:
                    lead = qualify.evaluate(c, f["data"], self.now, self.cfg)
                except Exception as e:
                    self._error("evaluate", c["key"], repr(e))
                    continue
            self.store.put_lead(lead, now_iso)
        self.store.commit()

    def _get_html(self, url):
        with net.open_url(url, timeout=20, retries=2, limiter=self.host_limiters[_host(url)]) as resp:
            if "html" not in resp.headers.get("Content-Type", "").lower():
                return ""
            return net.CappedReader(resp, cap=1_500_000).read().decode("utf-8", "replace")

    def _fetch_site(self, url):
        """Homepage first, then up to two same-site Contact/About pages it links to."""
        html = self._get_html(url)
        cc, snip = signals.website_country(html)
        if cc:
            return {"country": cc, "snippet": snip, "url": url}
        host = _host(url)
        seen = set()
        for href in re.findall(r'href=["\']([^"\'#]+)["\']', html, re.I):
            full = urljoin(url, href)
            if _host(full) != host or full in seen or not re.search(r"/(contact|about)", full, re.I) \
                    or re.search(r"trust-center|report|privacy|terms|policies/(privacy|terms)", full, re.I):
                continue
            seen.add(full)
            try:
                sub = self._get_html(full)
            except Exception:
                continue
            cc, snip = signals.website_country(sub)
            if cc:
                return {"country": cc, "snippet": snip, "url": full}
            if len(seen) >= 2:
                break
        return {"country": None, "snippet": snip, "url": url}

    def enrich_country(self, cands):
        """For creators failing only the country check, look for a postal address/registration/phone
        on their own website. One cached GET per site; nothing is inferred without a quoted snippet."""
        byk = {c["key"]: c for c in cands}
        targets = []
        for l in self.store.leads():
            rs = [r for r in (l.get("rejection_reason") or "").split("; ") if r]
            if len(rs) == 1 and rs[0].startswith("Country not verified") and l.get("website", "").startswith("http") \
                    and l["key"] in byk and "conflicting" not in rs[0]:
                targets.append((byk[l["key"]], l["website"]))
        todo = []
        for c, url in targets:
            f = self.store.feed("site:" + url)
            fresh = f and time.time() - f["fetched_at"] < self.cfg["run"]["feed_ttl_hours"] * 3600 * 4
            current = f and f["status"] == "ok" and f["data"].get("v") == SITE_CHECK_VERSION
            if not (fresh and (current or f["status"] != "ok")):
                todo.append(url)
        todo = sorted(set(todo))
        log.info("country enrichment: %d creators fail only on country; fetching %d websites", len(targets), len(todo))
        with ThreadPoolExecutor(max_workers=self.cfg["run"]["workers"]) as pool:
            futs = {pool.submit(self._fetch_site, u): u for u in todo}
            for fut in as_completed(futs):
                u = futs[fut]
                try:
                    self.store.put_feed("site:" + u, "ok", dict(fut.result(), v=SITE_CHECK_VERSION))
                except Exception as e:
                    self.store.put_feed("site:" + u, "error", error=str(e)[:300])
                    self.stats["site_errors"] += 1
        self.store.commit()
        now_iso = self.now.isoformat()
        found = 0
        for c, url in targets:
            s = self.store.feed("site:" + url)
            if not s or s["status"] != "ok" or not s["data"].get("country"):
                continue
            f = self.store.feed(c["feedUrl"])
            lead = qualify.evaluate(c, f["data"], self.now, self.cfg, site_info=s["data"])
            self.store.put_lead(lead, now_iso)
            found += lead["status"] == "Qualified"
        self.store.commit()
        self.stats["country_from_website"] = found
        log.info("country enrichment: %d creators verified via their website", found)

    # ------------------------------------------------------------------ post-processing
    def dedupe_creators(self, leads):
        """Same person behind several shows (or the same show listed twice) -> keep the best one."""
        q = [l for l in leads if l["status"] == "Qualified"]
        parent = {l["key"]: l["key"] for l in q}

        def find(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k

        index = defaultdict(list)
        for l in q:
            keys = {"feed:" + re.sub(r"^https?://(www\.)?", "", l["feed_url"]).rstrip("/").lower()}
            if l.get("email"):
                keys.add("email:" + l["email"].lower())
            if l.get("creator_name"):
                keys.add("name:" + re.sub(r"[^a-z]", "", l["creator_name"].lower()))
            for s in (l.get("socials") or {}).values():
                keys.add("social:" + s["url"].lower())
            for k in keys:
                index[k].append(l["key"])
        for ks in index.values():
            for k in ks[1:]:
                a, b = find(ks[0]), find(k)
                if a != b:
                    parent[b] = a
        groups = defaultdict(list)
        for l in q:
            groups[find(l["key"])].append(l)
        removed = 0
        for g in groups.values():
            if len(g) == 1:
                continue
            g.sort(key=lambda l: (bool(l.get("lead_id")), l["lead_score"]), reverse=True)
            keep = g[0]
            for l in g[1:]:
                l["status"] = "Rejected"
                l["rejection_reason"] = f"Duplicate creator: same person/contact as {keep['key']} ({keep['show_name']})"
                removed += 1
        self.stats["creator_duplicates_removed"] += removed
        return leads

    def balance_countries(self, leads):
        """No country may exceed the configured share; surplus lowest-scoring leads go to reserve."""
        share = self.cfg["countries"]["max_share"]
        q = [l for l in leads if l["status"] == "Qualified"]
        while q:
            counts = Counter(l["country_iso2"] for l in q)
            top, n = counts.most_common(1)[0]
            total = len(q)
            if n / total <= share or len(counts) < 2:
                break
            allowed = int(share / (1 - share) * (total - n))
            pool = sorted((l for l in q if l["country_iso2"] == top), key=lambda l: l["lead_score"])
            for l in pool[: n - allowed]:
                l["status"] = "Reserve"
                l["rejection_reason"] = f"Held in reserve: {top} would exceed {int(share * 100)}% country cap"
            q = [l for l in q if l["status"] == "Qualified"]
        self.stats["reserve_country_cap"] = sum(1 for l in leads if l["status"] == "Reserve")
        return leads

    def prioritise(self, leads):
        q = sorted((l for l in leads if l["status"] == "Qualified"), key=lambda l: -l["lead_score"])
        a_target = self.cfg["priority"]["a_count"]
        b_n = int(len(q) * self.cfg["priority"]["b_share"])
        a = 0
        rest = []
        for l in q:
            ready = l.get("second_title") and l["best_channel"] in ("Email", "LinkedIn", "Instagram", "X", "TikTok")
            if a < a_target and ready:
                l["priority"] = "A"
                a += 1
            else:
                rest.append(l)
        for i, l in enumerate(rest):
            l["priority"] = "B" if i < b_n else "C"
        return leads

    def finalise(self, leads):
        q = [l for l in leads if l["status"] == "Qualified"]
        q.sort(key=lambda l: (l.get("lead_id") or "~", l["key"]))
        for l in q:
            l["lead_id"] = self.store.assign_lead_id(l["key"])
            l["first_name"] = qualify.first_name(l["creator_name"])
            l["personalization_hook"] = (f'Latest episode "{messages.short(l["recent_title"], 90)}" '
                                         f'({l["recent_date"]}); {l["need_types"][0] if l["need_types"] else ""}'
                                         .strip("; "))
            l["first_message"] = messages.first_message(l, self.cfg)
            l["sequence"] = messages.sequence(l, self.cfg)
        now_iso = self.now.isoformat()
        for l in leads:
            self.store.put_lead(l, now_iso)
        self.store.commit()
        if self.paths.get("registry"):
            self.store.write_registry(self.paths["registry"])
        return leads

    # ------------------------------------------------------------------ orchestration
    def run(self, discover=True, seed=None, fail_after=None, force_refetch=False, only_seed=False):
        t0 = time.time()
        self.stats["t0"] = t0
        seed_keys = []
        if discover and not only_seed:
            self.discover()
        if seed:
            seed_keys = self.add_seed(seed)
        cands = self.store.candidates()
        if only_seed:
            cands = [c for c in cands if c["key"] in set(seed_keys)]
        self.fetch_feeds(cands, fail_after=fail_after, force=force_refetch)
        self.evaluate(cands)
        self.enrich_country(cands)
        leads = self.store.leads()
        # reserve/held leads get re-tested each run, so reset before re-balancing
        for l in leads:
            if l["status"] == "Reserve":
                l["status"], l["rejection_reason"] = "Qualified", ""
            if l["status"] == "Rejected" and l.get("rejection_reason", "").startswith("Duplicate creator"):
                l["status"], l["rejection_reason"] = "Qualified", ""
        leads = self.dedupe_creators(leads)
        leads = self.balance_countries(leads)
        leads = self.prioritise(leads)
        leads = self.finalise(leads)
        runtime = time.time() - t0
        report = export.write_all(leads, self.stats, self.errors, runtime, self.cfg, self.paths, self.now,
                                  seed_keys=seed_keys)
        self.store.close()
        return report

    def _error(self, stage, item, msg):
        log.warning("%s error for %s: %s", stage, item, msg)
        self.errors.append({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "stage": stage, "item": item, "error": msg})
