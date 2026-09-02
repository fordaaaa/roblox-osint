#!/usr/bin/env python3
"""
Roblox OSINT — terminal edition.

A command-line tool for mapping and investigating public Roblox accounts:
profiles, friend lists, friend-group clusters, follower/following lists, and
two-account comparisons. No web server, no browser — just commands.

Run `python cli.py --help` for the full list, or `python cli.py <command> -h`
for a single command.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

import roblox_api as api
import graph as graph_module
import visualize


# ── Output helpers ─────────────────────────────────────────────────────────────

def _err(msg: str):
    print(f"error: {msg}", file=sys.stderr)
    return 1


def _rule(title: str = ""):
    line = "─" * 60
    print(f"\n{title}\n{line}" if title else line)


async def _resolve(username: str) -> int:
    """Turn a username into a user id, or exit with a helpful message."""
    uid = await api.resolve_username(username)
    if uid is None:
        raise SystemExit(_err(f"'{username}' wasn't found on Roblox — check the spelling"))
    if uid == -1:
        raise SystemExit(_err("Roblox's API is busy (rate-limited) — wait a few seconds and retry"))
    return uid


def _pct_note_if_empty(node_count: int, username: str, what: str = "friends"):
    """A one-node graph means Roblox returned nothing — almost always privacy."""
    if node_count <= 1:
        print(f"\n(!) {username} has no public {what} — their list is private or empty.")


# ── Commands ───────────────────────────────────────────────────────────────────

async def cmd_profile(args):
    uid = await _resolve(args.username)
    user = await api.get_user(uid)
    if not user:
        return _err("Roblox is rate-limiting us — try again in a moment")

    counts, groups, badges, presence = await asyncio.gather(
        api.get_counts(uid), api.get_groups(uid),
        api.get_badges(uid, limit=10, oldest_first=True), api.get_presence(uid),
        return_exceptions=True,
    )
    counts   = counts   if isinstance(counts, dict)  else {}
    groups   = groups   if isinstance(groups, list)  else []
    badges   = badges   if isinstance(badges, list)  else []
    presence = presence if isinstance(presence, dict) else {}

    if args.json:
        print(json.dumps({
            "userId": uid,
            "displayName": user.get("displayName"),
            "username": user.get("username"),
            "created": user.get("created"),
            "counts": {
                "friends": counts.get("friends", 0),
                "followers": counts.get("followers", 0),
                "following": counts.get("following", 0),
            },
            "presence": presence,
            "groups": groups,
            "firstBadge": badges[0] if badges else None,
        }))
        return 0

    _rule(f"{user['displayName']}  (@{user['username']})")
    print(f"  User ID     : {uid}")
    print(f"  Created     : {user.get('created', '?')}")
    print(f"  Friends     : {counts.get('friends', 0)}")
    print(f"  Followers   : {counts.get('followers', 0)}")
    print(f"  Following   : {counts.get('following', 0)}")
    if presence.get("label"):
        loc = f" — {presence['location']}" if presence.get("location") else ""
        print(f"  Presence    : {presence['label']}{loc}")
    print(f"  Groups      : {len(groups)}")
    for g in groups[:8]:
        print(f"                • {g['name']}  [{g['rank']}]")
    if len(groups) > 8:
        print(f"                … and {len(groups) - 8} more")
    if badges:
        print(f"  First badge : {badges[0]['name']}  ({badges[0].get('awardedDate', '')[:10]})")
    return 0


async def cmd_friends(args):
    uid = await _resolve(args.username)
    friends = await api.get_friends(uid)
    _rule(f"{args.username} — {len(friends)} friend(s)")
    for f in sorted(friends, key=lambda x: (x.get("username") or "").lower()):
        print(f"  {f['id']:>12}  {f.get('displayName') or '?':<24} @{f.get('username') or '?'}")
    _pct_note_if_empty(len(friends) + 1, args.username)
    return 0


async def cmd_circle(args):
    uid = await _resolve(args.username)
    data = await graph_module.build_inner_circle(uid)
    stats = data["stats"]
    _rule(f"{args.username} — friend-group map")
    print(f"  {stats['nodeCount']} people · {stats['edgeCount']} connections · "
          f"{stats['clusterCount']} cluster(s)")
    # Clusters, largest first
    for cid, members in sorted(data["communities"].items(),
                               key=lambda kv: len(kv[1]), reverse=True):
        if len(members) < 2:
            continue
        preview = ", ".join(members[:6]) + ("…" if len(members) > 6 else "")
        print(f"    Cluster {int(cid) + 1:<2} ({len(members):>2}): {preview}")
    _pct_note_if_empty(stats["nodeCount"], args.username)
    if args.open:
        visualize.open_graph(data, title=f"{args.username} — friend circles")
    return 0


async def cmd_follow(args, mode: str):
    if not api.has_auth():
        return _err("Roblox requires login to list followers/following.\n"
                    "  Set ROBLOX_COOKIE to your .ROBLOSECURITY value and retry.")
    uid = await _resolve(args.username)
    data = await graph_module.build_follow_graph(uid, mode=mode)
    people = [n for n in data["nodes"] if not n["isSeed"]]
    _rule(f"{args.username} — {len(people)} {mode}")
    for p in people:
        print(f"  {p['id']:>12}  {p.get('displayName') or '?':<24} @{p.get('username') or '?'}")
    if args.open:
        visualize.open_graph(data, title=f"{args.username} — {mode}")
    return 0


async def cmd_compare(args):
    uid1 = await _resolve(args.user1)
    uid2 = await _resolve(args.user2)
    data = await graph_module.compare_graphs(uid1, uid2)
    cs = data["compareStats"]
    _rule(f"{cs['user1Name']}  vs  {cs['user2Name']}")
    print(f"  {cs['user1Name']:<20} {cs['user1Friends']} friends")
    print(f"  {cs['user2Name']:<20} {cs['user2Friends']} friends")
    print(f"  Mutual friends       {cs['mutualCount']}")
    print(f"  Only {cs['user1Name']:<15} {cs['user1Only']}")
    print(f"  Only {cs['user2Name']:<15} {cs['user2Only']}")
    if cs.get("degreesOfSeparation") is not None:
        chain = " → ".join(n["displayName"] or n["username"] for n in cs["connectionPath"])
        print(f"  Separation           {cs['degreesOfSeparation']} degree(s): {chain}")
    if args.open:
        visualize.open_graph(data, title=f"{cs['user1Name']} vs {cs['user2Name']}")
    return 0


async def cmd_explore(args):
    uid = await _resolve(args.username)
    G = await graph_module.build_graph(uid, depth=args.depth)
    data = graph_module.graph_to_json(G, seed_ids=[uid])
    stats = data["stats"]
    _rule(f"{args.username} — network (depth {args.depth})")
    print(f"  {stats['nodeCount']} people · {stats['edgeCount']} connections · "
          f"{stats['clusterCount']} cluster(s)")
    _pct_note_if_empty(stats["nodeCount"], args.username, what="connections")
    if args.open:
        visualize.open_graph(data, title=f"{args.username} — network depth {args.depth}")
    return 0


async def cmd_alts(args):
    """Detect friend accounts created within suspicious time windows."""
    uid = await _resolve(args.username)
    friends = await api.get_friends(uid)
    if not friends:
        return _err(f"{args.username} has no public friends (private list or empty)")

    # Fetch creation dates concurrently
    sem = asyncio.Semaphore(5)
    async def fetch(f):
        async with sem:
            return f, await api.get_user(f["id"])

    results = await asyncio.gather(*[fetch(f) for f in friends])

    dated = []
    for f, user in results:
        if user and user.get("created"):
            try:
                dt = datetime.fromisoformat(user["created"].replace("Z", "+00:00"))
                dated.append({**f, "created_dt": dt, "created": user["created"]})
            except ValueError:
                pass

    if not dated:
        return _err("Couldn't retrieve creation dates for any friends")

    dated.sort(key=lambda x: x["created_dt"])
    window  = timedelta(days=args.window)
    min_sz  = args.min_size

    # Sliding-window grouping — walk forward from each un-used anchor
    groups, used = [], set()
    for i, anchor in enumerate(dated):
        if anchor["id"] in used:
            continue
        group = [anchor]
        for item in dated[i + 1:]:
            if item["created_dt"] - anchor["created_dt"] <= window:
                group.append(item)
            else:
                break
        if len(group) >= min_sz:
            for m in group:
                used.add(m["id"])
            groups.append(group)

    _rule(f"{args.username} — alt/bot detection  (window={args.window}d, min={min_sz})")
    print(f"  Checked {len(dated)} friends with known join dates")

    if not groups:
        print("  No suspicious account clusters found.\n")
        return 0

    print(f"  Found {len(groups)} suspicious cluster(s):\n")
    for i, group in enumerate(groups, 1):
        d0 = group[0]["created_dt"].strftime("%Y-%m-%d")
        d1 = group[-1]["created_dt"].strftime("%Y-%m-%d")
        span = (group[-1]["created_dt"] - group[0]["created_dt"]).days
        print(f"  Cluster {i}  ({len(group)} accounts · {d0} → {d1} · {span}d span)")
        for m in group:
            print(f"    {m['id']:>12}  {m.get('displayName','?'):<24}"
                  f"  @{m.get('username','?'):<24}  {m['created'][:10]}")
        print()

    return 0


# ── Argument parsing ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cli.py",
        description="Roblox OSINT from the terminal — profiles, friends, clusters, compare.",
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    def add(name, help_, visual=False):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("username")
        if visual:
            sp.add_argument("--open", action="store_true",
                            help="open an interactive mind-map in your browser")
        return sp

    sp_profile = add("profile", "full profile: age, counts, groups, badges, presence")
    sp_profile.add_argument("--json", action="store_true",
                            help="print the profile as a single JSON object")
    add("friends",   "list a user's public friends")
    add("circle",    "friend-group clusters (community detection)", visual=True)
    add("followers", "list followers (needs ROBLOX_COOKIE)", visual=True)
    add("following", "list who a user follows (needs ROBLOX_COOKIE)", visual=True)

    sp_exp = add("explore", "crawl the friend network N hops out", visual=True)
    sp_exp.add_argument("--depth", type=int, default=2, choices=(1, 2, 3),
                        help="how many hops to crawl (default 2)")

    sp_cmp = sub.add_parser("compare", help="compare two users' friend graphs")
    sp_cmp.add_argument("user1")
    sp_cmp.add_argument("user2")
    sp_cmp.add_argument("--open", action="store_true",
                        help="open an interactive mind-map in your browser")

    sp_alt = sub.add_parser("alts",
        help="detect friends created in suspicious time windows (alt/bot farms)")
    sp_alt.add_argument("username")
    sp_alt.add_argument("--window", type=int, default=30, metavar="DAYS",
                        help="creation-date window to group accounts (default 30)")
    sp_alt.add_argument("--min-size", type=int, default=3, metavar="N",
                        help="minimum cluster size to report (default 3)")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    dispatch = {
        "profile":   cmd_profile,
        "friends":   cmd_friends,
        "circle":    cmd_circle,
        "followers": lambda a: cmd_follow(a, "followers"),
        "following": lambda a: cmd_follow(a, "following"),
        "compare":   cmd_compare,
        "explore":   cmd_explore,
        "alts":      cmd_alts,
    }
    try:
        return asyncio.run(dispatch[args.command](args)) or 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
