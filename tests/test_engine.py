"""Offline tests: no network. Run with  python -m unittest discover -s tests -v"""

import copy
import csv
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import export, feed, messages, qualify, signals  # noqa: E402
from engine.pipeline import Pipeline, SimulatedFailure  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "sample_feed.xml")
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
with open(os.path.join(ROOT, "config.json"), encoding="utf-8-sig") as f:
    CFG = json.load(f)


def parsed_fixture():
    with open(FIXTURE, "rb") as f:
        return feed.parse_stream(f)


def cand(i=1, name="Jane Tester | Business Coach for Creatives", feed_url="https://feeds.example/jane"):
    return {"key": f"apple_podcasts:{1000 + i}", "collectionId": 1000 + i, "artistName": name,
            "collectionName": f"The Test Coach Show {i}", "feedUrl": feed_url,
            "collectionViewUrl": f"https://podcasts.apple.com/gb/podcast/x/id{1000 + i}?uo=4",
            "primaryGenreName": "Careers", "genres": ["Careers", "Podcasts", "Business"],
            "releaseDate": "2026-10-12T06:00:00Z", "trackCount": 3, "_store": "gb", "_term": "t"}


class FeedParsing(unittest.TestCase):
    def test_channel_and_items(self):
        p = parsed_fixture()
        self.assertEqual(p["channel"]["language"], "en-gb")
        self.assertEqual(p["channel"]["owner_email"], "owner@janetest.co.uk")
        self.assertEqual(len(p["items"]), 3)
        self.assertEqual(p["items"][0]["duration_sec"], 42 * 60 + 10)
        self.assertEqual(p["items"][1]["duration_sec"], 2400)
        self.assertEqual(p["items"][0]["tz_offset_min"], 60)

    def test_max_items_stops_early(self):
        with open(FIXTURE, "rb") as f:
            self.assertEqual(len(feed.parse_stream(f, max_items=2)["items"]), 2)

    def test_truncated_feed_keeps_items(self):
        with open(FIXTURE, "rb") as f:
            data = f.read()
        cut = data[: data.index(b"<title>Why consistency")]
        import io
        p = feed.parse_stream(io.BytesIO(cut))
        self.assertEqual(len(p["items"]), 2)


class Signals(unittest.TestCase):
    def setUp(self):
        self.p = parsed_fixture()

    def test_business_email_beats_owner_and_guest(self):
        e, basis, _ = signals.find_contact_email(self.p["channel"], self.p["items"], "https://janetest.co.uk")
        self.assertEqual(e, "hello@janetest.co.uk")
        self.assertIn("business", basis)

    def test_guest_email_never_used(self):
        ch = dict(self.p["channel"], description="", owner_email="")
        e, _, _ = signals.find_contact_email(ch, self.p["items"], "")
        self.assertNotEqual(e, "sam@guestmail.com")
        self.assertIsNone(e)

    def test_placeholder_emails_rejected(self):
        self.assertIsNone(signals.usable_email("podcasts12345@anchor.fm"))
        self.assertIsNone(signals.usable_email("noreply@janetest.co.uk"))
        self.assertEqual(signals.usable_email("Hello@JaneTest.co.uk"), "hello@janetest.co.uk")

    def test_socials_need_repeat_mentions(self):
        s = signals.find_socials(self.p["channel"], self.p["items"])
        self.assertEqual(s["Instagram"]["handle"], "janetester")
        self.assertEqual(s["Instagram"]["newest_item"], 0)

    def test_money_signals(self):
        kinds = [m[0] for m in signals.money_signals(self.p["channel"], self.p["items"])]
        self.assertIn("Sponsorship", kinds)
        self.assertIn("Service (coaching/consulting)", kinds)

    def test_activity_counts(self):
        a = signals.activity(self.p["items"], NOW, 20)
        self.assertEqual(a["count_30d"], 3)
        self.assertEqual(a["longform_60d"], 3)
        self.assertEqual(a["median_gap_days"], 7)

    def test_country_from_domain(self):
        cc, basis = signals.infer_country(self.p["channel"], "https://janetest.co.uk", "hello@janetest.co.uk",
                                          "gb", self.p["items"])
        self.assertEqual(cc, "GB")

    def test_country_unknown_is_not_guessed(self):
        ch = {"language": "en", "description": "A show about marketing.", "title": "M"}
        cc, _ = signals.infer_country(ch, "", "a@gmail.com", "us", [])
        self.assertIsNone(cc)

    def test_country_from_timezone(self):
        items = [{"tz_offset_min": -300, "description": ""}] * 5
        cc, basis = signals.infer_country({"language": "en", "description": ""}, "", "a@gmail.com", "us", items)
        self.assertEqual(cc, "US")
        cc, _ = signals.infer_country({"language": "en", "description": "Toronto's best show"}, "", "", "us", items)
        self.assertEqual(cc, "CA")


class Qualification(unittest.TestCase):
    def test_qualified_lead_has_all_fields(self):
        lead = qualify.evaluate(cand(), parsed_fixture(), NOW, CFG)
        self.assertEqual(lead["status"], "Qualified", lead["rejection_reason"])
        self.assertEqual(lead["creator_name"], "Jane Tester")
        self.assertEqual(lead["country_iso2"], "GB")
        self.assertEqual(lead["creator_segment"], "Expert-Led Creator")
        self.assertEqual(lead["best_channel"], "Email")
        self.assertEqual(lead["backup_channel"], "Instagram")
        self.assertEqual(lead["profile_url"], "https://podcasts.apple.com/gb/podcast/x/id1001")

    def test_network_rejected(self):
        lead = qualify.evaluate(cand(name="Big Audio Network"), parsed_fixture(), NOW, CFG)
        self.assertEqual(lead["status"], "Rejected")
        self.assertIn("Organisation", lead["rejection_reason"])

    def test_inactive_rejected(self):
        later = datetime(2027, 3, 1, tzinfo=timezone.utc)
        lead = qualify.evaluate(cand(), parsed_fixture(), later, CFG)
        self.assertIn("Not active enough", lead["rejection_reason"])

    def test_audit_regressions(self):
        # "New England" is not England; UTC-0300 is not US
        cc, _ = signals.infer_country({"language": "en", "description": "Legends of New England"}, "", "", "us", [])
        self.assertIsNone(cc)
        items = [{"tz_offset_min": -180, "description": ""}] * 5
        cc, _ = signals.infer_country({"language": "en", "description": ""}, "", "", "us", items)
        self.assertIsNone(cc)
        # en-us alone is a host default
        cc, _ = signals.infer_country({"language": "en-us", "description": "A show."}, "", "a@gmail.com", "us", [])
        self.assertIsNone(cc)
        # topic words are not offers
        ch = {"description": "", "links": []}
        guest = [{"description": "Ben has spent decades coaching elite athletes. European Commission guidance.",
                  "links": [], "title": "x"}]
        self.assertEqual(signals.money_signals(ch, guest), [])
        # a company inbox unrelated to the show is not the creator's
        self.assertFalse(qualify.owns_contact("rmones@jbrec.com", "Dean Wehrli", "New Home Insights"))
        self.assertTrue(qualify.owns_contact("esg@esgfitness.co.uk", "Emma Storey-Gordon", "ESGfitness"))
        self.assertTrue(qualify.owns_contact("hello@missta.com.au", "Demi Duncan", "Missta Mums"))
        self.assertFalse(qualify.is_person("Women's Health Melbourne"))
        self.assertFalse(qualify.is_person("Sales Copywriting and Content Marketing Hacks"))

    def test_guest_money_links_ignored(self):
        ch = {"description": "", "links": []}
        items = [{"description": "Guest bio. https://www.patreon.com/thecreativepenn https://calendly.com/someguest/call",
                  "links": [], "title": "x"}]
        own = lambda h: qualify.owns_contact(h, "Anna Woolliscroft", "Writing with Purpose")
        self.assertEqual(signals.money_signals(ch, items, owner_check=own), [])
        items[0]["description"] += " https://www.patreon.com/writingwithpurpose"
        self.assertEqual(signals.money_signals(ch, items, owner_check=own)[0][0], "Membership/subscription")

    def test_title_name_needs_corroboration(self):
        ch = {"description": "Fantasy Football Scout brings you tips.", "owner_name": "", "hosts": [],
              "owner_email": "commercials@fantasyfootballscout.co.uk"}
        self.assertFalse(qualify.name_corroborated("Fantasy Football Scout", ch, "Fantasy Football Scout - FPL Tips"))
        ch = {"description": "Hosted by Jen Davis.", "owner_name": "", "hosts": [], "owner_email": ""}
        self.assertTrue(qualify.name_corroborated("Jen Davis", ch, "The Jen Davis Show"))

    def test_website_country(self):
        self.assertEqual(signals.website_country("<p>123 Main St, Austin, TX 78701</p>")[0], "US")
        self.assertEqual(signals.website_country("Toronto, ON M5V 2T6")[0], "CA")
        self.assertEqual(signals.website_country("Surry Hills NSW 2010")[0], "AU")
        self.assertEqual(signals.website_country("Registered in England and Wales no. 123")[0], "GB")
        self.assertIsNone(signals.website_country("We love podcasts")[0])
        self.assertIsNone(signals.website_country("Austin, TX 78701 and Sydney NSW 2000")[0])
        ch = {"language": "en", "description": ""}
        cc, basis = signals.infer_country(ch, "", "", "us", [], site_info={"country": "AU", "url": "https://x.au",
                                                                          "snippet": "NSW 2000"})
        self.assertEqual(cc, "AU")
        self.assertIn("NSW 2000", basis)

    def test_guest_linkedin_dropped(self):
        p = parsed_fixture()
        for it in p["items"][:2]:
            it["description"] += " Guest: linkedin.com/in/someguest"
        lead = qualify.evaluate(cand(), p, NOW, CFG)
        self.assertNotIn("LinkedIn", lead["socials"])

    def test_person_names(self):
        self.assertTrue(qualify.is_person("Kristin Morrison"))
        self.assertTrue(qualify.is_person("Jane Doe & John Smith"))
        self.assertFalse(qualify.is_person("The Daily Hustle"))
        self.assertFalse(qualify.is_person("Acme Media"))
        self.assertEqual(qualify.lead_segment("Kristin Morrison | Pet Business Coach"), "Kristin Morrison")


class Messaging(unittest.TestCase):
    def setUp(self):
        self.lead = qualify.evaluate(cand(), parsed_fixture(), NOW, CFG)
        self.lead["lead_id"] = "L00001"
        self.lead["first_name"] = "Jane"

    def test_email_sequence_is_compliant(self):
        seq = messages.sequence(self.lead, CFG)
        self.assertEqual([m["step"] for m in seq], [1, 2, 3, 4])
        for m in seq[:3]:
            self.assertIn("IncuBrix", m["body"])
            self.assertIn("no thanks", m["body"])
            self.assertIn("utm_content=L00001", m["body"])
        self.assertIn("How to price your first offer", seq[0]["body"])
        self.assertIn(CFG["sender"]["address"], seq[0]["body"])

    def test_stated_need_quote_survives_truncation(self):
        lead = dict(self.lead, need_types=["Captions/transcripts", "Repurposing into clips", "Publishing consistency",
                                           "Stated workflow need"],
                    incubrix_need="Captions/transcripts: x; Repurposing into clips: y; Publishing consistency: z",
                    need_quote="hiring an editor")
        self.assertIn('mention "hiring an editor"', messages.need_line(lead))
        lead["need_quote"] = ""
        self.assertNotIn("Captions/transcripts", messages.need_line(lead))

    def test_dm_lengths(self):
        for plat, limit in messages.DM_LIMITS.items():
            for _, body in messages.dm_steps(self.lead, CFG, plat):
                self.assertLessEqual(len(body), limit, plat)


class PipelineRuns(unittest.TestCase):
    """End-to-end with fake network: normal run, rerun, refresh with new input, crash + recovery."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = {"db": os.path.join(self.tmp, "s.sqlite"), "cache": os.path.join(self.tmp, "c"),
                      "output": os.path.join(self.tmp, "out"), "outreach": os.path.join(self.tmp, "outreach"),
                      "logs": self.tmp}
        self.cfg = copy.deepcopy(CFG)
        self.cfg["apple"]["terms"], self.cfg["apple"]["local_terms"] = ["coach"], []
        self.cfg["apple"]["stores"] = ["gb"]
        self.cfg["apple"]["chart_stores"] = []  # charts hit the network; the end-to-end tests stay offline
        self.cfg["countries"]["max_share"] = 1.0
        base = parsed_fixture()
        self.feeds = {}
        for i in range(1, 6):
            p = copy.deepcopy(base)
            p["channel"]["description"] = p["channel"]["description"].replace("hello@janetest", f"hello{i}@janetest")
            p["channel"]["owner_email"] = f"owner{i}@janetest.co.uk"
            p["channel"]["links"] = [f"https://www.instagram.com/janetester{i}/"]
            for it in p["items"]:
                it["description"] = it["description"].replace("janetester", f"janetester{i}")
            self.feeds[f"https://feeds.example/{i}"] = p
        self.hits = [cand(i, name=f"Jane Tester{'abcde'[i - 1]} | Coach", feed_url=f"https://feeds.example/{i}")
                     for i in range(1, 4)]
        # the same show surfacing twice in search must collapse to one candidate
        self.hits.append(copy.deepcopy(self.hits[0]))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make(self, hits=None, fail_urls=()):
        def fetch(url):
            if url in fail_urls:
                raise OSError("connection reset")
            return copy.deepcopy(self.feeds[url])
        return Pipeline(self.cfg, self.paths, now=NOW, fetch_feed=fetch,
                        search=lambda t, s: (copy.deepcopy(hits if hits is not None else self.hits), False))

    def read_leads(self):
        with open(os.path.join(self.paths["output"], "leads.csv"), encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_runs(self):
        rep = self.make().run()
        self.assertEqual(rep["qualified"], 3)
        self.assertGreaterEqual(rep["duplicates_removed"], 1)
        rows = self.read_leads()
        self.assertEqual(list(rows[0].keys()), export.LEAD_COLUMNS)
        self.assertTrue(all(r["completeness_check"] == "COMPLETE" for r in rows))
        first_ids = {r["stable_creator_id"]: r["lead_id"] for r in rows}

        # repeat run on identical input: same leads, same IDs, no duplicates
        self.make().run()
        rows2 = self.read_leads()
        self.assertEqual({r["stable_creator_id"]: r["lead_id"] for r in rows2}, first_ids)

        # refresh with new input: new creator added, old ones keep IDs
        new = [cand(4, name="Jane Testerd | Coach", feed_url="https://feeds.example/4")]
        self.make(hits=self.hits + new).run()
        rows3 = self.read_leads()
        self.assertEqual(len(rows3), 4)
        self.assertEqual(len({r["stable_creator_id"] for r in rows3}), 4)
        for k, v in first_ids.items():
            self.assertEqual({r["stable_creator_id"]: r["lead_id"] for r in rows3}[k], v)

    def test_fresh_machine_keeps_ids_via_registry(self):
        self.paths["registry"] = os.path.join(self.tmp, "lead_ids.csv")
        self.make().run()
        ids = {r["stable_creator_id"]: r["lead_id"] for r in self.read_leads()}
        os.remove(self.paths["db"])  # simulate a fresh clone: no local state, only the committed registry
        shutil.rmtree(self.paths["output"])
        self.make().run()
        self.assertEqual({r["stable_creator_id"]: r["lead_id"] for r in self.read_leads()}, ids)

    def test_same_creator_two_shows_deduped(self):
        twin = cand(5, name="Jane Testera | Coach", feed_url="https://feeds.example/5")
        self.feeds["https://feeds.example/5"] = copy.deepcopy(self.feeds["https://feeds.example/1"])
        self.make(hits=self.hits + [twin]).run()
        self.assertEqual(len(self.read_leads()), 3)

    def test_failure_and_recovery(self):
        with self.assertRaises(SimulatedFailure):
            self.make().run(fail_after=1)
        rep = self.make().run()
        self.assertEqual(rep["qualified"], 3)

    def test_bad_feed_logged_not_fatal(self):
        rep = self.make(fail_urls={"https://feeds.example/2"}).run()
        self.assertEqual(rep["qualified"], 2)
        self.assertEqual(rep["feed_errors"], 1)
        with open(os.path.join(self.paths["output"], "errors.csv"), encoding="utf-8") as f:
            self.assertIn("connection reset", f.read())
        rep = self.make().run()  # the failed feed is retried next run
        self.assertEqual(rep["qualified"], 3)


if __name__ == "__main__":
    unittest.main()
