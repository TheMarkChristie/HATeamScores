"""TV channels for a game: reading the guides, finding the teams in them, and TheSportsDB's broadcasters.

Run:  python -m unittest discover -s tests -v
The guide below is cut down from epgshare01's UK and Norway files of 18 Oct 2026, with the same channel ids, names and
listing wording, so the rules are tested on what the real guides say.
"""
import gzip
import unittest
from datetime import datetime, timezone

from _load import model, tv

UTC = timezone.utc
T = lambda s: datetime.fromisoformat(s).replace(tzinfo=UTC)  # noqa: E731
NOW = T("2026-10-18T06:00:00")

GUIDE_UK = """<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="TNT.Sports.1.HD.uk"><display-name>TNT Sports 1 HD</display-name></channel>
  <channel id="TNT.Sports.3.HD.uk"><display-name>TNT Sports 3 HD</display-name></channel>
  <channel id="TNT.Sports.Ultimate.HD.uk"><display-name>TNT Sports Ultimate HD</display-name></channel>
  <channel id="SkySpMainEvHD.uk"><display-name>SkySpMainEvHD</display-name></channel>
  <channel id="SkySp.Action.uk"><display-name>SkySp Action</display-name></channel>
  <channel id="BBC.R5L.uk"><display-name>BBC Radio 5 Live</display-name></channel>
  <channel id="BBC.One.ScotHD.uk"><display-name>BBC One ScotHD</display-name></channel>
  <programme start="20261020180000 +0000" stop="20261020214500 +0000" channel="TNT.Sports.1.HD.uk">
    <title>Live UEFA Champions League</title><sub-title>Manchester City v AEK Athens (Kick-off 8.00pm)</sub-title>
    <desc>Manchester City v AEK Athens (Kick-off 8.00pm). Coverage of the league phase match from Etihad Stadium.</desc></programme>
  <programme start="20261020180000 +0000" stop="20261020214500 +0000" channel="TNT.Sports.Ultimate.HD.uk">
    <title>Live UEFA Champions League</title><sub-title>Manchester City v AEK Athens (Kick-off 8.00pm)</sub-title></programme>
  <programme start="20261020184500 +0000" stop="20261020220000 +0000" channel="TNT.Sports.3.HD.uk">
    <title>Live: UEFA Champions League Goals Show Xtra</title><sub-title>A look at all the drama from Tuesday's fixtures</sub-title>
    <desc>Including Paris Saint-Germain v Barcelona, and Manchester City v AEK Athens.</desc></programme>
  <programme start="20261020183000 +0000" stop="20261020220000 +0000" channel="BBC.R5L.uk">
    <title>Champions League Football</title><desc>Manchester City v AEK Athens commentary.</desc></programme>
  <programme start="20261019001000 +0000" stop="20261019040000 +0000" channel="SkySpMainEvHD.uk">
    <title>Live NFL Cowboys @ Packers</title></programme>
  <programme start="20261019001000 +0000" stop="20261019040000 +0000" channel="SkySp.Action.uk">
    <title>Live: NFL Cowboys @ Packers</title></programme>
  <programme start="20261019120000 +0000" stop="20261019150000 +0000" channel="SkySpMainEvHD.uk">
    <title>NFL Cowboys @ Packers</title><sub-title>Replay</sub-title></programme>
  <programme start="20261017212500 +0000" stop="20261017222500 +0000" channel="BBC.One.ScotHD.uk">
    <title>Sportscene: Premiership Highlights</title><desc>Rangers v St Johnstone and the rest.</desc></programme>
</tv>"""

GUIDE_NO = """<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="V.sport.Premier.League.Norway.(NO,NO).no"><display-name>V sport Premier League Norway (NO,NO)</display-name></channel>
  <channel id="TV3.Sport.Denmark.(DK,DA).no"><display-name>TV3 Sport Denmark (DK,DA)</display-name></channel>
  <channel id="TV.2.Sport.1.Norway.(NO,NO).no"><display-name>TV 2 Sport 1 Norway (NO,NO)</display-name></channel>
  <programme start="20261018145500 +0200" stop="20261018170000 +0200" channel="V.sport.Premier.League.Norway.(NO,NO).no">
    <title>Premier League</title><sub-title>Leeds - Manchester United</sub-title></programme>
  <programme start="20261018145500 +0200" stop="20261018170000 +0200" channel="TV3.Sport.Denmark.(DK,DA).no">
    <title>Premier League</title><sub-title>Leeds - Manchester United</sub-title></programme>
  <programme start="20261022185500 +0200" stop="20261022213000 +0200" channel="TV.2.Sport.1.Norway.(NO,NO).no">
    <title>Ishockey: Fjordkraft-ligaen</title><sub-title>Vålerenga - Frisk Asker</sub-title></programme>
</tv>"""


def guides():
    return (tv.parse_guide(gzip.compress(GUIDE_UK.encode()), "UK", NOW)
            + tv.parse_guide(GUIDE_NO.encode(), "NO", NOW))


def find(when, home, away, sport="Soccer", progs=None):
    got = tv.guide_listings(T(when), tv.team_needles(home, sport), tv.team_needles(away, sport), progs if progs is not None else guides())
    return [(i["channel"], i["country"]) for i in got]


class Channels(unittest.TestCase):
    def test_names_people_use(self):
        self.assertEqual(tv.channel_name("SkySpMainEvHD"), "Sky Sports Main Event")
        self.assertEqual(tv.channel_name("SkySp Fball HD"), "Sky Sports Football")
        self.assertEqual(tv.channel_name("TNT Sports 1 HD"), "TNT Sports 1")
        self.assertEqual(tv.channel_name("V sport Premier League 1 Norway (NO,NO)"), "V sport Premier League 1")
        self.assertEqual(tv.channel_name("Viasport+ Norway (NO,NO)"), "V sport+")
        self.assertEqual(tv.channel_name("BBC One ScotHD"), "BBC One Scotland")

    def test_only_this_countrys_television(self):
        self.assertFalse(tv.guide_channel_wanted("BBC.R5L.uk", "UK"), "radio")
        self.assertFalse(tv.guide_channel_wanted("STV.Central.+1.uk", "UK"), "an hour later")
        self.assertFalse(tv.guide_channel_wanted("TNT.Sports.Ultimate.HD.uk", "UK"), "a 4K copy of another channel")
        self.assertFalse(tv.guide_channel_wanted("TV3.Sport.Denmark.(DK,DA).no", "NO"), "Danish, in the Norwegian file")
        self.assertTrue(tv.guide_channel_wanted("TV.2.Sport.1.Norway.(NO,NO).no", "NO"))


class Matching(unittest.TestCase):
    def test_the_live_broadcast_not_the_goals_show_or_radio(self):
        self.assertEqual(find("2026-10-20T19:00:00", "Manchester City", "AEK Athens"), [("TNT Sports 1", "UK")])

    def test_north_american_nicknames_and_the_replay_left_out(self):
        self.assertEqual(find("2026-10-19T00:20:00", "Green Bay Packers", "Dallas Cowboys", "American Football"),
                         [("Sky Sports Main Event", "UK"), ("Sky Sports Action", "UK")])

    def test_norwegian_listing_short_names_and_local_times(self):
        self.assertEqual(find("2026-10-18T13:00:00", "Leeds United", "Manchester United"), [("V sport Premier League", "NO")])
        self.assertEqual(find("2026-10-22T17:00:00", "Vålerenga", "Frisk Asker", "Ice Hockey"), [("TV 2 Sport 1", "NO")])

    def test_highlights_the_night_before_are_not_the_game(self):
        self.assertEqual(find("2026-10-24T14:00:00", "Rangers", "St Johnstone"), [])

    def test_a_long_word_by_its_start(self):
        self.assertTrue(tv.names_team(tv.fold("Manchester City - AEK Athen"), tv.team_needles("AEK Athens")))
        self.assertFalse(tv.names_team(tv.fold("Arsenal - Chelsea"), tv.team_needles("Manchester City")))


class SportsDB(unittest.TestCase):
    ROWS = [{"strCountry": "United Kingdom", "strChannel": "Amazon Prime Video UK"},
            {"strCountry": "The Netherlands", "strChannel": "Ziggo Sport 3"},
            {"strCountry": "Norway", "strChannel": "TV 2 Play"}]

    def test_uk_and_norway_only(self):
        self.assertEqual(tv.sportsdb_listings(self.ROWS), [
            {"channel": "Amazon Prime Video", "country": "UK", "source": "thesportsdb"},
            {"channel": "TV 2 Play", "country": "NO", "source": "thesportsdb"}])

    def test_merge_once_per_channel_uk_first(self):
        guide = [{"channel": "V sport 1", "country": "NO", "source": "guide"}, {"channel": "TNT Sports 1", "country": "UK", "source": "guide"}]
        sdb = [{"channel": "TNT Sports 1", "country": "UK", "source": "thesportsdb"}, {"channel": "Amazon Prime Video", "country": "UK", "source": "thesportsdb"}]
        self.assertEqual([(i["channel"], i["source"]) for i in tv.merge(guide, sdb)],
                         [("TNT Sports 1", "guide"), ("Amazon Prime Video", "thesportsdb"), ("V sport 1", "guide")])


class OnTheSensor(unittest.TestCase):
    def test_channels_on_fixtures_and_kept_across_a_restart(self):
        team = model.Team(id="133613", name="Manchester City", sport="Soccer")
        game = model.Event(id="2594550", name="Manchester City vs AEK Athens", sport="Soccer", start=T("2026-10-20T19:00:00"),
                           home_id="133613", home_name="Manchester City", away_id="1", away_name="AEK Athens")
        mem = model.Memory(tracked=game, upcoming=[game], tv={"2594550": [{"channel": "TNT Sports 1", "country": "UK", "source": "guide"}]})
        mem = model.Memory.from_dict(mem.to_dict())
        state, attrs = model.present(team, mem, NOW, 24, 6)
        self.assertEqual(state, "PRE")
        self.assertEqual(attrs["fixtures"][0]["tv"], [{"channel": "TNT Sports 1", "country": "UK", "source": "guide"}])
        self.assertEqual(attrs["tv_network"], "TNT Sports 1")


if __name__ == "__main__":
    unittest.main()
