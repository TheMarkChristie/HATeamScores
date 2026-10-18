"""Constants for TheSportsDB Tracker. Nothing here imports Home Assistant, so the model and its tests stay pure."""

DOMAIN = "sportsdb_tracker"
NAME = "TheSportsDB Tracker"
ATTRIBUTION = "Data provided by TheSportsDB.com"

# TheSportsDB v1 API: https://www.thesportsdb.com/api/v1/json/<key>/<call>.php
API_BASE = "https://www.thesportsdb.com/api/v1/json"
DEFAULT_API_KEY = "123"                  # the public free key: 30 requests a minute
FREE_MIN_INTERVAL = 2.2                  # seconds between requests on the free key (about 27 a minute)
PREMIUM_MIN_INTERVAL = 0.7               # a premium key allows 100 a minute

CONF_API_KEY = "api_key"
CONF_TEAM_ID = "team_id"
CONF_TEAM_NAME = "team_name"
CONF_SPORT = "sport"
CONF_LEAGUE = "league"
CONF_PREFIX = "prefix"                   # the sensor's entity id prefix, e.g. football -> sensor.football_<team>
CONF_RESULTS_HOURS = "results_hours"     # how long a full-time result stays on the sensor
CONF_PRE_HOURS = "pre_hours"             # switch from the result to the next fixture this long before kick-off
DEFAULT_RESULTS_HOURS = 24
DEFAULT_PRE_HOURS = 6

STORAGE_VERSION = 1

# TV channels for each fixture (tv.py): the UK guide from epgshare01, Norway's from Allente, and TheSportsDB's broadcasters
GUIDE_UK_URL = "https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz"
ALLENTE_URL = "https://www.allente.no/api/epg/refetch-epg-data?Start={day}"
ALLENTE_DAYS = 5                         # Allente lists about five days ahead
GUIDE_REFRESH_HOURS = 6                  # the guides are rebuilt daily; a few reads a day catch the new days early
GUIDE_RETRY_MINUTES = 30                 # after a failed download
TV_DAYS_AHEAD = 14                       # fixtures this close get their channels looked up
SPORTSDB_TV_HOURS = 12                   # TheSportsDB's broadcasters for a game are asked again after this long

# Who scored (scorers.py): ESPN first, TheSportsDB's timeline for football games ESPN does not cover
SCORERS_DAYS = 3                         # finished games this recent get their scorers looked up
SCORERS_RECHECK_MINUTES = 20             # a game whose goals are not final yet is asked again after this long

# Channels a game gets when the guides and TheSportsDB find none for that country. Mark, 18 Oct 2026: "by default have
# all Norwegian ice hockey and football elite games on TV2" (TV 2 holds both; most Eliteserien games are on TV 2 Play
# only, so no guide lists them). Matched by TheSportsDB league id, or by the league's name if an event has no id.
DEFAULT_TV = [
    {"league_id": "4358", "league": "Norwegian Eliteserien", "country": "NO", "channel": "TV 2"},
    {"league_id": "4926", "league": "Norwegian Fjordkraft-ligaen", "country": "NO", "channel": "TV 2"},
]

# the Team Scores card, served by the integration from its www folder and registered as a dashboard resource
URL_BASE = "/sportsdb_tracker"
CARD_FILE = "team-scores-card.js"

UPDATE_MINUTES_IDLE = 30                 # between checks of the next fixture
UPDATE_MINUTES_LIVE = 10                 # while a game is on, or its result is awaited
NEXT_CHECK_MINUTES = 30                  # re-read the next fixture this often (moved games, postponements)
LOOKUP_GRACE_HOURS = 24                  # give up on a fixture this long after its expected end if the API loses it

# Mark's names for the sports, and the entity id prefixes the scoreboard card groups by
SPORT_LABEL = {"Soccer": "Football"}
SPORT_PREFIX = {
    "Soccer": "football",
    "Ice Hockey": "ice_hockey",
    "American Football": "american_football",
    "Basketball": "basketball",
}
SPORT_ICON = {
    "Soccer": "mdi:soccer",
    "Ice Hockey": "mdi:hockey-puck",
    "American Football": "mdi:football",
    "Basketball": "mdi:basketball",
    "Rugby": "mdi:rugby",
    "Baseball": "mdi:baseball",
    "Cricket": "mdi:cricket",
    "Australian Football": "mdi:football-australian",
    "Handball": "mdi:handball",
    "Volleyball": "mdi:volleyball",
    "Tennis": "mdi:tennis",
    "Golf": "mdi:golf",
}
DEFAULT_ICON = "mdi:scoreboard"

# How long a game runs, kick-off to final whistle, including the breaks (minutes): the sensor shows the game as
# in play for this long, then waits for TheSportsDB to post the result
GAME_MINUTES = {
    "Soccer": 120,
    "Ice Hockey": 170,
    "American Football": 210,
    "Basketball": 150,
    "Rugby": 120,
    "Baseball": 200,
    "Cricket": 480,
    "Australian Football": 150,
    "Handball": 110,
    "Volleyball": 130,
}
DEFAULT_GAME_MINUTES = 180
RESULT_WAIT_MINUTES = 30                 # after the expected end, "In play" becomes "Awaiting result"

# TheSportsDB status values of a finished game (seen: FT in every sport checked on 11 Oct 2026)
FINISHED_STATUSES = {"FT", "AET", "AOT", "AP", "PEN", "FT/OT", "FT/SO", "FT/PEN", "AWARDED", "FINISHED", "MATCH FINISHED", "FINAL", "F"}
CANCELLED_STATUSES = {"CANC", "CANCELLED", "CANCELED", "POSTP", "POSTP.", "POSTPONED", "ABD", "ABANDONED", "SUSP", "SUSPENDED", "WO", "WALKOVER"}

STATE_PRE = "PRE"
STATE_IN = "IN"
STATE_POST = "POST"
STATE_NOT_FOUND = "NOT_FOUND"
