"""The model on its own: parsing TheSportsDB records, the fixture memory through a game, and what the sensor shows.

Run:  python -m unittest discover -s tests -v
"""
import unittest
from datetime import datetime, timedelta, timezone

from _load import const, model

UTC = timezone.utc
T = lambda s: datetime.fromisoformat(s).replace(tzinfo=UTC)  # noqa: E731

# recorded from TheSportsDB on 11 Oct 2026 (free key), trimmed to the fields the model reads
CLAN = {"idTeam": "136520", "strTeam": "Glasgow Clan", "strTeamShort": "", "strSport": "Ice Hockey", "strLeague": "UK Elite Ice Hockey League",
        "idLeague": "4381", "strStadium": "Braehead Arena", "strLocation": "Glasgow", "strCountry": "Scotland",
        "strBadge": "https://r2.thesportsdb.com/images/media/team/badge/8lgdnh1554229324.png", "strGender": "Male"}
AWAY_FT = {"idEvent": "2523079", "strEvent": "Manchester Storm vs Glasgow Clan", "strSport": "Ice Hockey", "strLeague": "UK Elite Ice Hockey League",
           "idLeague": "4381", "strSeason": "2026-2027", "intRound": "1", "strTimestamp": "2026-09-23T18:30:00", "dateEvent": "2026-09-23",
           "strTime": "18:30:00", "idHomeTeam": "136522", "strHomeTeam": "Manchester Storm", "strHomeTeamBadge": "https://x/storm.png",
           "idAwayTeam": "136520", "strAwayTeam": "Glasgow Clan", "strAwayTeamBadge": "https://x/clan.png", "intHomeScore": "2",
           "intAwayScore": "1", "strVenue": "Altrincham Ice Dome", "strCountry": "England", "strStatus": "FT", "strPostponed": "no"}
HOME_NS = {"idEvent": "2537330", "strEvent": "Glasgow Clan vs Guildford Flames", "strSport": "Ice Hockey", "strLeague": "UK Elite Ice Hockey League",
           "strTimestamp": "2026-10-11T15:00:00", "dateEvent": "2026-10-11", "strTime": "15:00:00", "idHomeTeam": "136520",
           "strHomeTeam": "Glasgow Clan", "strHomeTeamBadge": "https://x/clan.png", "idAwayTeam": "136530", "strAwayTeam": "Guildford Flames",
           "strAwayTeamBadge": "https://x/flames.png", "intHomeScore": None, "intAwayScore": None, "strVenue": "Braehead Arena",
           "strCountry": "Scotland", "strStatus": "NS", "strPostponed": "no"}
NEXT_AWAY = {"idEvent": "2537340", "strEvent": "Fife Flyers vs Glasgow Clan", "strSport": "Ice Hockey", "strLeague": "UK Elite Ice Hockey League",
             "strTimestamp": "2026-10-18T18:00:00", "dateEvent": "2026-10-18", "strTime": "18:00:00", "idHomeTeam": "136519",
             "strHomeTeam": "Fife Flyers", "idAwayTeam": "136520", "strAwayTeam": "Glasgow Clan", "strVenue": "Fife Ice Arena",
             "strCountry": "Scotland", "strStatus": "NS", "strPostponed": "no"}


class ParseTests(unittest.TestCase):
    def test_event_fields(self):
        e = model.Event.parse(AWAY_FT)
        self.assertEqual(e.start, T("2026-09-23T18:30:00"))
        self.assertTrue(e.time_known)
        self.assertEqual((e.home_score, e.away_score), (2, 1))
        self.assertEqual(e.venue, "Altrincham Ice Dome")
        self.assertTrue(e.finished(T("2026-09-23T21:00:00")))
        self.assertEqual(e.expected_end, T("2026-09-23T21:20:00"))

    def test_event_without_time(self):
        e = model.Event.parse({"idEvent": "1", "dateEvent": "2026-11-14", "strSport": "Soccer"})
        self.assertFalse(e.time_known)
        self.assertEqual(e.start, T("2026-11-14T12:00:00"))

    def test_unfinished_and_cancelled(self):
        e = model.Event.parse(HOME_NS)
        self.assertFalse(e.finished(T("2026-10-11T16:00:00")))
        e.home_score, e.away_score = 3, 2
        self.assertFalse(e.finished(T("2026-10-11T17:00:00")), "scores alone are not a result until well after the end")
        self.assertTrue(e.finished(T("2026-10-11T19:00:00")))
        p = model.Event.parse(dict(HOME_NS, strPostponed="yes"))
        self.assertTrue(p.cancelled)

    def test_team_and_abbreviations(self):
        t = model.Team.parse(CLAN)
        self.assertEqual((t.id, t.sport, t.city), ("136520", "Ice Hockey", "Glasgow"))
        self.assertEqual(t.abbr, "GC")
        city = model.Team.parse({"idTeam": "133613", "strTeam": "Manchester City", "strTeamShort": "MCI", "strSport": "Soccer"})
        self.assertEqual(city.abbr, model.abbreviation("Manchester City"), "our side and the opponent's side must agree")
        self.assertEqual(model.abbreviation("Liverpool"), "LIV")
        self.assertEqual(model.abbreviation("Seattle Sounders FC"), "SS")
        self.assertEqual(model.abbreviation("St Johnstone"), "SJ")
        self.assertEqual(model.prefix_for_sport("Soccer"), "football")
        self.assertEqual(model.prefix_for_sport("Field Hockey"), "field_hockey")

    def test_round_trip(self):
        mem = model.Memory(tracked=model.Event.parse(HOME_NS), last=model.Event.parse(AWAY_FT), checked_next=T("2026-10-11T10:00:00"), seeded=True)
        mem.last.finished_at = T("2026-09-23T21:20:00")
        back = model.Memory.from_dict(mem.to_dict())
        self.assertEqual(back.to_dict(), mem.to_dict())
        self.assertEqual(back.last.finished_at, T("2026-09-23T21:20:00"))
        self.assertEqual(model.Team.from_dict(model.Team.parse(CLAN).to_dict()), model.Team.parse(CLAN))


class LifecycleTests(unittest.TestCase):
    """A Glasgow Clan week: a home game on Sunday, then an away game the next Sunday."""

    def setUp(self):
        self.team = model.Team.parse(CLAN)
        self.mem = model.Memory()

    def show(self, now):
        return model.present(self.team, self.mem, now, 24, 6)

    def test_first_run_then_a_game(self):
        now = T("2026-10-11T10:00:00")
        self.assertTrue(model.needs_next(self.mem, now))
        model.absorb_next(self.mem, [model.Event.parse(HOME_NS)], now)
        model.absorb_last(self.mem, [model.Event.parse(AWAY_FT)], now)
        state, a = self.show(now)
        self.assertEqual(state, "PRE")
        self.assertEqual(a["kickoff_in"], "Today 15:00")
        self.assertEqual((a["team_homeaway"], a["opponent_name"], a["location"]), ("home", "Guildford Flames", "Braehead Arena, Scotland"))
        self.assertEqual(a["last_game"]["name"], "Manchester Storm vs Glasgow Clan")
        self.assertIsNone(a["next_game"])
        self.assertEqual(a["date"], "2026-10-11T15:00:00+00:00")
        # kick-off: in play, no score on the free key
        now = T("2026-10-11T15:05:00")
        self.assertFalse(model.needs_next(self.mem, now))
        self.assertTrue(model.needs_lookup(self.mem, now))
        model.absorb_lookup(self.mem, model.Event.parse(HOME_NS), now)
        state, a = self.show(now)
        self.assertEqual((state, a["clock"], a["team_score"]), ("IN", "In play", None))
        # the clock says it is over, TheSportsDB has not posted the score
        now = T("2026-10-11T18:30:00")
        state, a = self.show(now)
        self.assertEqual((state, a["clock"]), ("POST", "Awaiting result"))
        # the result lands
        now = T("2026-10-11T19:00:00")
        model.absorb_lookup(self.mem, model.Event.parse(dict(HOME_NS, strStatus="FT", intHomeScore="4", intAwayScore="2")), now)
        self.assertIsNone(self.mem.tracked)
        self.assertEqual(self.mem.last.finished_at, T("2026-10-11T17:50:00"), "capped at the expected end")
        state, a = self.show(now)
        self.assertEqual((state, a["clock"], a["team_score"], a["opponent_score"], a["team_winner"], a["opponent_winner"]),
                         ("POST", "FT", 4, 2, True, False))
        # the next fixture is read; the game just played is not it
        self.assertTrue(model.needs_next(self.mem, now))
        model.absorb_next(self.mem, [model.Event.parse(dict(HOME_NS, strStatus="FT")), model.Event.parse(NEXT_AWAY)], now)
        self.assertEqual(self.mem.tracked.id, "2537340")
        state, a = self.show(now)
        self.assertEqual(state, "POST", "the result stays for 24 hours")
        self.assertEqual(a["next_game"]["name"], "Fife Flyers vs Glasgow Clan")
        # the lists for the card: both results newest first, the one coming fixture
        self.assertEqual([r["name"] for r in a["results"]], ["Glasgow Clan vs Guildford Flames", "Manchester Storm vs Glasgow Clan"])
        self.assertEqual([f["name"] for f in a["fixtures"]], ["Fife Flyers vs Glasgow Clan"])
        self.assertEqual((a["results"][0]["finished"], a["results"][0]["home_score"], a["results"][0]["day"], a["results"][0]["time"]),
                         (True, 4, "2026-10-11", "15:00"))
        self.assertEqual((a["fixtures"][0]["finished"], a["fixtures"][0]["live"], a["fixtures"][0]["home_badge"]), (False, False, None))
        # a day later the next fixture takes over
        now = T("2026-10-12T18:00:00")
        state, a = self.show(now)
        self.assertEqual((state, a["team_homeaway"], a["kickoff_in"]), ("PRE", "away", "Sun 18 Oct 18:00"))
        self.assertEqual(a["last_game"]["home_score"], 4)

    def test_next_fixture_takes_over_before_kick_off(self):
        now = T("2026-10-11T19:00:00")
        last = model.Event.parse(dict(HOME_NS, strStatus="FT", intHomeScore="1", intAwayScore="1"))
        last.finished_at = T("2026-10-11T18:00:00")
        self.mem.last = last
        self.mem.tracked = model.Event.parse(dict(NEXT_AWAY, strTimestamp="2026-10-12T14:00:00"))
        self.assertEqual(self.show(T("2026-10-12T07:00:00"))[0], "POST")
        state, a = self.show(T("2026-10-12T09:00:00"))
        self.assertEqual(state, "PRE", "six hours before kick-off the fixture shows")
        self.assertEqual(a["kickoff_in"], "Today 14:00")
        self.assertEqual(model.next_transition(self.mem, now, 24, 6), T("2026-10-12T08:00:00"))

    def test_old_result_is_dated_and_nothing_is_not_found(self):
        self.assertEqual(self.show(T("2026-10-11T10:00:00"))[0], "NOT_FOUND")
        last = model.Event.parse(AWAY_FT)
        last.finished_at = T("2026-09-23T21:20:00")
        self.mem.last = last
        state, a = self.show(T("2026-10-11T10:00:00"))
        self.assertEqual((state, a["clock"], a["team_homeaway"], a["team_winner"]), ("POST", "FT 23 Sep", "away", False))

    def test_postponed_and_lost_fixtures(self):
        now = T("2026-10-11T10:00:00")
        model.absorb_next(self.mem, [model.Event.parse(dict(HOME_NS, strPostponed="yes")), model.Event.parse(NEXT_AWAY)], now)
        self.assertEqual(self.mem.tracked.id, "2537340")
        self.mem.tracked = model.Event.parse(HOME_NS)
        now = T("2026-10-11T16:00:00")
        model.absorb_lookup(self.mem, None, now)
        self.assertIsNotNone(self.mem.tracked, "a failed read keeps the fixture")
        model.absorb_lookup(self.mem, None, T("2026-10-13T16:00:00"))
        self.assertIsNone(self.mem.tracked, "a day after its end a lost fixture is dropped")

    def test_kickoff_text(self):
        today = T("2026-10-11T09:00:00")
        self.assertEqual(model.kickoff_text(T("2026-10-11T15:00:00"), today), "Today 15:00")
        self.assertEqual(model.kickoff_text(T("2026-10-12T19:30:00"), today), "Tomorrow 19:30")
        self.assertEqual(model.kickoff_text(T("2026-11-14T19:45:00"), today), "Sat 14 Nov 19:45")
        self.assertEqual(model.kickoff_text(T("2026-11-14T12:00:00"), today, time_known=False), "Sat 14 Nov")

    def test_local_time_in_attributes(self):
        oslo = lambda d: d.astimezone(timezone(timedelta(hours=2)))  # noqa: E731
        self.mem.tracked = model.Event.parse(HOME_NS)
        state, a = model.present(self.team, self.mem, T("2026-10-11T09:00:00"), 24, 6, oslo)
        self.assertEqual(a["kickoff_in"], "Today 17:00")
        self.assertEqual(a["date"], "2026-10-11T15:00:00+00:00", "the date stays UTC for the card")


if __name__ == "__main__":
    unittest.main()
