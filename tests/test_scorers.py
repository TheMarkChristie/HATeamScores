"""Who scored: finding the game on ESPN, reading its goals, and TheSportsDB's timeline as the fallback.

Run:  python -m unittest discover -s tests -v
The fixtures are ESPN's real answers for 17 Oct 2026, trimmed to the fields the rules read.
"""
import json
import pathlib
import unittest
from datetime import datetime, timezone

from _load import scorers

UTC = timezone.utc
T = lambda s: datetime.fromisoformat(s).replace(tzinfo=UTC)  # noqa: E731
FIX = pathlib.Path(__file__).parent / "fixtures"
load = lambda name: json.loads((FIX / name).read_text(encoding="utf-8"))  # noqa: E731


class Leagues(unittest.TestCase):
    def test_by_id_or_by_name(self):
        self.assertEqual(scorers.espn_slug("4328", "English Premier League"), "soccer/eng.1")
        self.assertEqual(scorers.espn_slug(None, "Scottish Premier League"), "soccer/sco.1")
        self.assertEqual(scorers.espn_slug("4358", None), "soccer/nor.1")
        self.assertEqual(scorers.espn_slug(None, "NHL"), "hockey/nhl")
        self.assertIsNone(scorers.espn_slug("4926", "Norwegian Fjordkraft-ligaen"), "not on ESPN")

    def test_espn_files_games_by_us_eastern_date(self):
        self.assertEqual(scorers.scoreboard_dates(T("2026-10-17T14:00:00")), ["20261017"])
        self.assertEqual(scorers.scoreboard_dates(T("2026-10-19T00:20:00")), ["20261018", "20261019"], "a late kick-off in Europe is the day before in New York")


class Espn(unittest.TestCase):
    def test_finds_the_game_on_the_scoreboard(self):
        sb = load("espn_eng1_scoreboard_20261017.json")
        self.assertEqual(scorers.find_espn_event(sb, T("2026-10-17T14:00:00"), "Brentford", "Liverpool", "Soccer"), "401879262")
        self.assertEqual(scorers.find_espn_event(sb, T("2026-10-17T16:30:00"), "Manchester City", "Ipswich Town", "Soccer"), "401879259")
        self.assertIsNone(scorers.find_espn_event(sb, T("2026-10-17T14:00:00"), "Arsenal", "Rosenborg", "Soccer"))
        self.assertIsNone(scorers.find_espn_event(sb, T("2026-10-24T14:00:00"), "Brentford", "Liverpool", "Soccer"), "a week out")

    def test_every_football_goal_with_scorer_assist_and_side(self):
        goals, final = scorers.parse_espn_summary(load("espn_summary_brentford_liverpool.json"), "Soccer")
        self.assertTrue(final)
        self.assertEqual([(g["time"], g["side"], g["player"], g["assist"]) for g in goals], [
            ("44'", "home", "Keane Lewis-Potter", "Igor Thiago"),
            ("62'", "away", "Víctor Muñoz", "Florian Wirtz"),
            ("70'", "away", "Alexander Isak", "Bradley Barcola")])

    def test_ice_hockey_goals_by_period(self):
        goals, final = scorers.parse_espn_summary(load("espn_summary_panthers_kraken.json"), "Ice Hockey")
        self.assertTrue(final)
        self.assertEqual(len(goals), 11, "8-3")
        self.assertEqual(sum(1 for g in goals if g["side"] == "home"), 8)
        self.assertEqual((goals[0]["time"], goals[0]["player"], goals[0]["assist"]), ("P1 1:05", "Sam Bennett", "Matthew Tkachuk"))


class TheSportsDB(unittest.TestCase):
    ROWS = [  # TheSportsDB's free timeline for Brentford 1-2 Liverpool: five events, one goal
        {"strTimeline": "Card", "strTimelineDetail": "Yellow Card", "strHome": "No", "strPlayer": "A", "intTime": "30"},
        {"strTimeline": "Goal", "strTimelineDetail": "Normal Goal", "strHome": "Yes", "strPlayer": "Keane Lewis-Potter", "strAssist": "Igor Thiago", "intTime": "44"},
        {"strTimeline": "Goal", "strTimelineDetail": "Penalty", "strHome": "No", "strPlayer": "Mohamed Salah", "strAssist": "x", "intTime": "88"},
    ]

    def test_goals_and_whether_they_cover_the_score(self):
        goals, complete = scorers.timeline_goals(self.ROWS, 1, 2)
        self.assertEqual([(g["time"], g["side"], g["player"], g["note"]) for g in goals],
                         [("44'", "home", "Keane Lewis-Potter", ""), ("88'", "away", "Mohamed Salah", "pen")])
        self.assertEqual(goals[1]["assist"], "", "no assist on a penalty")
        self.assertFalse(complete, "two goals listed for a 1-2 game")
        self.assertTrue(scorers.timeline_goals(self.ROWS, 1, 1)[1])


if __name__ == "__main__":
    unittest.main()
