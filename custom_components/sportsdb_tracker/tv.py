"""Which UK and Norwegian TV channels show a game: pure functions, no Home Assistant, tested in tests/test_tv.py.

Two sources, merged per game: the TV guides below, and TheSportsDB's broadcaster list (sportsdb_listings), which adds
streaming rights that no guide carries.

  UK      epgshare01's free XMLTV guide (rebuilt daily, about six days ahead): Sky Sports, TNT Sports, Premier Sports,
          BBC One Scotland, BBC Scotland, STV and the rest.
  Norway  Allente's public TV guide (one JSON file per day, about five days ahead): TV 2 Sport 1, 2 and Premium,
          Viaplay's V sport 1, 2, 3, V sport+, V sport Premier League 1-4 and V sport live 1-5, NRK, Eurosport Norge.

A channel shows a game when its programme is on air at kick-off and its title (or episode title) names both teams;
a description counts only for a programme whose title says it is live and is not a goals show or round-up. Services
that sell events rather than run channels (Prime Video, DAZN, TV 2 Play, VG+) have no guide; they appear only when
TheSportsDB lists them.
"""
from __future__ import annotations

import gzip
import io
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any, Iterable

UTC = timezone.utc

# guide programmes that overlap kick-off: starting no later than this after it, and still on this long after it
STARTS_BY = timedelta(minutes=15)
STILL_ON = timedelta(minutes=20)
STARTS_FROM = timedelta(hours=3)           # a programme that began earlier than this is a long block, not the game

# ---- channel names ------------------------------------------------------------------------------------------------

# the UK guide's terse names for the channels people actually say out loud
CHANNEL_NAMES = {
    "skyspmainev": "Sky Sports Main Event", "skysp pl": "Sky Sports Premier League", "skysp fball": "Sky Sports Football",
    "sky sports football": "Sky Sports Football", "skysp action": "Sky Sports Action", "skysp mix": "Sky Sports Mix",
    "skysp+": "Sky Sports+", "skyspcricket": "Sky Sports Cricket", "skysp cricket": "Sky Sports Cricket",
    "skysp f1": "Sky Sports F1", "skysp golf": "Sky Sports Golf", "skysp racing": "Sky Sports Racing",
    "skysp tennis": "Sky Sports Tennis", "skysp news": "Sky Sports News", "skyspboxoff": "Sky Sports Box Office",
    "sky sports nfl": "Sky Sports NFL", "tntsboxoff2": "TNT Sports Box Office 2", "tnt sport boxoffice": "TNT Sports Box Office",
    "bbc one scot": "BBC One Scotland", "bbcscotland": "BBC Scotland", "bbc alba": "BBC Alba",
}
# not television, a repeat an hour later, or a 4K copy of another channel
_NOT_TV = re.compile(r"(^|\.)(bbc\.r[\w.]*|talksport[\w.]*|radio[\w.]*)|\+1\b|\.\+1\.|ginx|esports|ultimate|ultra\.?hd|uhd", re.I)


def channel_name(display: str) -> str:
    """A UK guide's channel name as people say it: 'SkySpMainEvHD' is 'Sky Sports Main Event', 'TNT Sports 1 HD' is
    'TNT Sports 1'."""
    name = re.sub(r"\s*(UHD|HD)$", "", display.strip()).strip()
    key = name.lower()
    for short, full in CHANNEL_NAMES.items():
        if key == short or key.replace(" ", "") == short.replace(" ", ""):
            return full
    return name


# the UK guide carries Irish channels too (Virgin Media Two shows the NFL in Ireland, not the UK)
_IRISH = re.compile(r"^(rte|virgin\.?media|tg4|irish)", re.I)


def guide_channel_wanted(channel_id: str) -> bool:
    return not _NOT_TV.search(channel_id) and not _IRISH.search(channel_id)


# Allente sells to Norway but carries Danish, Swedish and Finnish channels too, NRK1 in every region, and copies with
# subtitles or sign language: one name per Norwegian channel
_ALLENTE_FOREIGN = re.compile(r"\((D|S|F|DK|SE|FI)\)\s*$|^(yle|svt\d?|dr\d?|tv4|kanal 5|tv3 sport|kunskapskanalen)\b|sverige", re.I)
_ALLENTE_COPY = re.compile(r"lydtekst|tegnspr|tekst h.rsel|\bultra\b|\buhd\b", re.I)


def allente_channel_name(name: str) -> str | None:
    """Allente's channel name as people say it, or None for a channel that is not wanted: 'V sport 1 HD (N)' is
    'V sport 1', 'NRK1 Midtnytt' is 'NRK1', 'NRK Super / NRK3 HD' is 'NRK3', 'TV 2 HD (D)' is Danish and left out."""
    n = name.strip()
    if _ALLENTE_FOREIGN.search(n) or _ALLENTE_COPY.search(n):
        return None
    n = re.sub(r"\s*\(N\)\s*$", "", n)
    n = re.sub(r"\s+(UHD|HD)$", "", n).strip()
    if re.match(r"NRK1\b", n):
        return "NRK1"
    if "NRK3" in n:
        return "NRK3"
    return re.sub(r"\s*\+\s*", "+", n) if n.lower().startswith("v sport") else n


# ---- reading the guides -------------------------------------------------------------------------------------------

_MATCHLIKE = re.compile(r"\w[\w.')]*\s+(v|vs|v\.|@|-|–)\s+\w", re.I)
_LIVE = re.compile(r"\b(live|direkte)\b", re.I)
# a live programme about many games, not one: its description names games it does not show
_ROUNDUP = re.compile(r"goals?|highlights|round-?up|review|studio|netbusters|magazine|preview|extra|xtra|weekly|oppsummering|mål", re.I)


@dataclass
class Programme:
    start: datetime
    stop: datetime
    channel: str          # the name people use
    country: str          # UK or NO
    head: str             # title and episode title, folded for matching
    desc: str = ""        # the description, folded; kept only for a live programme that is not a round-up
    live: bool = False    # the title says live or direkte, and it is not a goals show, highlights, studio or round-up


def _programme(start: datetime, stop: datetime, channel: str, country: str, title: str, sub: str, desc: str) -> Programme | None:
    if not _MATCHLIKE.search(f"{title} {sub} {desc}"):
        return None
    live = bool(_LIVE.search(title)) and not _ROUNDUP.search(f"{title} {sub}")
    return Programme(start, stop, channel, country, fold(f"{title} {sub}"), fold(desc) if live else "", live)


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip()
    for parse in (lambda s: datetime.strptime(s, "%Y%m%d%H%M%S %z"), datetime.fromisoformat,
                  lambda s: datetime.strptime(s[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)):
        try:
            d = parse(v)
            return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC)
        except ValueError:
            continue
    return None


def parse_xmltv(data: bytes, country: str, now: datetime | None = None, days: int = 8) -> list[Programme]:
    """The programmes of an XMLTV guide (gzipped or plain) that could be a game, from now to `days` ahead. Read as a
    stream, so a 40,000-programme guide never sits in memory whole."""
    raw = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
    now = now or datetime.now(UTC)
    end = now + timedelta(days=days)
    names: dict[str, str] = {}
    out: list[Programme] = []
    for _ev, el in ET.iterparse(io.BytesIO(raw), events=("end",)):
        if el.tag == "channel":
            cid = el.get("id") or ""
            if guide_channel_wanted(cid):
                names[cid] = channel_name(el.findtext("display-name") or cid)
            el.clear()
        elif el.tag == "programme":
            cid = el.get("channel") or ""
            if cid in names:
                start, stop = _time(el.get("start")), _time(el.get("stop"))
                if start and stop and stop > now - timedelta(hours=6) and start < end:
                    p = _programme(start, stop, names[cid], country, el.findtext("title") or "", el.findtext("sub-title") or "",
                                   el.findtext("desc") or "")
                    if p:
                        out.append(p)
            el.clear()
    return out


def parse_allente(days: Iterable[bytes], now: datetime | None = None) -> list[Programme]:
    """Allente's guide, one JSON file per day: the Norwegian channels' programmes that could be a game."""
    now = now or datetime.now(UTC)
    out: list[Programme] = []
    seen: set[tuple[str, str]] = set()
    for data in days:
        try:
            doc = json.loads(data)
        except ValueError:
            continue
        channels = doc.get("channels") if isinstance(doc, dict) else None
        for ch in channels or []:
            name = allente_channel_name(str(ch.get("name") or ""))
            if not name:
                continue
            for p in ch.get("programs") or []:
                start, stop = _time(p.get("eventStart")), _time(p.get("eventEnd"))
                if not start or not stop or stop <= now - timedelta(hours=6):
                    continue
                key = (name, start.isoformat())
                if key in seen:                      # the same programme on a day's edge, or a regional NRK1
                    continue
                prog = _programme(start, stop, name, "NO", str(p.get("title") or ""), "", str(p.get("shortDescription") or ""))
                if prog:
                    seen.add(key)
                    out.append(prog)
    return out


# ---- team names ---------------------------------------------------------------------------------------------------

_FOLD = str.maketrans({"æ": "ae", "ø": "o", "å": "a", "ß": "ss", "&": " and ", "'": "", "’": ""})


def fold(text: str) -> str:
    """Lower case, accents gone (Vålerenga is valerenga), punctuation as spaces."""
    t = text.lower().translate(_FOLD)
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " " + re.sub(r"[^a-z0-9]+", " ", t).strip() + " "


# words that say nothing about which team it is
_GENERIC = {"fc", "afc", "cf", "sc", "il", "bk", "fk", "sk", "if", "hc", "ihc", "bc", "ac", "as", "ss", "sv", "the", "and", "of",
            "club", "city", "united", "utd", "town", "rovers", "athletic", "county", "albion", "wanderers", "hotspur", "basket",
            "basketball", "football", "hockey", "ishockey", "manchester", "sheffield", "bristol", "nottingham", "real", "sporting",
            # a side or a squad, not a team: Chelsea Women, Hammarby Damer, Real Madrid II
            "women", "womens", "ladies", "kvinner", "dam", "damer", "ii", "iii", "u17", "u19", "u20", "u21", "u23", "reserves",
            "academy", "rugby", "rfc", "rlfc", "league"}
# what the guides call teams whose full names they never print
_ALIASES = {
    "manchester city": ["man city"], "manchester united": ["man utd", "man united", "manchester utd"],
    "tottenham hotspur": ["spurs", "tottenham"], "wolverhampton wanderers": ["wolves"], "brighton and hove albion": ["brighton"],
    "west ham united": ["west ham"], "newcastle united": ["newcastle"], "leeds united": ["leeds"],
    "nottingham forest": ["nottm forest", "nott m forest", "nottingham f"], "sheffield united": ["sheff utd", "sheffield utd"],
    "sheffield wednesday": ["sheff wed"], "queens park rangers": ["qpr"], "paris saint germain": ["psg", "paris sg"],
    "internazionale": ["inter", "inter milan"], "bayern munich": ["bayern"], "borussia dortmund": ["dortmund"],
    "atletico madrid": ["atletico"], "glasgow rangers": ["rangers"], "celtic glasgow": ["celtic"],
    # national teams as the Norwegian guide writes them
    "norway": ["norge"], "scotland": ["skottland"], "sweden": ["sverige"], "denmark": ["danmark"], "germany": ["tyskland"],
    "spain": ["spania"], "italy": ["italia"], "france": ["frankrike"], "netherlands": ["nederland"], "belgium": ["belgia"],
    "switzerland": ["sveits"], "austria": ["osterrike"], "poland": ["polen"], "croatia": ["kroatia"], "iceland": ["island"],
    "ireland": ["irland"], "republic of ireland": ["irland"], "northern ireland": ["nord irland"], "north macedonia": ["nord makedonia"],
    "czech republic": ["tsjekkia"], "czechia": ["tsjekkia"], "turkey": ["tyrkia"], "turkiye": ["tyrkia"], "greece": ["hellas"],
    "ukraine": ["ukraina"], "hungary": ["ungarn"], "estonia": ["estland"], "lithuania": ["litauen"], "cyprus": ["kypros"],
    "kazakhstan": ["kasakhstan"], "england": ["england"], "wales": ["wales"],
}
_US_SPORTS = {"American Football", "Ice Hockey", "Basketball", "Baseball"}


def team_needles(name: str, sport: str | None = None, extra: Iterable[str] = ()) -> list[str]:
    """The ways a guide might write a team: the full name, without FC and the like, the usual short forms, its
    distinctive words (Rosenborg, Villarreal), its own capitals (AEK), and for North American sports the nickname
    (Cowboys, Red Wings)."""
    full = fold(name).strip()
    words = full.split()
    needles = {full, " ".join(w for w in words if w not in {"fc", "afc", "cf", "sc", "il", "bk", "fk", "if", "hc", "bc"})}
    needles.update(_ALIASES.get(full, []))
    for e in extra:
        if e and e.strip():
            needles.add(fold(e).strip())
    needles.update(w for w in words if len(w) >= 4 and w not in _GENERIC)
    needles.update(fold(w).strip() for w in re.split(r"[\s\-./]+", name)
                   if 2 <= len(w) <= 4 and w.isupper() and w.isalpha() and fold(w).strip() not in _GENERIC)   # AEK, PSG; never FC or BK
    if sport in _US_SPORTS and len(words) >= 2:
        needles.add(words[-1])
        needles.add(" ".join(words[-2:]))
    return sorted((n for n in needles if n and len(n) >= 2), key=len, reverse=True)


def pair_needles(home: str, away: str, sport: str | None = None, home_extra: Iterable[str] = (),
                 away_extra: Iterable[str] = ()) -> tuple[list[str], list[str]]:
    """Both teams' needles, without the words they share: in Makkabi Berlin v Füchse Berlin, "berlin" names neither."""
    h = team_needles(home, sport, home_extra)
    a = team_needles(away, sport, away_extra)
    shared = set(h) & set(a)
    return [n for n in h if n not in shared] or h, [n for n in a if n not in shared] or a


def names_team(text: str, needles: Iterable[str]) -> bool:
    """Whether a folded text names the team: a needle as whole words, or a word of six letters or more by its first
    five (the Norwegian 'AEK Athen' for AEK Athens). Both teams must be named, at kick-off, so this is safe."""
    for n in needles:
        if f" {n} " in text:
            return True
        if " " not in n and len(n) >= 6 and re.search(rf" {re.escape(n[:5])}[a-z]* ", text):
            return True
    return False


# ---- matching -----------------------------------------------------------------------------------------------------

def guide_listings(start: datetime, home: list[str], away: list[str], programmes: Iterable[Programme]) -> list[dict[str, str]]:
    """The channels whose programme at kick-off names both teams, once per channel, UK first then Norway."""
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for p in programmes:
        if not (start - STARTS_FROM <= p.start <= start + STARTS_BY and p.stop >= start + STILL_ON):
            continue
        named = names_team(p.head, home) and names_team(p.head, away)
        if not named and p.live:        # "Live UEFA Champions League" with the teams in the description
            named = names_team(p.desc, home) and names_team(p.desc, away)
        if named:
            key = (p.country, p.channel.lower())
            if key not in seen:
                seen.add(key)
                out.append({"channel": p.channel, "country": p.country, "source": "guide"})
    order = {"UK": 0, "NO": 1}
    return sorted(out, key=lambda i: order.get(i["country"], 9))


# ---- TheSportsDB's broadcasters -------------------------------------------------------------------------------------

# TheSportsDB country names, and the short labels the card shows
COUNTRY_LABEL = {"United Kingdom": "UK", "England": "UK", "Scotland": "UK", "Norway": "NO"}


def sportsdb_listings(rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """TheSportsDB's broadcasters for a game (lookuptv), the UK and Norwegian ones only. This is how streaming rights
    that no guide carries get listed (Prime Video). The free key returns two broadcasters from any country; a premium
    key returns them all."""
    out: list[dict[str, str]] = []
    for r in rows or []:
        country = COUNTRY_LABEL.get(str(r.get("strCountry") or "").strip())
        channel = str(r.get("strChannel") or "").strip()
        if country and channel and not re.search(r"\b(ultimate|ultra hd|uhd|4k)\b", channel, re.I):   # 4K copies, as in the guides
            channel = re.sub(r"\s+(UK|Norway|Norge)$", "", channel)
            out.append({"channel": channel, "country": country, "source": "thesportsdb"})
    return out


def merge(*lists: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """One list, UK first then Norway, each channel once (the guide's name wins)."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for lst in lists:
        for item in lst:
            key = (item["country"], fold(item["channel"]).replace(" ", ""))
            if key not in seen:
                seen.add(key)
                out.append(item)
    order = {"UK": 0, "NO": 1}
    return sorted(out, key=lambda i: order.get(i["country"], 9))


def with_defaults(listings: list[dict[str, str]], league_id: str | None, league: str | None,
                  defaults: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """A league's usual channel for a country (Eliteserien: TV 2 in Norway), added only when nothing was found for
    that country: a channel the guide names for the game (TV 2 Sport 1) is more exact and wins."""
    out = list(listings)
    have = {i["country"] for i in out}
    name = (league or "").strip().lower()
    for d in defaults:
        hit = (league_id and str(d.get("league_id") or "") == str(league_id)) or (name and str(d.get("league") or "").strip().lower() == name)
        if hit and d["country"] not in have:
            out.append({"channel": d["channel"], "country": d["country"], "source": "default"})
            have.add(d["country"])
    order = {"UK": 0, "NO": 1}
    return sorted(out, key=lambda i: order.get(i["country"], 9))


# ---- today on TV ----------------------------------------------------------------------------------------------------

def today_on_tv(events: Iterable[dict[str, Any]], programmes: list[Programme], day: date, tz: tzinfo,
                defaults: Iterable[dict[str, str]] = ()) -> list[dict[str, Any]]:
    """Every game of the local `day` (TheSportsDB's eventsday records, any sport) that a UK or Norwegian channel shows
    live: on air at kick-off and naming both teams, the same rule as a fixture's channels, or in a league whose usual
    channel is known (`defaults`, as for a fixture). Soonest first, each game once."""
    defaults = list(defaults)
    lo = datetime.combine(day, time.min, tz).astimezone(UTC) - STARTS_FROM
    hi = datetime.combine(day + timedelta(days=1), time.min, tz).astimezone(UTC)
    todays = sorted((p for p in programmes if lo <= p.start < hi), key=lambda p: p.start)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e in events or []:
        eid = str(e.get("idEvent") or "")
        ts = e.get("strTimestamp")
        if not eid or eid in seen or not ts:
            continue
        try:
            start = datetime.fromisoformat(str(ts))
        except ValueError:
            continue
        start = (start if start.tzinfo else start.replace(tzinfo=UTC)).astimezone(UTC)
        if start.astimezone(tz).date() != day:
            continue
        seen.add(eid)
        home, away = str(e.get("strHomeTeam") or ""), str(e.get("strAwayTeam") or "")
        if not home or not away:
            continue
        h, a = pair_needles(home, away, e.get("strSport"))
        window = [p for p in todays if start - STARTS_FROM <= p.start <= start + STARTS_BY]
        found = with_defaults(guide_listings(start, h, a, window), e.get("idLeague"), e.get("strLeague"), defaults)
        if found:
            out.append({"event_id": eid, "date": start.isoformat(), "sport": e.get("strSport"), "league": e.get("strLeague"),
                        "league_logo": e.get("strLeagueBadge"), "home": home, "away": away, "home_id": e.get("idHomeTeam"),
                        "away_id": e.get("idAwayTeam"), "home_badge": e.get("strHomeTeamBadge"), "away_badge": e.get("strAwayTeamBadge"),
                        "tv": found})
    return sorted(out, key=lambda g: g["date"])
