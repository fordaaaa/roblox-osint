import asyncio
from collections import deque

import networkx as nx
import roblox_api as api

MAX_NODES    = 300
_CONCURRENCY = 5


# ── Community detection (shared) ──────────────────────────────────────────────

def detect_communities(G) -> dict:
    """Louvain on the undirected friend subgraph; falls back to greedy modularity."""
    if len(G.nodes()) == 0:
        return {}

    friend_edges = [
        (u, v) for u, v, d in G.edges(data=True) if d.get("type") == "friend"
    ]
    UG = nx.Graph()
    UG.add_nodes_from(G.nodes())
    UG.add_edges_from(friend_edges)

    try:
        import community as community_louvain
        return community_louvain.best_partition(UG)
    except Exception:
        pass

    try:
        from networkx.algorithms.community import greedy_modularity_communities
        partition: dict = {}
        for cid, comm in enumerate(greedy_modularity_communities(UG)):
            for node in comm:
                partition[node] = cid
        return partition
    except Exception:
        # Last resort: every node is its own community
        return {uid: i for i, uid in enumerate(G.nodes())}


def _find_cliques(G, seed_ids: list) -> dict:
    """
    Return dict: node_id → clique_id for nodes that belong to a clique of 3+.
    Only looks at the friend subgraph, excluding seed nodes.
    """
    non_seeds = [n for n in G.nodes() if n not in seed_ids]
    friend_edges = [
        (u, v) for u, v, d in G.edges(data=True)
        if d.get("type") == "friend" and u in non_seeds and v in non_seeds
    ]
    sub = nx.Graph()
    sub.add_nodes_from(non_seeds)
    sub.add_edges_from(friend_edges)

    cliques = [c for c in nx.find_cliques(sub) if len(c) >= 3]
    # Sort by size desc so larger cliques win for each node
    cliques.sort(key=len, reverse=True)
    node_clique: dict = {}
    for cid, clique in enumerate(cliques):
        for node in clique:
            if node not in node_clique:
                node_clique[node] = cid
    return node_clique


def graph_to_json(G, seed_ids: list = None, compare_groups: dict = None,
                  mutual_counts: dict = None) -> dict:
    seed_ids = seed_ids or []
    partition  = detect_communities(G)
    clique_map = _find_cliques(G, seed_ids)

    nodes = []
    valid_ids: set = set()
    for uid, data in G.nodes(data=True):
        is_seed = uid in seed_ids
        # Drop non-seed nodes that are banned — these are terminated accounts.
        # Do NOT drop nodes that merely lack an avatar: the thumbnails endpoint
        # is rate-limited separately and frequently returns empty/Blocked/Pending,
        # so a single 429 there would otherwise wipe every friend from the graph.
        # Avatar-less nodes render fine as a coloured circle on the frontend.
        if not is_seed and data.get("isBanned"):
            continue
        node = {
            "id":          uid,
            "username":    data.get("username",    str(uid)),
            "displayName": data.get("displayName", str(uid)),
            "avatarUrl":   data.get("avatarUrl",   ""),
            "created":     data.get("created",     ""),
            "isSeed":      is_seed,
            "community":   partition.get(uid, 0),
            "degree":      G.degree(uid),
            "mutualCount": mutual_counts.get(uid, 0) if mutual_counts else None,
            "cliqueId":    clique_map.get(uid),
        }
        if compare_groups:
            node["group"] = compare_groups.get(uid, "common")
        nodes.append(node)
        valid_ids.add(uid)

    # Deduplicate bidirectional friend edges; skip edges referencing filtered-out nodes
    seen_pairs: set = set()
    edges = []
    for u, v, data in G.edges(data=True):
        if u not in valid_ids or v not in valid_ids:
            continue
        etype = data.get("type", "friend")
        if etype == "friend":
            pair = (min(u, v), max(u, v))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
        edges.append({"source": u, "target": v, "type": etype})

    communities: dict = {}
    for uid, cid in partition.items():
        if uid not in G.nodes:
            continue
        key = str(cid)
        communities.setdefault(key, [])
        communities[key].append(G.nodes[uid].get("displayName", str(uid)))

    return {
        "nodes":       nodes,
        "edges":       edges,
        "communities": communities,
        "stats": {
            "nodeCount":    len(nodes),
            "edgeCount":    len(edges),
            "clusterCount": len(communities),
        },
    }


# ── Mode: Inner Circle ────────────────────────────────────────────────────────

async def build_inner_circle(seed_id: int) -> dict:
    """
    The most useful view: seed's direct friends as nodes, with edges drawn
    between friends who are ALSO friends with each other.
    """
    # Fetch seed first so it's cached before bulk operations hit rate limits
    seed_user_pre = await api.get_user(seed_id)
    friends = await api.get_friends(seed_id)
    if not friends:
        # Return just the seed
        seed_user = await api.get_user(seed_id)
        G = nx.Graph()
        if seed_user:
            G.add_node(seed_id, **seed_user, isSeed=True)
        return graph_to_json(G, seed_ids=[seed_id])

    # Validate each friend via get_user — this filters banned/deleted accounts
    # and warms the cache so profile clicks are instant.
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def validate(f):
        async with sem:
            user = await api.get_user(f["id"])
        return f, user

    validations = await asyncio.gather(*[validate(f) for f in friends], return_exceptions=True)
    # Only keep real, non-banned accounts; skip anything that errored
    valid_friends = [
        (f, user) for f, user in validations
        if not isinstance(user, Exception)
        and user is not None
        and not user.get("isBanned", False)
    ]

    if not valid_friends:
        seed_user = await api.get_user(seed_id)
        G = nx.Graph()
        if seed_user:
            G.add_node(seed_id, **seed_user, isSeed=True)
        return graph_to_json(G, seed_ids=[seed_id])

    friend_ids = {f["id"] for f, _ in valid_friends}

    # Build graph with seed + validated friends (seed already cached above)
    G = nx.Graph()
    seed_user = seed_user_pre or await api.get_user(seed_id)
    if seed_user:
        G.add_node(seed_id, **seed_user, isSeed=True, depth=0)

    for f, user_data in valid_friends:
        # Use full user_data (includes created, isBanned) not just the friends-list stub
        G.add_node(f["id"], **user_data, depth=1, isSeed=False)
        G.add_edge(seed_id, f["id"], type="friend")

    # Fetch each friend's friend list to find mutual connections
    async def get_their_friends(fid):
        async with sem:
            return fid, await api.get_friends(fid)

    results = await asyncio.gather(*[get_their_friends(fid) for fid in friend_ids], return_exceptions=True)

    # mutual_counts[fid] = how many of seed's friends fid is also friends with
    mutual_counts: dict = {}
    for entry in results:
        if isinstance(entry, Exception):
            continue
        fid, their_friends = entry
        their_ids = {f["id"] for f in their_friends}
        mutual = their_ids & friend_ids - {seed_id}
        mutual_counts[fid] = len(mutual)
        for mid in mutual:
            if not G.has_edge(fid, mid):
                G.add_edge(fid, mid, type="friend")

    # Avatars
    avatars = await api.get_avatars(list(G.nodes()))
    for uid, url in avatars.items():
        if uid in G.nodes and url:
            G.nodes[uid]["avatarUrl"] = url

    return graph_to_json(G, seed_ids=[seed_id], mutual_counts=mutual_counts)


# ── Mode: Followers / Following ───────────────────────────────────────────────

async def build_follow_graph(seed_id: int, mode: str = "followers") -> dict:
    """
    mode = 'followers' or 'following'
    Shows the seed + the people following/followed, as a simple star.
    """
    G = nx.DiGraph()

    seed_user = await api.get_user(seed_id)
    if seed_user:
        G.add_node(seed_id, **seed_user, isSeed=True, depth=0)

    if mode == "followers":
        people = await api.get_followers(seed_id, limit=100)
    else:
        people = await api.get_following(seed_id, limit=100)

    for p in people:
        G.add_node(p["id"], **p, isSeed=False, depth=1)
        if mode == "followers":
            G.add_edge(p["id"], seed_id, type="follows")
        else:
            G.add_edge(seed_id, p["id"], type="follows")

    avatars = await api.get_avatars(list(G.nodes()))
    for uid, url in avatars.items():
        if uid in G.nodes and url:
            G.nodes[uid]["avatarUrl"] = url

    return graph_to_json(G, seed_ids=[seed_id])


# ── Mode: Full BFS (explore) ──────────────────────────────────────────────────

async def build_graph(seed_id: int, depth: int = 2,
                      include_followers: bool = False,
                      include_following: bool = False) -> nx.DiGraph:
    G       = nx.DiGraph()
    visited: set = set()
    sem     = asyncio.Semaphore(_CONCURRENCY)

    async def fetch_connections(uid):
        async with sem:
            tasks = [api.get_friends(uid)]
            if include_followers:
                tasks.append(api.get_followers(uid))
            if include_following:
                tasks.append(api.get_following(uid))
            results = await asyncio.gather(*tasks)
        friends   = results[0]
        idx       = 1
        followers = results[idx] if include_followers else []; idx += include_followers
        following = results[idx] if include_following else []
        return friends, followers, following

    frontier = [seed_id]
    for level in range(depth):
        if not frontier or len(G.nodes) >= MAX_NODES:
            break

        profiles = await asyncio.gather(*[api.get_user(uid) for uid in frontier if uid not in visited])
        profile_map = {uid: p for uid, p in zip([u for u in frontier if u not in visited], profiles)}

        conns    = await asyncio.gather(*[fetch_connections(uid) for uid in frontier if uid not in visited])
        conn_map = {uid: c for uid, c in zip([u for u in frontier if u not in visited], conns)}

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
        frontier = list(dict.fromkeys(next_frontier))

    avatars = await api.get_avatars(list(G.nodes()))
    for uid, url in avatars.items():
        if uid in G.nodes and url:
            G.nodes[uid]["avatarUrl"] = url

    return G


# ── Mode: Compare ─────────────────────────────────────────────────────────────

async def compare_graphs(user1_id: int, user2_id: int) -> dict:
    """
    Builds inner-circle graphs for both users, merges them,
    and marks nodes as user1/user2/common.
    Only friend edges — the question is purely "who do they both know".
    """
    friends1, friends2 = await asyncio.gather(
        api.get_friends(user1_id),
        api.get_friends(user2_id),
    )
    ids1 = {f["id"] for f in friends1} | {user1_id}
    ids2 = {f["id"] for f in friends2} | {user2_id}
    common_ids = ids1 & ids2

    # Build one merged graph from both friend lists
    all_friend_ids = ids1 | ids2
    G = nx.Graph()

    # Seed nodes
    u1, u2 = await asyncio.gather(api.get_user(user1_id), api.get_user(user2_id))
    if u1: G.add_node(user1_id, **u1, isSeed=True)
    if u2: G.add_node(user2_id, **u2, isSeed=True)

    # All friend nodes
    all_friends = {f["id"]: f for f in friends1 + friends2}
    for fid, fdata in all_friends.items():
        G.add_node(fid, **fdata, isSeed=False)

    # Edges from seed → friends
    for f in friends1:
        G.add_edge(user1_id, f["id"], type="friend")
    for f in friends2:
        G.add_edge(user2_id, f["id"], type="friend")

    # Also add mutual edges between common friends (who know each other)
    sem = asyncio.Semaphore(_CONCURRENCY)
    common_friends = [f for f in friends1 + friends2 if f["id"] in common_ids - {user1_id, user2_id}]
    seen = set()
    unique_common = [f for f in common_friends if f["id"] not in seen and not seen.add(f["id"])]

    async def get_their_friends(fid):
        async with sem:
            return fid, await api.get_friends(fid)

    results = await asyncio.gather(*[get_their_friends(f["id"]) for f in unique_common])
    for fid, their_friends in results:
        for tf in their_friends:
            if tf["id"] in all_friend_ids and tf["id"] != fid:
                if not G.has_edge(fid, tf["id"]):
                    G.add_edge(fid, tf["id"], type="friend")

    avatars = await api.get_avatars(list(G.nodes()))
    for uid, url in avatars.items():
        if uid in G.nodes and url:
            G.nodes[uid]["avatarUrl"] = url

    compare_groups = {
        uid: ("common" if uid in common_ids else "user1" if uid in ids1 else "user2")
        for uid in G.nodes()
    }

    result = graph_to_json(G, seed_ids=[user1_id, user2_id], compare_groups=compare_groups)

    # ── Compare stats ──
    mutual_nodes = [uid for uid in common_ids if uid not in {user1_id, user2_id}]
    u1_only      = [uid for uid in ids1 if uid not in common_ids and uid != user1_id]
    u2_only      = [uid for uid in ids2 if uid not in common_ids and uid != user2_id]

    # Shortest path between the two users through the shared friend graph
    connection_path = []
    degrees = None
    try:
        if user1_id in G.nodes and user2_id in G.nodes:
            path_ids = nx.shortest_path(G, source=user1_id, target=user2_id)
            degrees  = len(path_ids) - 1
            connection_path = [
                {
                    "id":          uid,
                    "username":    G.nodes[uid].get("username", str(uid)),
                    "displayName": G.nodes[uid].get("displayName", str(uid)),
                    "avatarUrl":   G.nodes[uid].get("avatarUrl", ""),
                }
                for uid in path_ids
                if uid in G.nodes
            ]
    except Exception:
        pass

    result["compareStats"] = {
        "user1Id":       user1_id,
        "user2Id":       user2_id,
        "user1Name":     G.nodes[user1_id].get("displayName", "User 1") if user1_id in G else "User 1",
        "user2Name":     G.nodes[user2_id].get("displayName", "User 2") if user2_id in G else "User 2",
        "user1Friends":  len(friends1),
        "user2Friends":  len(friends2),
        "mutualCount":   len(mutual_nodes),
        "user1Only":     len(u1_only),
        "user2Only":     len(u2_only),
        "friendDiff":    abs(len(friends1) - len(friends2)),
        "connectionPath": connection_path,
        "degreesOfSeparation": degrees,
    }

    return result
