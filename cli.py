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
import sys

import roblox_api as api
import graph as graph_module


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
    return 0


# ── Argument parsing ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cli.py",
        description="Roblox OSINT from the terminal — profiles, friends, clusters, compare.",
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    def add(name, help_):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("username")
        return sp

    add("profile",   "full profile: age, counts, groups, badges, presence")
    add("friends",   "list a user's public friends")
    add("circle",    "friend-group clusters (community detection)")
    add("followers", "list followers (needs ROBLOX_COOKIE)")
    add("following", "list who a user follows (needs ROBLOX_COOKIE)")

    sp_exp = add("explore", "crawl the friend network N hops out")
    sp_exp.add_argument("--depth", type=int, default=2, choices=(1, 2, 3),
                        help="how many hops to crawl (default 2)")

    sp_cmp = sub.add_parser("compare", help="compare two users' friend graphs")
    sp_cmp.add_argument("user1")
    sp_cmp.add_argument("user2")

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
    }
    try:
        return asyncio.run(dispatch[args.command](args)) or 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
