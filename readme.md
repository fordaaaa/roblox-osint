# Roblox OSINT

Social-graph analysis for **public** Roblox accounts, built for trust & safety
style work: spotting bot farms and alt-account rings, mapping how a scam or
spam network is connected, and checking whether two accounts share a circle.

It pulls only what Roblox already exposes publicly (profiles, friend lists,
follows), builds a graph with `networkx`, runs community detection, and can
render the result as an interactive mind-map in your browser.

## Scope and ethics

This is an analysis tool for public data, not a stalking tool.

- **Public data only.** It calls Roblox's public web API. It doesn't bypass
  privacy settings, scrape private messages, or touch anything an account has
  hidden. A private friends list stays private.
- **Investigate networks, not people.** The intended targets are suspicious
  clusters: bot farms, mass-created alts, scam rings. Don't use it to track,
  harass, or dox an individual.
- **Respect the platform.** Keep crawl depth low, don't hammer the API, and
  follow Roblox's Terms of Use.
- **Your cookie is a password.** The follower/following commands need a
  `.ROBLOSECURITY` cookie. Use a throwaway account, never commit it, and never
  paste it anywhere you don't control.

## Setup

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

There are three dependencies: `httpx`, `networkx`, and `python-louvain`. Most
commands need no API keys.

## Usage

```bash
venv/bin/python3 cli.py <command> <username> [options]
```

| Command | What it does |
|---|---|
| `profile <user> [--json]` | Account age, friend/follower/following counts, groups, badges, presence |
| `friends <user>` | List the user's public friends |
| `circle <user> [--open]` | Friend-group clusters (Louvain community detection) |
| `explore <user> [--depth 1-3] [--open]` | Crawl the friend network N hops out and report its size |
| `followers <user> [--open]` | List followers *(needs `ROBLOX_COOKIE`)* |
| `following <user> [--open]` | List who the user follows *(needs `ROBLOX_COOKIE`)* |
| `compare <user1> <user2> [--open]` | Mutual friends, who-only-knows-who, and degrees of separation |
| `alts <user> [--window DAYS] [--min-size N]` | Flag friends created in tight time windows (possible alt/bot clusters) |

`--open` writes a self-contained HTML mind-map (graph data embedded, no server)
and opens it in your browser.

### Examples

```bash
venv/bin/python3 cli.py profile Linkmon99
venv/bin/python3 cli.py circle Linkmon99 --open
venv/bin/python3 cli.py explore shedletsky --depth 2
venv/bin/python3 cli.py compare shedletsky Linkmon99
venv/bin/python3 cli.py alts shedletsky --window 30 --min-size 3
```

## Web UI

There's also a small local web UI for clicking through the same data:

```bash
venv/bin/python3 server.py   # then open http://127.0.0.1:7390
```

It binds to `127.0.0.1` only and uses the same API client and graph code as
the CLI.

## How `alts` works

Bot farms and alt rings are usually created in batches. `alts` takes a user's
friends, sorts them by account creation date, and groups accounts created
within `--window` days of each other. Groups of at least `--min-size` are
reported as possible coordinated accounts.

This is a heuristic. A group of real friends who all joined the same week will
also trigger it, so treat the output as a lead to check, not a verdict.

## Notes

- **Private friends lists look empty.** When Roblox returns nothing, the tool
  prints a `(!)` note that the list is private or empty. That isn't an error.
- **Followers/following need a login cookie.** Roblox gates those endpoints
  behind a session:

  ```bash
  export ROBLOX_COOKIE="<.ROBLOSECURITY value from a throwaway account>"
  venv/bin/python3 cli.py followers Linkmon99
  ```

  The cookie also raises rate limits on every command.
- **Rate limiting.** Unauthenticated traffic gets throttled. If results come
  back thin after a big `explore`, wait a few seconds and retry. Failed fetches
  aren't cached, so a retry really does re-fetch.

## Project layout

```
cli.py           # command-line entry point (alts logic lives here)
server.py        # local web UI (127.0.0.1:7390)
ui.html          # front end for the web UI
roblox_api.py    # async client for Roblox's public API, with caching
graph.py         # friend/follow graphs and community detection
visualize.py     # self-contained HTML mind-map for --open
requirements.txt # httpx, networkx, python-louvain
```
