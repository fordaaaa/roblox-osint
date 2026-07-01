# Roblox OSINT (terminal edition)

A command-line tool for investigating **public** Roblox accounts — profiles,
friend lists, friend-group clusters, followers/following, and two-account
comparisons. No web server and no browser; everything runs from your terminal.

It's pure Python. The only third-party pieces are `httpx` (HTTP), `networkx`
(graphs), and `python-louvain` (cluster detection).

## Setup

```bash
pip install -r requirements.txt
```

That's it — no API keys required for most commands.

## Usage

```bash
python cli.py <command> <username> [options]
```

| Command | What it does |
|---|---|
| `profile <user>`       | Account age, friend/follower/following counts, groups, badges, presence |
| `friends <user>`       | List the user's public friends |
| `circle <user>`        | Friend-group clusters (community detection) |
| `explore <user> [--depth 1-3]` | Crawl the friend network N hops out and report its size |
| `followers <user>`     | List followers *(needs `ROBLOX_COOKIE`, see below)* |
| `following <user>`     | List who the user follows *(needs `ROBLOX_COOKIE`)* |
| `compare <user1> <user2>` | Mutual friends, who-only-knows-who, and degrees of separation |

### Examples

```bash
python cli.py profile Linkmon99
python cli.py friends shedletsky
python cli.py circle Linkmon99
python cli.py explore shedletsky --depth 2
python cli.py compare shedletsky Linkmon99
```

Run `python cli.py --help` for the command list, or
`python cli.py <command> -h` for one command's options.

## Notes & gotchas

- **Private friends lists look empty.** Many accounts hide their friends. When
  Roblox returns nothing, the tool prints a `(!)` note saying the list is
  private or empty — it isn't an error. Try `Linkmon99` or `shedletsky` to see
  a populated result.
- **Followers / Following need a login cookie.** Roblox now gates those list
  endpoints behind a session. Export your `.ROBLOSECURITY` cookie first:

  ```bash
  export ROBLOX_COOKIE="_|WARNING:-DO-NOT-SHARE-THIS...<your cookie>"
  python cli.py followers Linkmon99
  ```

  The cookie also raises rate limits across every command. `profile`,
  `friends`, `circle`, `explore`, and `compare` all work without it.
- **Rate limiting.** Roblox throttles unauthenticated traffic. If a command
  comes back thin or empty right after a big `explore`, wait a few seconds and
  retry — failed fetches are no longer cached, so a retry genuinely re-fetches.

## Project layout

```
cli.py           # command-line entry point (this is what you run)
roblox_api.py    # thin async client for Roblox's public API + caching
graph.py         # builds friend/follow graphs and detects clusters
requirements.txt # httpx, networkx, python-louvain
```
