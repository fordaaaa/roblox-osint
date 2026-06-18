import asyncio
import time
import httpx
from typing import Optional

_cache: dict = {}
_CACHE_TTL = 300  # 5 minutes

def _get(key: str):
    entry = _cache.get(key)
    if entry and time.time() - entry[1] < _CACHE_TTL:
        return entry[0]
    return None

def _set(key: str, val):
    _cache[key] = (val, time.time())
    return val

USERS_BASE    = "https://users.roblox.com/v1"
FRIENDS_BASE  = "https://friends.roblox.com/v1"
THUMBS_BASE   = "https://thumbnails.roblox.com/v1"
GROUPS_BASE   = "https://groups.roblox.com/v1"
BADGES_BASE   = "https://badges.roblox.com/v1"
PRESENCE_BASE = "https://presence.roblox.com/v1"


async def resolve_username(username: str) -> Optional[int]:
    key = f"un:{username.lower()}"
    if (v := _get(key)) is not None:
        return v
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(
            f"{USERS_BASE}/usernames/users",
            json={"usernames": [username], "excludeBannedUsers": False},
        )
    data = r.json().get("data", [])
    return _set(key, data[0]["id"]) if data else None


async def get_user(user_id: int) -> Optional[dict]:
    key = f"user:{user_id}"
    if (v := _get(key)) is not None:
        return v
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{USERS_BASE}/users/{user_id}")
    if r.status_code != 200:
        return None
    d = r.json()
    return _set(key, {
        "id": d["id"],
        "username": d["name"],
        "displayName": d["displayName"],
        "created": d.get("created", ""),
    })


async def get_friends(user_id: int) -> list:
    key = f"friends:{user_id}"
    if (v := _get(key)) is not None:
        return v
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{FRIENDS_BASE}/users/{user_id}/friends")
    if r.status_code != 200:
        return _set(key, [])
    users = [
        {"id": u["id"], "username": u["name"], "displayName": u["displayName"]}
        for u in r.json().get("data", [])
    ]
    return _set(key, users)


async def get_followers(user_id: int, limit: int = 100) -> list:
    key = f"followers:{user_id}"
    if (v := _get(key)) is not None:
        return v
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{FRIENDS_BASE}/users/{user_id}/followers",
            params={"limit": min(limit, 100), "sortOrder": "Asc"},
        )
    if r.status_code != 200:
        return _set(key, [])
    users = [
        {"id": u["id"], "username": u["name"], "displayName": u["displayName"]}
        for u in r.json().get("data", [])
    ]
    return _set(key, users)


async def get_following(user_id: int, limit: int = 100) -> list:
    key = f"following:{user_id}"
    if (v := _get(key)) is not None:
        return v
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{FRIENDS_BASE}/users/{user_id}/followings",
            params={"limit": min(limit, 100), "sortOrder": "Asc"},
        )
    if r.status_code != 200:
        return _set(key, [])
    users = [
        {"id": u["id"], "username": u["name"], "displayName": u["displayName"]}
        for u in r.json().get("data", [])
    ]
    return _set(key, users)


async def get_avatar_full(user_id: int) -> str:
    key = f"avfull:{user_id}"
    if (v := _get(key)) is not None:
        return v
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{THUMBS_BASE}/users/avatar",
            params={"userIds": str(user_id), "size": "150x200", "format": "Png"},
        )
    if r.status_code != 200:
        return _set(key, "")
    data = r.json().get("data", [])
    return _set(key, data[0].get("imageUrl", "") if data else "")


async def get_groups(user_id: int) -> list:
    key = f"groups:{user_id}"
    if (v := _get(key)) is not None:
        return v
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{GROUPS_BASE}/users/{user_id}/groups/roles")
    if r.status_code != 200:
        return _set(key, [])
    groups = [
        {
            "id": entry["group"]["id"],
            "name": entry["group"]["name"],
            "memberCount": entry["group"].get("memberCount", 0),
            "rank": entry["role"]["name"],
            "rankLevel": entry["role"].get("rank", 0),
        }
        for entry in r.json().get("data", [])
    ]
    return _set(key, groups)


async def get_badges(user_id: int, limit: int = 10, oldest_first: bool = True) -> list:
    key = f"badges:{user_id}:{limit}:{oldest_first}"
    if (v := _get(key)) is not None:
        return v
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(
            f"{BADGES_BASE}/users/{user_id}/badges",
            params={"limit": limit, "sortOrder": "Asc" if oldest_first else "Desc"},
        )
    if r.status_code != 200:
        return _set(key, [])
    badges = [
        {"id": b["id"], "name": b["name"], "awardedDate": b.get("awardedDate", "")}
        for b in r.json().get("data", [])
    ]
    return _set(key, badges)


async def get_counts(user_id: int) -> dict:
    key = f"counts:{user_id}"
    if (v := _get(key)) is not None:
        return v
    async with httpx.AsyncClient(timeout=15) as c:
        rf, rfol, rfow = await asyncio.gather(
            c.get(f"{FRIENDS_BASE}/users/{user_id}/friends/count"),
            c.get(f"{FRIENDS_BASE}/users/{user_id}/followers/count"),
            c.get(f"{FRIENDS_BASE}/users/{user_id}/followings/count"),
        )
    return _set(key, {
        "friends":   rf.json().get("count", 0)   if rf.status_code   == 200 else 0,
        "followers": rfol.json().get("count", 0) if rfol.status_code == 200 else 0,
        "following": rfow.json().get("count", 0) if rfow.status_code == 200 else 0,
    })


async def get_presence(user_id: int) -> dict:
    key = f"presence:{user_id}"
    # presence is short-lived — 30s TTL
    entry = _cache.get(key)
    if entry and time.time() - entry[1] < 30:
        return entry[0]
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(f"{PRESENCE_BASE}/presence/users", json={"userIds": [user_id]})
    if r.status_code != 200:
        return _set(key, {})
    presences = r.json().get("userPresences", [])
    if not presences:
        return _set(key, {})
    p = presences[0]
    type_map = {0: "Offline", 1: "Online", 2: "In-Game", 3: "In Studio"}
    result = {
        "type": p.get("userPresenceType", 0),
        "label": type_map.get(p.get("userPresenceType", 0), "Unknown"),
        "lastOnline": p.get("lastOnline", ""),
        "location": p.get("lastLocation", ""),
    }
    return _set(key, result)


async def get_avatars(user_ids: list) -> dict:
    results: dict = {}
    chunks = [user_ids[i:i + 100] for i in range(0, len(user_ids), 100)]
    async with httpx.AsyncClient(timeout=15) as c:
        for chunk in chunks:
            ids_str = ",".join(str(i) for i in chunk)
            key = f"av:{ids_str}"
            if (v := _get(key)) is not None:
                results.update(v)
                continue
            r = await c.get(
                f"{THUMBS_BASE}/users/avatar-headshot",
                params={"userIds": ids_str, "size": "48x48", "format": "Png"},
            )
            if r.status_code == 200:
                batch = {
                    item["targetId"]: item.get("imageUrl", "")
                    for item in r.json().get("data", [])
                }
                _set(key, batch)
                results.update(batch)
    return results
