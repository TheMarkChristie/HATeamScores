"""Club streams' own schedules: Clan TV's feed (as it was on 18 Oct 2026, the night of the Challenge Cup game against
Fife that TheSportsDB did not have) read into games, and On TV today showing them until the stream ends."""
import json
import pathlib
import unittest
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from _load import const, streams, tv

FEED = json.loads((pathlib.Path(__file__).parent / "clantv_feed.json").read_text(encoding="utf-8"))
CLAN = const.STREAMS[0]
OSLO = ZoneInfo("Europe/Oslo")


class Streams(unittest.TestCase):
    def test_the_feed_becomes_games(self):
        games = streams.stream_games(FEED, CLAN)
        self.assertEqual([(g["strHomeTeam"], g["strAwayTeam"], g["strLeague"]) for g in games],
                         [("Glasgow Clan", "Fife Flyers", "Challenge Cup"), ("Glasgow Clan", "Belfast Giants", "EIHL"),
                          ("Glasgow Clan", "Dundee Stars", "Challenge Cup")])
        fife = games[0]
        self.assertEqual(fife["strTimestamp"], "2026-10-18T14:45:00+00:00")
        self.assertEqual(fife["strEndTimestamp"], "2026-10-18T18:15:00+00:00")
        self.assertEqual((fife["idHomeTeam"], fife["idAwayTeam"]), ("136520", None))
        self.assertEqual(streams.stream_games({"data": [{"programmes": [{"title": "Studio show", "starttime_utc": "2026-10-18 10:00:00"}]}]}, CLAN), [])
        self.assertEqual(streams.stream_games(None, CLAN), [])

    def test_a_game_thesportsdb_has_is_not_added_twice(self):
        games = streams.stream_games(FEED, CLAN)
        known = [{"strTimestamp": "2026-10-23T18:30:00", "strHomeTeam": "Glasgow Clan", "strAwayTeam": "Belfast Giants"}]
        self.assertEqual([g["strAwayTeam"] for g in streams.missing_from(games, known)], ["Fife Flyers", "Dundee Stars"])

    def test_on_tv_today_shows_the_stream_until_it_ends(self):
        games = streams.missing_from(streams.stream_games(FEED, CLAN), [])
        now = datetime(2026, 10, 18, 17, 12, tzinfo=timezone.utc)        # 2 h 27 min after it began: over by the clock
        listed = tv.today_on_tv(games, [], date(2026, 10, 18), OSLO, const.DEFAULT_TV, now)
        self.assertEqual(len(listed), 1)
        game = listed[0]
        self.assertEqual((game["home"], game["away"], game["live"], game["ends"]),
                         ("Glasgow Clan", "Fife Flyers", True, "2026-10-18T18:15:00+00:00"))
        self.assertEqual(game["tv"], [{"channel": "Clan TV", "country": "UK", "source": "default"},
                                      {"channel": "Clan TV", "country": "NO", "source": "default"}])
        after = datetime(2026, 10, 18, 18, 16, tzinfo=timezone.utc)
        self.assertEqual(tv.today_on_tv(games, [], date(2026, 10, 18), OSLO, const.DEFAULT_TV, after), [])

    def test_glasgow_away_games_show_clan_tv_too(self):
        away = {"idEvent": "1", "strTimestamp": "2026-11-01T18:00:00", "strHomeTeam": "Guildford Flames", "strAwayTeam": "Glasgow Clan",
                "strSport": "Ice Hockey", "idLeague": "4381", "strLeague": "UK Elite Ice Hockey League", "idHomeTeam": "134920",
                "idAwayTeam": "136520"}
        listed = tv.today_on_tv([away], [], date(2026, 11, 1), OSLO, const.DEFAULT_TV, datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc))
        self.assertEqual([c["channel"] for c in listed[0]["tv"]], ["Clan TV", "Clan TV"])


if __name__ == "__main__":
    unittest.main()
