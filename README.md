# HA Team Scores (TheSportsDB Tracker)

A Home Assistant integration that follows your teams on [TheSportsDB](https://www.thesportsdb.com): one sensor per
team with the next fixture (date and time, venue, both teams and their logos), then the full-time result. Football,
ice hockey, American football, basketball, rugby, baseball, cricket and any other team sport TheSportsDB lists, from
the big leagues down to the UK Elite Ice Hockey League, Norway's Fjordkraft-ligaen and Super League Basketball.

It brings its own Team Scores card, which lays every team's games out by day, and registers it with your dashboards
itself. One download, nothing else to install.

The free TheSportsDB key is enough. It has no live scores, so the sensor shows a game as in play from kick-off until
the clock says it is over, then the result once TheSportsDB posts it (usually within the hour).

## What you need

- Home Assistant 2025.1 or later.
- [HACS](https://hacs.xyz) installed.
- Nothing else. The free TheSportsDB key (`123`) is built in. A [premium key](https://www.thesportsdb.com/pricing)
  (USD 9 a month) allows more requests a minute and, for the leagues it covers, scores during the game.

## Install

1. In Home Assistant open **HACS**, then the three-dot menu at the top right, then **Custom repositories**.
2. Enter `https://github.com/TheMarkChristie/HATeamScores`, choose the type **Integration**, and select **Add**.
3. Search HACS for **TheSportsDB Tracker** and select **Download**.
4. Restart Home Assistant (**Settings > System**, then the power button at the top right, **Restart Home Assistant**).

The Team Scores card comes with the integration and is registered with your dashboards at that restart; nothing
else to install.

## Add a team

This works the same in a browser and in the Companion app on a phone.

1. Go to **Settings > Devices & services**, select **Add integration** (bottom right), and search for
   **TheSportsDB Tracker**.
2. **Find a team.** Type part of the team's name (for example `St Johnstone`, `Rosenborg`, `Seattle Kraken`). Choose
   the sport if the name is common (`Norway`, `Scotland`, `Liverpool` exist in several sports). Leave the key as `123`
   unless you have your own.
3. **Pick the team.** The matches are listed with their sport and league. Women's and youth teams say so.
4. **Name the sensor.** The name is what Home Assistant shows; the sensor's entity id is given on the page, for
   example `sensor.football_st_johnstone`. Select **Submit**.

Repeat for each team. A team cannot be added twice. Adding many teams in one go is fine: every team's reads go
through one paced client, and a refused request waits half a minute and tries again.

The integration carries its own icon (a scoreboard), which Home Assistant 2026.3 and later show in the integrations
list and on each team's device page.

### Options

Open **Settings > Devices & services > TheSportsDB Tracker**, find the team and select **Configure**:

| Option | Default | What it does |
|---|---|---|
| TheSportsDB API key | `123` | Your premium key, if you have one. Set it on each team you want it used for. |
| Show a result for (hours) | 24 | After full time the result stays on the sensor this long, then the next fixture shows. |
| Show the next fixture from (hours before kick-off) | 6 | The next fixture takes over this long before its kick-off, even if the result is still within its hours. |

## The Team Scores card

The integration brings its own card and registers it with your dashboards, so there is nothing more to install.
It lists every tracked team's games by day: yesterday's results, today, then the fixtures of the next two weeks.
Each row has the time, the two teams with their badges (your teams in bold), the score once it is in, and the venue
and competition underneath. It is laid out for a phone first.

Add it to a dashboard: **Edit dashboard > Add card**, search for **Team Scores**, or use **Manual** and paste:

```yaml
type: custom:team-scores-card
title: Scores
days_ahead: 14
results_days: 1
```

| Option | Default | What it does |
|---|---|---|
| `title` | none | A heading on the card |
| `days_ahead` | 14 | Fixtures up to this many days ahead |
| `results_days` | 1 | Results from this many days back (1 is yesterday and today) |
| `prefixes` | all teams | Only sensors whose id starts with one of these, for example `[sensor.football_]` for one sport |
| `entities` | all teams | Or an explicit list of sensors |
| `show_venue` | true | The venue under each row |
| `show_league` | true | The competition under each row |
| `show_tv` | true | The UK and Norwegian TV channels under each coming game |
| `tv_countries` | `[UK, NO]` | Which countries' channels to show, in this order |
| `layout` | `columns` | `columns` puts the days side by side when the card is wide enough (a tablet or desktop); `list` keeps one long column. A phone always shows one column |
| `day_width` | 300 | The narrowest a day column may be, in pixels |

A game in play shows `LIVE` in the time column; the score arrives with the result on the free key. A game both
your teams play (Liverpool v Manchester City) appears once.

On the free key TheSportsDB lists one coming fixture per team, so the two weeks ahead hold each team's next game.
With a premium key the list fills with everything TheSportsDB has scheduled.

### Which channel a game is on

Under each coming game the card shows its channels, UK first then Norway, for example `UK TNT Sports 1` and
`NO V sport Premier League 1`. Two sources are merged:

- **The TV guides.** Every six hours, one download for all teams: the UK guide published by
  [epgshare01](https://epgshare01.online/epgshare01/) (Sky Sports, TNT Sports, Premier Sports, BBC One Scotland, STV
  and the rest), and Allente's public TV guide for Norway (TV 2 Sport 1, 2 and Premium, Viaplay's V sport channels
  including V sport live 1-5, NRK1, NRK2, NRK3, Eurosport Norge). A channel is listed when its programme at kick-off
  names both teams in its title, for example `Live NFL Cowboys @ Packers` or `EHL: Vålerenga - Frisk Asker`. Goals
  shows, highlights, studios, radio, +1, subtitled and 4K copies, and the Danish and Swedish channels in Allente's
  list are left out. The guides reach about five or six days ahead, so channels appear as the game gets close.
- **TheSportsDB.** Its broadcaster list for the game, UK and Norway only, read twice a day per game. This adds
  streaming rights no guide carries, such as Amazon Prime Video. On the free key TheSportsDB returns two broadcasters
  from any country, so this part is thin; with a premium key it returns them all.

Not every game is listed anywhere. Services that sell events rather than run channels (DAZN, VG+ Sport, TV 2 Play's
extra streams) have no guide, and TheSportsDB's broadcaster data is crowd-sourced and often empty for Scottish and
Norwegian domestic games. The sensor carries the channels too: `tv` on each fixture, and `tv_network` for the game the
sensor shows.

### One sport per card

Give the card a `prefixes` list to show one sport. The prefixes are `sensor.football_` for soccer,
`sensor.ice_hockey_`, `sensor.american_football_`, `sensor.basketball_`, and the sport's name in lower case with
underscores for the rest (`sensor.rugby_`, `sensor.field_hockey_`).

```yaml
type: custom:team-scores-card
title: Football
prefixes:
  - sensor.football_
```

## The sensor

State: `PRE` (a fixture is coming), `IN` (the game is on), `POST` (a result) or `NOT_FOUND` (TheSportsDB lists
nothing for the team, for example in the off-season).

| Attribute | Meaning |
|---|---|
| `date` | Kick-off, ISO 8601 in UTC |
| `kickoff_in` | Kick-off for people, in your time zone: `Today 15:00`, `Tomorrow 19:30`, `Sat 18 Oct 15:00` (`PRE` only) |
| `venue`, `location`, `country` | Where the game is; `location` is `venue, country` |
| `team_name`, `team_abbr`, `team_logo`, `team_homeaway`, `team_score`, `team_winner` | Your team |
| `opponent_name`, `opponent_abbr`, `opponent_logo`, `opponent_homeaway`, `opponent_score`, `opponent_winner` | The other team |
| `clock` | `In play`, `Awaiting result`, `FT`, or `FT 24 Sep` for an old result |
| `league`, `league_logo`, `season`, `round`, `sport` | The competition |
| `event_name`, `event_id`, `event_url`, `video` | The game on TheSportsDB, and its highlights link when there is one |
| `fixtures` | Every coming game TheSportsDB lists, soonest first, each with `date`, `time`, `venue`, `league`, `home`, `away`, their badges and ids |
| `results` | The finished games the integration has seen, latest first, in the same shape with the scores and `finished: true` |
| `next_game`, `last_game` | The single game on the other side of the one shown, in the same shape |

`team_record`, `tv_network`, `odds`, `last_play` and `series_summary` are always empty: TheSportsDB does not carry
them. They are there so the sensor also fits scoreboard cards that expect them.

The entity's picture is the team's badge, so the sensor also looks right in an entities card or a tile.

## How it follows a game on the free key

The free key lists a team's next fixture, home or away, but its results list only has home games. So the
integration remembers each fixture as it appears, and once the kick-off has passed it looks that game up by its id
every ten minutes until TheSportsDB marks it full time. That is how away results come through. What it remembers is
saved in Home Assistant's storage, so a restart during a game loses nothing.

Three things follow from this:

- **Results from before a team was added** show only if the last game was at home.
- **No live scores.** During the game the sensor says `In play`; the score arrives with the result. With a premium
  key, scores TheSportsDB updates during a game (football, NFL, NBA, MLB, NHL) show as they come.
- **Requests stay well inside the limit.** Every team is checked every 30 minutes (every 10 while a game is on),
  through one shared, paced client. Twenty teams use about 40 requests an hour against the free key's 30 a minute.

## When a team is missing

TheSportsDB is community-edited, so lower leagues come and go. If a search finds nothing, look on
[thesportsdb.com](https://www.thesportsdb.com) itself: if the team is there, search here with the exact name shown.
If it is not there, anyone can add a team and its fixtures to TheSportsDB; the integration picks it up as soon as
the fixtures exist.

## Troubleshooting

- **"TheSportsDB did not answer."** The free key is shared by everyone who uses it, and TheSportsDB answers
  `429 Too Many Requests` under load. Wait a minute and try again.
- **The sensor is `NOT_FOUND`.** TheSportsDB has no coming fixture and no past result for the team. Off-season
  teams sit here until their new schedule is published.
- **A game is over but the sensor says `Awaiting result`.** TheSportsDB has not posted the score yet. The integration
  keeps checking every ten minutes for a day.
- **Logs.** Warnings from the integration appear under **Settings > System > Logs**, filtered for
  `sportsdb_tracker`.

## Data and licence

Data provided by [TheSportsDB.com](https://www.thesportsdb.com), whose terms ask for that line on free use; each
sensor carries it as its attribution.

MIT licence. Copyright (c) 2026 Mark Christie.
