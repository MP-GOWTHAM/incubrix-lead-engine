"""HTTP access: polite rate limiting, retries with backoff, size caps, a JSON cache."""

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("engine.net")

USER_AGENT = "IncuBrix-LeadEngine/1.0 (public-API research crawler; respects rate limits)"
MAX_BYTES = 6 * 1024 * 1024


class FetchError(Exception):
    pass


class RateLimiter:
    """Spaces calls to one host at least `interval` seconds apart (thread-safe)."""

    def __init__(self, interval):
        self.interval = interval
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval
        if delay > 0:
            time.sleep(delay)


class CappedReader:
    """File-like wrapper that refuses to read past MAX_BYTES (guards against huge feeds)."""

    def __init__(self, raw, cap=MAX_BYTES):
        self.raw, self.cap, self.read_bytes = raw, cap, 0

    def read(self, n=-1):
        if self.read_bytes >= self.cap:
            return b""
        if n is None or n < 0 or n > self.cap - self.read_bytes:
            n = self.cap - self.read_bytes
        chunk = self.raw.read(n)
        self.read_bytes += len(chunk)
        return chunk


def open_url(url, timeout=20, retries=3, limiter=None):
    """Open a URL and return the response object. Retries 429/5xx/network errors."""
    last = None
    for attempt in range(retries):
        if limiter:
            limiter.wait()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt * (5 if e.code == 429 else 1))
                continue
            raise FetchError(f"HTTP {e.code} for {url}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            time.sleep(2 ** attempt)
    raise FetchError(f"Gave up on {url}: {last}")


class JsonCache:
    """Disk cache for JSON API responses, keyed by URL, with a TTL."""

    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def _path(self, url):
        return os.path.join(self.root, hashlib.sha1(url.encode()).hexdigest() + ".json")

    def get(self, url, ttl_sec):
        p = self._path(url)
        if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl_sec:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return None

    def put(self, url, data):
        tmp = self._path(url) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self._path(url))


def get_json(url, cache=None, ttl_sec=0, limiter=None, timeout=20):
    if cache and ttl_sec:
        hit = cache.get(url, ttl_sec)
        if hit is not None:
            return hit, True
    with open_url(url, timeout=timeout, limiter=limiter) as resp:
        data = json.loads(CappedReader(resp).read().decode("utf-8", "replace"))
    if cache:
        cache.put(url, data)
    return data, False


def with_query(base, **params):
    return base + "?" + urllib.parse.urlencode(params)
