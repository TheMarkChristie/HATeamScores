"""TV channels for a game: reading the UK and Norwegian guides, finding the teams in them, and TheSportsDB's
broadcasters.

Run:  python -m unittest discover -s tests -v
The guides below are cut down from epgshare01's UK file and Allente's Norwegian guide of 18 Oct 2026, with the same
channel ids, names, fields and listing wording, so the rules are tested on what the real guides say.
"""
import gzip
import json
import unittest
from datetime import date, datetime, timedelta, timezone

from _load import const, model, tv

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


def allente_day(channels):
    return json.dumps({"start": "2026-10-22T00:00:00+00:00", "end": "2026-10-23T00:00:00+00:00", "totalChannels": len(channels),
                       "channels": [{"id": cid, "name": name, "programs": [
                           {"id": f"{cid}-{i}", "title": t, "shortDescription": d, "eventStart": s, "eventEnd": e, "genres": ["Sport"]}
                           for i, (t, d, s, e) in enumerate(progs)]} for cid, name, progs in channels]}).encode()


ALLENTE = [
    allente_day([
        ("10099", "TV 2 Sport 1 HD", [("EHL: Vålerenga - Frisk Asker", "Fra Jordal Amfi og kampen mellom Vålerenga og Frisk Asker.",
                                      "2026-10-22T16:55:00+00:00", "2026-10-22T19:30:00+00:00"),
                                     ("UEFA Champions League: Aston Villa - Viking", "", "2026-10-21T22:00:00+00:00", "2026-10-22T00:00:00+00:00")]),
        ("30003", "TV 2 HD (D)", [("EHL: Vålerenga - Frisk Asker", "", "2026-10-22T16:55:00+00:00", "2026-10-22T19:30:00+00:00")]),
        ("50047", "V sport 1 HD (N)", [("NHL: Seattle Kraken - Detroit Red Wings", "Ishockey, NHL.", "2026-10-21T01:30:00+00:00",
                                       "2026-10-21T04:30:00+00:00")]),
        ("50105", "V sport ultra HD", [("NHL: Seattle Kraken - Detroit Red Wings", "", "2026-10-21T01:30:00+00:00", "2026-10-21T04:30:00+00:00")]),
        ("10106", "V sport Premier League HD", [("Premier League: Leeds - Manchester United", "Fra Elland Road.",
                                                "2026-10-18T12:55:00+00:00", "2026-10-18T15:00:00+00:00")]),
        ("10055", "NRK1 Midtnytt", [("Fotball: Norge - Wales", "Nations League.", "2026-11-14T16:45:00+00:00", "2026-11-14T19:00:00+00:00")]),
        ("10001", "NRK1 HD", [("Fotball: Norge - Wales", "Nations League.", "2026-11-14T16:45:00+00:00", "2026-11-14T19:00:00+00:00")]),
        ("10042", "NRK1 Lydtekst", [("Fotball: Norge - Wales", "", "2026-11-14T16:45:00+00:00", "2026-11-14T19:00:00+00:00")]),
    ]),
    b"{not json",
]


def guides():
    return tv.parse_xmltv(gzip.compress(GUIDE_UK.encode()), "UK", NOW) + tv.parse_allente(ALLENTE, NOW)


def find(when, home, away, sport="Soccer", progs=None):
    got = tv.guide_listings(T(when), tv.team_needles(home, sport), tv.team_needles(away, sport), progs if progs is not None else guides())
    return [(i["channel"], i["country"]) for i in got]


class Channels(unittest.TestCase):
    def test_uk_names_people_use(self):
        self.assertEqual(tv.channel_name("SkySpMainEvHD"), "Sky Sports Main Event")
        self.assertEqual(tv.channel_name("SkySp Fball HD"), "Sky Sports Football")
        self.assertEqual(tv.channel_name("TNT Sports 1 HD"), "TNT Sports 1")
        self.assertEqual(tv.channel_name("BBC One ScotHD"), "BBC One Scotland")

    def test_uk_television_only(self):
        self.assertFalse(tv.guide_channel_wanted("BBC.R5L.uk"), "radio")
        self.assertFalse(tv.guide_channel_wanted("STV.Central.+1.uk"), "an hour later")
        self.assertFalse(tv.guide_channel_wanted("TNT.Sports.Ultimate.HD.uk"), "a 4K copy of another channel")
        self.assertTrue(tv.guide_channel_wanted("Premier.Sports.1.HD.uk"))

    def test_norwegian_names_and_the_channels_left_out(self):
        self.assertEqual(tv.allente_channel_name("V sport 1 HD (N)"), "V sport 1")
        self.assertEqual(tv.allente_channel_name("V sport + HD"), "V sport+")
        self.assertEqual(tv.allente_channel_name("TV 2 Sport Premium 2 HD"), "TV 2 Sport Premium 2")
        self.assertEqual(tv.allente_channel_name("NRK1 Midtnytt"), "NRK1")
        self.assertEqual(tv.allente_channel_name("NRK Super / NRK3 HD"), "NRK3")
        self.assertEqual(tv.allente_channel_name("Eurosport Norge HD"), "Eurosport Norge")
        self.assertIsNone(tv.allente_channel_name("TV 2 HD (D)"), "Danish")
        self.assertIsNone(tv.allente_channel_name("Yle TV2 HD"), "Finnish")
        self.assertIsNone(tv.allente_channel_name("NRK1 Lydtekst"), "a subtitled copy")
        self.assertIsNone(tv.allente_channel_name("V sport ultra HD"), "a 4K copy")


class Matching(unittest.TestCase):
    def test_the_live_broadcast_not_the_goals_show_radio_or_4k(self):
        self.assertEqual(find("2026-10-20T19:00:00", "Manchester City", "AEK Athens"), [("TNT Sports 1", "UK")])

    def test_north_american_nicknames_and_the_replay_left_out(self):
        self.assertEqual(find("2026-10-19T00:20:00", "Green Bay Packers", "Dallas Cowboys", "American Football"),
                         [("Sky Sports Main Event", "UK"), ("Sky Sports Action", "UK")])

    def test_norway_tv2_sport_without_the_danish_copy(self):
        self.assertEqual(find("2026-10-22T17:00:00", "Vålerenga", "Frisk Asker", "Ice Hockey"), [("TV 2 Sport 1", "NO")])

    def test_norway_v_sport_both_ways_round(self):
        self.assertEqual(find("2026-10-21T01:40:00", "Seattle Kraken", "Detroit Red Wings", "Ice Hockey"), [("V sport 1", "NO")])
        self.assertEqual(find("2026-10-18T13:00:00", "Leeds United", "Manchester United"), [("V sport Premier League", "NO")])

    def test_nrk1_once_whatever_the_region_and_norway_is_norge(self):
        self.assertEqual(find("2026-11-14T17:00:00", "Norway", "Wales"), [("NRK1", "NO")])

    def test_highlights_the_night_before_are_not_the_game(self):
        self.assertEqual(find("2026-10-24T14:00:00", "Rangers", "St Johnstone"), [])

    def test_a_long_word_by_its_start_and_capitals(self):
        self.assertTrue(tv.names_team(tv.fold("Manchester City - AEK Athen"), tv.team_needles("AEK Athens")))
        self.assertFalse(tv.names_team(tv.fold("Arsenal - Chelsea"), tv.team_needles("Manchester City")))


class SportsDB(unittest.TestCase):
    ROWS = [{"strCountry": "United Kingdom", "strChannel": "Amazon Prime Video UK"},
            {"strCountry": "The Netherlands", "strChannel": "Ziggo Sport 3"},
            {"strCountry": "Norway", "strChannel": "TV 2 Play"},
            {"strCountry": "United Kingdom", "strChannel": "TNT Sports Ultimate"}]   # the 4K copy, left out

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
        listing = {"channel": "TNT Sports 1", "country": "UK", "source": "guide"}
        mem = model.Memory(tracked=game, upcoming=[game], tv={"2594550": [listing]}, tv_checked={"2594550": NOW.isoformat()})
        mem = model.Memory.from_dict(mem.to_dict())
        self.assertEqual(mem.tv_checked, {"2594550": NOW.isoformat()})
        state, attrs = model.present(team, mem, NOW, 24, 6)
        self.assertEqual(state, "PRE")
        self.assertEqual(attrs["fixtures"][0]["tv"], [listing])
        self.assertEqual(attrs["tv_network"], "TNT Sports 1")


class LeagueDefaults(unittest.TestCase):
    DEFAULTS = [{"league_id": "4358", "league": "Norwegian Eliteserien", "country": "NO", "channel": "TV 2"},
                {"league_id": "4926", "league": "Norwegian Fjordkraft-ligaen", "country": "NO", "channel": "TV 2"}]

    def test_eliteserien_and_fjordkraft_ligaen_are_on_tv2_when_nothing_else_is_found(self):
        self.assertEqual(tv.with_defaults([], "4358", "Norwegian Eliteserien", self.DEFAULTS),
                         [{"channel": "TV 2", "country": "NO", "source": "default"}])
        self.assertEqual(tv.with_defaults([], None, "Norwegian Fjordkraft-ligaen", self.DEFAULTS)[0]["channel"], "TV 2", "by name")

    def test_the_guides_exact_channel_wins_and_uk_listings_stay(self):
        found = [{"channel": "TV 2 Sport 1", "country": "NO", "source": "guide"}]
        self.assertEqual(tv.with_defaults(found, "4926", None, self.DEFAULTS), found)
        uk = [{"channel": "Premier Sports 1", "country": "UK", "source": "guide"}]
        self.assertEqual([i["channel"] for i in tv.with_defaults(uk, "4358", None, self.DEFAULTS)], ["Premier Sports 1", "TV 2"])

    def test_uk_basketball_is_on_dazn_in_both_countries(self):
        for league_id, name in (("4431", "British Super League Basketball"), ("5127", "British Super League Basketball Women")):
            self.assertEqual(tv.with_defaults([], league_id, None, const.DEFAULT_TV),
                             [{"channel": "DAZN", "country": "UK", "source": "default"},
                              {"channel": "DAZN", "country": "NO", "source": "default"}], name)
            self.assertEqual(len(tv.with_defaults([], None, name, const.DEFAULT_TV)), 2, "by name")

    def test_valencia_is_on_euroleague_tv_home_or_away_in_any_competition(self):
        euroleague_tv = [{"channel": "EuroLeague TV", "country": "UK", "source": "default"},
                         {"channel": "EuroLeague TV", "country": "NO", "source": "default"}]
        self.assertEqual(tv.with_defaults([], "4408", "Spanish Liga ACB", const.DEFAULT_TV, ("135097", "134993")), euroleague_tv)
        self.assertEqual(tv.with_defaults([], "4546", "EuroLeague Basketball", const.DEFAULT_TV, ("135000", "135097")), euroleague_tv)
        self.assertEqual(tv.with_defaults([], "4408", "Spanish Liga ACB", const.DEFAULT_TV, ("134993", "135000")), [],
                         "another ACB game")
        self.assertEqual(tv.with_defaults([], "4408", "Spanish Liga ACB", const.DEFAULT_TV), [], "no teams given")

    def test_clan_tv_for_glasgow_clan_home_games_only(self):
        home = tv.with_defaults([], "4381", "UK Elite Ice Hockey League", const.DEFAULT_TV, ("136520", "136530"))
        self.assertEqual([(i["country"], i["channel"]) for i in home], [("UK", "Clan TV"), ("NO", "Clan TV")])
        self.assertEqual(tv.with_defaults([], "4381", "UK Elite Ice Hockey League", const.DEFAULT_TV, ("136519", "136520")), [],
                         "away at Fife")
        on_tv = [{"channel": "Premier Sports 1", "country": "UK", "source": "guide"}]
        self.assertEqual([(i["country"], i["channel"]) for i in
                          tv.with_defaults(on_tv, "4381", None, const.DEFAULT_TV, ("136520", "136530"))],
                         [("UK", "Premier Sports 1"), ("NO", "Clan TV")], "the guide's UK channel wins")

    def test_st_johnstone_tv_only_when_the_game_is_on_no_channel(self):
        saints = ("133639", "133604")
        self.assertEqual([(i["country"], i["channel"]) for i in
                          tv.with_defaults([], "4330", "Scottish Premier League", const.DEFAULT_TV, saints)],
                         [("UK", "St Johnstone TV"), ("NO", "St Johnstone TV")])
        self.assertEqual([(i["country"], i["channel"]) for i in
                          tv.with_defaults([], "4330", None, const.DEFAULT_TV, saints[::-1])],
                         [("UK", "St Johnstone TV"), ("NO", "St Johnstone TV")], "away as well")
        sky = [{"channel": "Sky Sports Main Event", "country": "UK", "source": "guide"}]
        self.assertEqual(tv.with_defaults(sky, "4330", None, const.DEFAULT_TV, saints), sky, "on TV: no club stream")

    def test_other_leagues_are_left_alone(self):
        self.assertEqual(tv.with_defaults([], "4328", "English Premier League", self.DEFAULTS), [])
        self.assertEqual(tv.with_defaults([], "4380", "Norwegian 1. Divisjon", self.DEFAULTS), [])


class TodayOnTv(unittest.TestCase):
    PROGS = None

    def setUp(self):
        mk = lambda start, ch, cc, head: tv.Programme(T(start), T(start) + timedelta(hours=2), ch, cc, tv.fold(head))  # noqa: E731
        self.progs = [
            mk("2026-10-18T12:00:00", "Sky Sports Main Event", "UK", "Live: Leeds United v Manchester United"),
            mk("2026-10-18T12:55:00", "V sport Premier League", "NO", "Premier League: Leeds - Manchester United"),
            mk("2026-10-18T21:00:00", "TNT Sports 1", "UK", "Live NWSL: Bay FC v Portland Thorns"),
            mk("2026-10-18T11:00:00", "TNT Sports 4", "UK", "Live WSL: Chelsea Women v Tottenham Women"),
            mk("2026-10-18T10:00:00", "V sport 3", "NO", "Bundesliga 2: Union Berlin - Hertha Berlin"),
        ]

    def ev(self, eid, ts, home, away, sport="Soccer"):
        return {"idEvent": eid, "strTimestamp": ts, "strHomeTeam": home, "strAwayTeam": away, "strSport": sport, "strLeague": "L"}

    def test_the_days_games_on_tv_by_time_without_the_traps(self):
        from zoneinfo import ZoneInfo
        events = [
            self.ev("1", "2026-10-18T13:00:00", "Leeds United", "Manchester United"),
            self.ev("2", "2026-10-18T21:00:00", "Chattanooga FC", "New York City FC II"),      # FC is not a name
            self.ev("3", "2026-10-18T11:00:00", "BK Häcken Women", "Hammarby Women"),          # Women is not a name
            self.ev("4", "2026-10-18T10:00:00", "Makkabi Berlin", "Füchse Berlin"),             # Berlin names neither
            self.ev("5", "2026-10-18T11:00:00", "Chelsea Women", "Tottenham Women"),
            self.ev("1", "2026-10-18T13:00:00", "Leeds United", "Manchester United"),           # listed twice: once
            self.ev("6", "2026-10-19T13:00:00", "Leeds United", "Manchester United"),           # another day
        ]
        games = tv.today_on_tv(events, self.progs, date(2026, 10, 18), ZoneInfo("Europe/Oslo"))
        self.assertEqual([(g["event_id"], [i["channel"] for i in g["tv"]]) for g in games],
                         [("5", ["TNT Sports 4"]), ("1", ["Sky Sports Main Event", "V sport Premier League"])])

    def test_a_league_default_puts_a_game_on_the_list(self):
        from zoneinfo import ZoneInfo
        game = dict(self.ev("7", "2026-10-18T14:00:00", "Manchester Basketball", "Caledonia Gladiators", "Basketball"),
                    idLeague="4431", strLeague="British Super League Basketball")
        other = dict(self.ev("8", "2026-10-18T14:00:00", "Bristol Flyers", "Sheffield Sharks", "Basketball"), idLeague="9999")
        games = tv.today_on_tv([game, other], self.progs, date(2026, 10, 18), ZoneInfo("Europe/Oslo"), const.DEFAULT_TV)
        self.assertEqual([(g["event_id"], [(i["country"], i["channel"]) for i in g["tv"]]) for g in games],
                         [("7", [("UK", "DAZN"), ("NO", "DAZN")])])

    def test_only_what_is_on_now_or_still_to_come(self):
        from zoneinfo import ZoneInfo
        events = [self.ev("1", "2026-10-18T13:00:00", "Leeds United", "Manchester United"),          # 13:00-15:00 UTC
                  self.ev("5", "2026-10-18T11:00:00", "Chelsea Women", "Tottenham Women")]             # 11:00-13:00 UTC
        oslo = ZoneInfo("Europe/Oslo")
        games = tv.today_on_tv(events, self.progs, date(2026, 10, 18), oslo, now=T("2026-10-18T13:30:00"))
        self.assertEqual([(g["event_id"], g["live"]) for g in games], [("1", True)], "the WSL game is over; Leeds is on now")
        games = tv.today_on_tv(events, self.progs, date(2026, 10, 18), oslo, now=T("2026-10-18T10:00:00"))
        self.assertEqual([(g["event_id"], g["live"]) for g in games], [("5", False), ("1", False)], "both still to come")
        self.assertEqual(games[1]["ends"], "2026-10-18T15:00:00+00:00")

    def test_irish_channels_are_not_uk(self):
        self.assertFalse(tv.guide_channel_wanted("Virgin.Media.Two.uk"))
        self.assertFalse(tv.guide_channel_wanted("RTE2.uk"))


class UtcDates(unittest.TestCase):
    def test_the_utc_dates_a_local_day_touches(self):
        from zoneinfo import ZoneInfo
        day = date(2026, 10, 18)
        self.assertEqual(tv.utc_dates(day, ZoneInfo("Europe/Oslo")), ["2026-10-17", "2026-10-18"])
        self.assertEqual(tv.utc_dates(day, ZoneInfo("Europe/London")), ["2026-10-17", "2026-10-18"])
        self.assertEqual(tv.utc_dates(day, ZoneInfo("America/Los_Angeles")), ["2026-10-18", "2026-10-19"])
        self.assertEqual(tv.utc_dates(day, ZoneInfo("UTC")), ["2026-10-18"])


if __name__ == "__main__":
    unittest.main()
