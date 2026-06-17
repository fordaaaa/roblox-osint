import asyncio
from collections import deque

import networkx as nx
import roblox_api as api

MAX_NODES = 300
_CONCURRENCY = 8


def _make_semaphore():
    return asyncio.Semaphore(_CONCURRENCY)


async def _fetch_connections(uid: int, sem, include_followers: bool, include_following: bool):
    async with sem:
        tasks = [api.get_friends(uid)]
        if include_followers:
            tasks.append(api.get_followers(uid))
        if include_following:
            tasks.append(api.get_following(uid))
        results = await asyncio.gather(*tasks)

    friends = results[0]
    idx = 1
    followers = results[idx] if include_followers else []
    if include_followers:
        idx += 1
    following = results[idx] if include_following else []
    return friends, followers, following


async def build_graph(
    seed_id: int,
    depth: int = 2,
    include_followers: bool = True,
    include_following: bool = True,
) -> nx.DiGraph:
    G = nx.DiGraph()
    visited: set = set()
    sem = _make_semaphore()

    # Level-by-level BFS
    frontier = [seed_id]
    for level in range(depth):
        if not frontier or len(G.nodes) >= MAX_NODES:
            break

        # Fetch all node profiles for this level
        profile_tasks = {uid: api.get_user(uid) for uid in frontier if uid not in visited}
        profiles = await asyncio.gather(*profile_tasks.values())
        profile_map = dict(zip(profile_tasks.keys(), profiles))

        # Fetch connections for all frontier nodes concurrently
        conn_tasks = {
            uid: _fetch_connections(uid, sem, include_followers, include_following)
            for uid in frontier if uid not in visited
        }
        connections = await asyncio.gather(*conn_tasks.values())
        conn_map = dict(zip(conn_tasks.keys(), connections))

        next_frontier = []
        for uid in frontier:
            if uid in visited:
                continue
            visited.add(uid)

            user = profile_map.get(uid)
            if not user:
                continue

            G.add_node(uid, **user, isSeed=(uid == seed_id), depth=level)

            friends, followers, following = conn_map.get(uid, ([], [], []))

            for f in friends:
                fid = f["id"]
                if fid not in G:
                    G.add_node(fid, **f, isSeed=False, depth=level + 1)
                G.add_edge(uid, fid, type="friend")
                G.add_edge(fid, uid, type="friend")
                if fid not in visited and len(G.nodes) < MAX_NODES:
                    next_frontier.append(fid)

            for f in followers:
                fid = f["id"]
                if fid not in G:
                    G.add_node(fid, **f, isSeed=False, depth=level + 1)
                G.add_edge(fid, uid, type="follows")

            for f in following:
                fid = f["id"]
                if fid not in G:
                    G.add_node(fid, **f, isSeed=False, depth=level + 1)
                G.add_edge(uid, fid, type="follows")

        frontier = list(dict.fromkeys(next_frontier))  # deduplicate preserving order

    # Batch-fetch avatars for all nodes
    all_ids = list(G.nodes())
    avatars = await api.get_avatars(all_ids)
    for uid, url in avatars.items():
        if uid in G.nodes and url:
            G.nodes[uid]["avatarUrl"] = url

    return G


def detect_communities(G: nx.DiGraph) -> dict:
    friend_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("type") == "friend"]
    UG = nx.Graph()
    UG.add_nodes_from(G.nodes())
    UG.add_edges_from(friend_edges)

    try:
        import community as community_louvain
        return community_louvain.best_partition(UG)
    except (ImportError, Exception):
        from networkx.algorithms.community import greedy_modularity_communities
        partition: dict = {}
        for cid, comm in enumerate(greedy_modularity_communities(UG)):
            for node in comm:
                partition[node] = cid
        return partition


def graph_to_json(G: nx.DiGraph, seed_ids: list = None, compare_groups: dict = None) -> dict:
    seed_ids = seed_ids or []
    partition = detect_communities(G)

    nodes = []
    for uid, data in G.nodes(data=True):
        node = {
            "id": uid,
            "username": data.get("username", str(uid)),
            "displayName": data.get("displayName", str(uid)),
            "avatarUrl": data.get("avatarUrl", ""),
            "created": data.get("created", ""),
            "isSeed": uid in seed_ids,
            "community": partition.get(uid, 0),
            "degree": G.degree(uid),
        }
        if compare_groups:
            node["group"] = compare_groups.get(uid, "common")
        nodes.append(node)

    # Deduplicate friend edges (they're bidirectional in DiGraph)
    seen_friend_pairs: set = set()
    edges = []
    for u, v, data in G.edges(data=True):
        etype = data.get("type", "friend")
        if etype == "friend":
            pair = (min(u, v), max(u, v))
            if pair in seen_friend_pairs:
                continue
            seen_friend_pairs.add(pair)
        edges.append({"source": u, "target": v, "type": etype})

    communities: dict = {}
    for uid, cid in partition.items():
        key = str(cid)
        communities.setdefault(key, [])
        node_data = G.nodes.get(uid, {})
        communities[key].append(node_data.get("displayName", str(uid)))

    return {
        "nodes": nodes,
        "edges": edges,
        "communities": communities,
        "stats": {
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "clusterCount": len(communities),
        },
    }


async def compare_graphs(user1_id: int, user2_id: int, depth: int = 2) -> dict:
    G1, G2 = await asyncio.gather(
        build_graph(user1_id, depth),
        build_graph(user2_id, depth),
    )

    merged = nx.compose(G1, G2)
    nodes1 = set(G1.nodes())
    nodes2 = set(G2.nodes())
    common = nodes1 & nodes2

    compare_groups = {
        uid: ("common" if uid in common else "user1" if uid in nodes1 else "user2")
        for uid in merged.nodes()
    }

    return graph_to_json(merged, seed_ids=[user1_id, user2_id], compare_groups=compare_groups)
