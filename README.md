# HA Team Scores (TheSportsDB Tracker)

A Home Assistant integration that follows your teams on [TheSportsDB](https://www.thesportsdb.com): one sensor per
team with the next fixture (date and time, venue, both teams and their logos), then the full-time result. Football,
ice hockey, American football, basketball, rugby, baseball, cricket and any other team sport TheSportsDB lists, from
the big leagues down to the UK Elite Ice Hockey League, Norway's Fjordkraft-ligaen and Super League Basketball.

The sensors use the same shape as the [Team Tracker](https://github.com/vasqued2/ha-teamtracker) integration, so the
[TeamTracker Scoreboard Card](https://github.com/marcintk/ha-teamtracker-scoreboard-card) shows them as a scoreboard,
grouped by sport.

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

To see the sensors as a scoreboard, also install the card:

5. In HACS, search for **TeamTracker Scoreboard Card** and select **Download**. HACS registers the card's resource
   itself. Reload the browser once (or the Companion app) after installing it.

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

Repeat for each team. A team cannot be added twice.

### Options

Open **Settings > Devices & services > TheSportsDB Tracker**, find the team and select **Configure**:

| Option | Default | What it does |
|---|---|---|
| TheSportsDB API key | `123` | Your premium key, if you have one. Set it on each team you want it used for. |
| Show a result for (hours) | 24 | After full time the result stays on the sensor this long, then the next fixture shows. |
| Show the next fixture from (hours before kick-off) | 6 | The next fixture takes over this long before its kick-off, even if the result is still within its hours. |

## The scoreboard

Add the card to a dashboard: **Edit dashboard > Add card > Manual**, paste this, and change the sections to the
sports you track. Every section lists the sensors whose entity id starts with its prefix.

```yaml
type: custom:ha-teamtracker-scoreboard-card
name_format: name
live_first: true
tv_badge: 0
sections:
  - name: Football
    prefix: sensor.football_
    limit: 20
  - name: Ice Hockey
    prefix: sensor.ice_hockey_
    limit: 20
  - name: American Football
    prefix: sensor.american_football_
    limit: 20
  - name: Basketball
    prefix: sensor.basketball_
    limit: 20
```

Each row shows the two teams with their logos. Before the game it shows the kick-off (`Today 15:00`,
`Sat 18 Oct 19:30`) and the venue; during the game, `In play`; afterwards, the score and `Full Time`. A result with
nothing coming up shows its date (`FT 24 Sep`).

The prefixes are: `football_` for soccer, `ice_hockey_`, `american_football_`, `basketball_`, and the sport's name in
lower case with underscores for the rest (`rugby_`, `field_hockey_`). The card's other options (colours, layout,
slide mode) are in its [README](https://github.com/marcintk/ha-teamtracker-scoreboard-card).

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
| `next_game` | While a result shows: the next fixture (`name`, `date`, `when`, `venue`, `home`, `away`) |
| `last_game` | While a fixture shows: the last result (`name`, `date`, `venue`, `home_score`, `away_score`) |

`team_record`, `tv_network`, `odds`, `last_play` and `series_summary` are present for the card and always empty:
TheSportsDB does not carry them.

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

## Credits and licence

Data provided by [TheSportsDB.com](https://www.thesportsdb.com). Card by
[marcintk](https://github.com/marcintk/ha-teamtracker-scoreboard-card); attribute shape after
[vasqued2's Team Tracker](https://github.com/vasqued2/ha-teamtracker).

MIT licence. Copyright (c) 2026 Mark Christie.
