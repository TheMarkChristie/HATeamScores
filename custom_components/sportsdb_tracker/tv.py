"""Which UK and Norwegian TV channels show a game: pure functions, no Home Assistant, tested in tests/test_tv.py.

Two sources, merged per game:

  the TV guides   epgshare01's free XMLTV files for the UK and Norway (rebuilt daily, a few days ahead). A programme
                  shows a game when it is on air at kick-off and its title, episode title or description names both
                  teams. That finds every linear channel: Sky Sports, TNT Sports, Premier Sports, BBC, STV, V sport,
                  TV 2 Sport, NRK, Eurosport.
  TheSportsDB     its per-game broadcaster list (lookuptv), filtered to the United Kingdom and Norway. That adds
                  streaming rights no guide carries (Prime Video, TV 2 Play). The free key returns two broadcasters
                  from any country; a premium key returns them all.
"""
from __future__ import annotations

import gzip
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

UTC = timezone.utc

# TheSportsDB country names, and the short labels the card shows
COUNTRY_LABEL = {"United Kingdom": "UK", "England": "UK", "Scotland": "UK", "Norway": "NO"}

# guide programmes that overlap kick-off: starting no later than this after it, and still on this long after it
STARTS_BY = timedelta(minutes=15)
STILL_ON = timedelta(minutes=20)
STARTS_FROM = timedelta(hours=3)           # a programme that began earlier than this is a long block, not the game

# ---- channel names ------------------------------------------------------------------------------------------------

# the guides' terse names for the channels people actually say out loud
CHANNEL_NAMES = {
    "skyspmainev": "Sky Sports Main Event", "skysp pl": "Sky Sports Premier League", "skysp fball": "Sky Sports Football",
    "sky sports football": "Sky Sports Football", "skysp action": "Sky Sports Action", "skysp mix": "Sky Sports Mix",
    "skysp+": "Sky Sports+", "skyspcricket": "Sky Sports Cricket", "skysp cricket": "Sky Sports Cricket",
    "skysp f1": "Sky Sports F1", "skysp golf": "Sky Sports Golf", "skysp racing": "Sky Sports Racing",
    "skysp tennis": "Sky Sports Tennis", "skysp news": "Sky Sports News", "skyspboxoff": "Sky Sports Box Office",
    "sky sports nfl": "Sky Sports NFL", "tntsboxoff2": "TNT Sports Box Office 2", "tnt sport boxoffice": "TNT Sports Box Office",
    "bbc one scot": "BBC One Scotland", "bbcscotland": "BBC Scotland", "bbc alba": "BBC Alba",
    "eurosport n": "Eurosport Norge", "viasport 1": "V sport 1", "viasport 2": "V sport 2", "viasport 3": "V sport 3",
    "viasport+": "V sport+",
}
# not television, or a repeat an hour later
_NOT_TV = re.compile(r"(^|\.)(bbc\.r[\w.]*|talksport[\w.]*|radio[\w.]*)|\+1\b|\.\+1\.|ginx|esports|ultimate|ultra\.?hd|uhd", re.I)


def channel_name(display: str) -> str:
    """A guide's channel name as people say it: 'SkySpMainEvHD' is 'Sky Sports Main Event', 'TNT Sports 1 HD' is
    'TNT Sports 1', 'V sport Premier League 1 Norway (NO,NO)' is 'V sport Premier League 1'."""
    name = re.sub(r"\s*\([A-Z]{2},[A-Z]{2}\)\s*$", "", display.strip())          # (NO,NO)
    name = re.sub(r"\s+(Norway|Norge|UK)$", "", name)
    name = re.sub(r"\s*(UHD|HD)$", "", name).strip()
    key = name.lower()
    for short, full in CHANNEL_NAMES.items():
        if key == short or key.replace(" ", "") == short.replace(" ", ""):
            return full
    return name


def guide_channel_wanted(channel_id: str, country: str) -> bool:
    """Television channels of the guide's own country: the Norwegian file also carries Danish and Swedish channels."""
    if _NOT_TV.search(channel_id):
        return False
    if country == "NO":
        return "norway" in channel_id.lower() or "(no,no)" in channel_id.lower()
    return True


# ---- reading a guide ------------------------------------------------------------------------------------------------

_MATCHLIKE = re.compile(r"\w[\w.')]*\s+(v|vs|v\.|@|-|–)\s+\w", re.I)
_LIVE = re.compile(r"\b(live|direkte)\b", re.I)
# a live programme that is about many games, not one: its description names games it does not show
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


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y%m%d%H%M%S %z").astimezone(UTC)
    except ValueError:
        try:
            return datetime.strptime(value.strip()[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            return None


def parse_guide(data: bytes, country: str, now: datetime | None = None, days: int = 8) -> list[Programme]:
    """The programmes of an XMLTV guide (gzipped or plain) that could be a game: on a wanted channel, from now to
    `days` ahead, with something like "A v B" in the title, episode title or description. Read as a stream, so a
    40,000-programme guide never sits in memory whole."""
    raw = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
    now = now or datetime.now(UTC)
    end = now + timedelta(days=days)
    names: dict[str, str] = {}
    out: list[Programme] = []
    for _ev, el in ET.iterparse(io.BytesIO(raw), events=("end",)):
        if el.tag == "channel":
            cid = el.get("id") or ""
            if guide_channel_wanted(cid, country):
                names[cid] = channel_name(el.findtext("display-name") or cid)
            el.clear()
        elif el.tag == "programme":
            cid = el.get("channel") or ""
            if cid in names:
                start, stop = _time(el.get("start")), _time(el.get("stop"))
                if start and stop and stop > now - timedelta(hours=6) and start < end:
                    title, sub, desc = el.findtext("title") or "", el.findtext("sub-title") or "", el.findtext("desc") or ""
                    if _MATCHLIKE.search(f"{title} {sub} {desc}"):
                        live = bool(_LIVE.search(title)) and not _ROUNDUP.search(f"{title} {sub}")
                        out.append(Programme(start, stop, names[cid], country, fold(f"{title} {sub}"), fold(desc) if live else "", live))
            el.clear()
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
            "basketball", "football", "hockey", "ishockey", "manchester", "sheffield", "bristol", "nottingham", "real", "sporting"}
# what the guides call teams whose full names they never print
_ALIASES = {
    "manchester city": ["man city"], "manchester united": ["man utd", "man united", "manchester utd"],
    "tottenham hotspur": ["spurs", "tottenham"], "wolverhampton wanderers": ["wolves"], "brighton and hove albion": ["brighton"],
    "west ham united": ["west ham"], "newcastle united": ["newcastle"], "leeds united": ["leeds"],
    "nottingham forest": ["nottm forest", "nott m forest", "nottingham f"], "sheffield united": ["sheff utd", "sheffield utd"],
    "sheffield wednesday": ["sheff wed"], "queens park rangers": ["qpr"], "paris saint germain": ["psg", "paris sg"],
    "internazionale": ["inter", "inter milan"], "bayern munich": ["bayern"], "borussia dortmund": ["dortmund"],
    "atletico madrid": ["atletico"], "glasgow rangers": ["rangers"], "celtic glasgow": ["celtic"],
}
_US_SPORTS = {"American Football", "Ice Hockey", "Basketball", "Baseball"}


def team_needles(name: str, sport: str | None = None, extra: Iterable[str] = ()) -> list[str]:
    """The ways a guide might write a team: the full name, without FC and the like, the usual short forms, its
    distinctive words (Rosenborg, Villarreal), and for North American sports the nickname (Cowboys, Red Wings)."""
    full = fold(name).strip()
    words = full.split()
    needles = {full, " ".join(w for w in words if w not in {"fc", "afc", "cf", "sc", "il", "bk", "fk", "if", "hc", "bc"})}
    needles.update(_ALIASES.get(full, []))
    for e in extra:
        if e and e.strip():
            needles.add(fold(e).strip())
    needles.update(w for w in words if len(w) >= 4 and w not in _GENERIC)
    # an all-capitals short name in the original is the team's own short form: AEK, PSG, QPR
    needles.update(fold(w).strip() for w in re.split(r"[\s\-./]+", name) if 2 <= len(w) <= 4 and w.isupper() and w.isalpha())
    if sport in _US_SPORTS and len(words) >= 2:
        needles.add(words[-1])
        needles.add(" ".join(words[-2:]))
    return sorted((n for n in needles if n and len(n) >= 3), key=len, reverse=True)


def names_team(text: str, needles: Iterable[str]) -> bool:
    """Whether a folded text names the team: a needle as whole words, or a word of six letters or more by its first
    five (the Norwegian guide's 'AEK Athen' for AEK Athens). Both teams must be named, at kick-off, so this is safe."""
    for n in needles:
        if f" {n} " in text:
            return True
        if " " not in n and len(n) >= 6 and re.search(rf" {re.escape(n[:5])}[a-z]* ", text):
            return True
    return False


# ---- matching -----------------------------------------------------------------------------------------------------

def guide_listings(start: datetime, home: list[str], away: list[str], programmes: Iterable[Programme]) -> list[dict[str, str]]:
    """The channels whose programme at kick-off names both teams, once per channel."""
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
    return out


def sportsdb_listings(rows: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """TheSportsDB's broadcasters for a game, the UK and Norwegian ones only."""
    out: list[dict[str, str]] = []
    for r in rows or []:
        country = COUNTRY_LABEL.get(str(r.get("strCountry") or "").strip())
        channel = str(r.get("strChannel") or "").strip()
        if country and channel:
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
