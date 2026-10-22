"""Build a small seed file of shows the engine has never seen (for the refresh / recovery demos).

    python scripts/make_demo_seed.py demo/new_input.txt "beekeeping" "chess" "sailing"
"""

import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    out, terms = sys.argv[1], sys.argv[2:]
    db = sqlite3.connect(os.path.join(ROOT, "data", "state.sqlite"))
    known = {r[0] for r in db.execute("SELECT key FROM candidates")}
    picked = []
    for t in terms:
        url = "https://itunes.apple.com/search?" + urllib.parse.urlencode(
            {"term": t, "media": "podcast", "entity": "podcast", "country": "gb", "limit": 50})
        with urllib.request.urlopen(url, timeout=20) as r:
            res = json.load(r)["results"]
        recent = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        new = [x for x in res if f"apple_podcasts:{x['collectionId']}" not in known and x.get("feedUrl")
               and (x.get("releaseDate") or "") >= recent[:10]]
        picked += [x["collectionViewUrl"].split("?")[0] for x in new[:6]]
    os.makedirs(os.path.dirname(os.path.join(ROOT, out)), exist_ok=True)
    with open(os.path.join(ROOT, out), "w", encoding="utf-8") as f:
        f.write("# New input for the refresh demo: Apple Podcasts URLs not yet in the database\n")
        f.write("\n".join(picked) + "\n")
    print(f"{len(picked)} new shows -> {out}")


if __name__ == "__main__":
    main()
