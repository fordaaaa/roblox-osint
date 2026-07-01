import asyncio
import os
import time
import httpx
from typing import Optional

# Optional auth. Roblox now gates the followers/following list endpoints behind
# a logged-in session (they return 401 otherwise). Set ROBLOX_COOKIE to your
# .ROBLOSECURITY value to unlock them; it also raises rate limits across the
# board. Friends/inner-circle/compare work without it.
_COOKIE = os.environ.get("ROBLOX_COOKIE", "").strip()
_COOKIES = {".ROBLOSECURITY": _COOKIE} if _COOKIE else None

def has_auth() -> bool:
    """True if a Roblox session cookie is configured (unlocks followers/following)."""
    return bool(_COOKIE)


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

async def _get_req(url: str, **kwargs) -> Optional[httpx.Response]:
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=12, cookies=_COOKIES) as c:
                r = await c.get(url, **kwargs)
            if r.status_code == 429:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            return r if r.status_code == 200 else None
        except Exception:
            if attempt == 2:
                return None
            await asyncio.sleep(0.5)
    return None

async def _post_req(url: str, **kwargs) -> Optional[httpx.Response]:
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=12, cookies=_COOKIES) as c:
                r = await c.post(url, **kwargs)
            if r.status_code == 429:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            return r if r.status_code == 200 else None
        except Exception:
            if attempt == 2:
                return None
            await asyncio.sleep(0.5)
    return None


# ── User lookups ──────────────────────────────────────────────────────────────

async def resolve_username(username: str) -> Optional[int]:
    key = f"un:{username.lower()}"
    if (v := _get(key)) is not None:
        return v

    # Try POST username search first
    r = await _post_req(
        f"{USERS_BASE}/usernames/users",
        json={"usernames": [username], "excludeBannedUsers": False},
    )
    if r:
        data = r.json().get("data", [])
        if data:
            return _set(key, data[0]["id"])
        # Roblox returned 200 but empty data = genuinely not found
        return None

    # POST failed (rate-limited / network) — try GET as fallback
    # The GET /v1/users?username= endpoint is different and may have a separate rate limit
    r2 = await _get_req(f"{USERS_BASE}/users/search", params={"keyword": username, "limit": 10})
    if r2:
        for u in r2.json().get("data", []):
            if u.get("name", "").lower() == username.lower():
                return _set(key, u["id"])

    # Both failed — likely rate limited, not a missing account
    return -1  # sentinel: -1 = API failure, None = genuinely not found


async def get_users_batch(user_ids: list, exclude_banned: bool = True) -> dict:
    """
    Resolve many user ids → {id: {id, username, displayName}} in one request.
    Roblox's friends/followers/following lists now return empty name fields,
    so we backfill names here. With exclude_banned=True, terminated/deleted
    accounts are simply absent from the result (handy for filtering).
    Uses POST /v1/users (limit 100 ids per call) instead of N single lookups,
    which avoids the rate-limit storms that made nodes disappear.
    """
    out: dict = {}
    ids = [i for i in user_ids if i is not None]
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        r = await _post_req(
            f"{USERS_BASE}/users",
            json={"userIds": chunk, "excludeBannedUsers": exclude_banned},
        )
        if not r:
            continue
        for d in r.json().get("data", []):
            out[d["id"]] = {
                "id":          d["id"],
                "username":    d.get("name", ""),
                "displayName": d.get("displayName", ""),
            }
    return out


def _parse_user_list(data: list) -> list:
    """Map a friends/followers/following payload to our node dicts.

    Roblox salts these lists with placeholder junk — entries with id -1 and empty
    names (terminated/hidden accounts). Drop them so they don't become blank nodes.
    """
    return [
        {"id": u["id"], "username": u.get("name", ""), "displayName": u.get("displayName", "")}
        for u in data
        if u.get("id", -1) > 0
    ]


def _fill_names(users: list, names: dict) -> list:
    """Backfill empty username/displayName on a list of {id, ...} dicts."""
    for u in users:
        info = names.get(u["id"])
        if info:
            if not u.get("username"):    u["username"]    = info["username"]
            if not u.get("displayName"): u["displayName"] = info["displayName"]
    return users


async def get_user(user_id: int) -> Optional[dict]:
    key = f"user:{user_id}"
    if (v := _get(key)) is not None:
        return v
    # get_user is called a lot — _get_req already retries on 429,
    # but give it one extra attempt with a small gap in case of burst limiting
    r = await _get_req(f"{USERS_BASE}/users/{user_id}")
    if not r:
        await asyncio.sleep(0.8)
        r = await _get_req(f"{USERS_BASE}/users/{user_id}")
    if not r:
        return None
    d = r.json()
    # Roblox returns 200 for banned users but with limited data
    return _set(key, {
        "id":          d["id"],
        "username":    d.get("name", ""),
        "displayName": d.get("displayName", ""),
        "created":     d.get("created", ""),
        "isBanned":    d.get("isBanned", False),
    })


# ── Social lists ──────────────────────────────────────────────────────────────

async def get_friends(user_id: int, enrich: bool = True) -> list:
    key = f"friends:{user_id}"
    if (v := _get(key)) is not None:
        return v
    r = await _get_req(f"{FRIENDS_BASE}/users/{user_id}/friends")
    if not r:
        # Don't cache a failed fetch — a transient 429 would otherwise make this
        # account look empty for the full 5-min TTL even on reload. Let it retry.
        return []
    users = _parse_user_list(r.json().get("data", []))
    # Roblox's friends list returns empty names — backfill from the batch endpoint.
    # enrich=False skips it for bulk friends-of-friends fetches that only need ids.
    if enrich:
        names = await get_users_batch([u["id"] for u in users], exclude_banned=False)
        _fill_names(users, names)
    return _set(key, users)


async def get_followers(user_id: int, limit: int = 100) -> list:
    key = f"followers:{user_id}"
    if (v := _get(key)) is not None:
        return v
    r = await _get_req(
        f"{FRIENDS_BASE}/users/{user_id}/followers",
        params={"limit": min(limit, 100), "sortOrder": "Asc"},
    )
    if not r:
        return []  # don't cache a failed fetch (see get_friends)
    users = _parse_user_list(r.json().get("data", []))
    names = await get_users_batch([u["id"] for u in users], exclude_banned=False)
    _fill_names(users, names)
    return _set(key, users)


async def get_following(user_id: int, limit: int = 100) -> list:
    key = f"following:{user_id}"
    if (v := _get(key)) is not None:
        return v
    r = await _get_req(
        f"{FRIENDS_BASE}/users/{user_id}/followings",
        params={"limit": min(limit, 100), "sortOrder": "Asc"},
    )
    if not r:
        return []  # don't cache a failed fetch (see get_friends)
    users = _parse_user_list(r.json().get("data", []))
    names = await get_users_batch([u["id"] for u in users], exclude_banned=False)
    _fill_names(users, names)
    return _set(key, users)


# ── Profile extras ────────────────────────────────────────────────────────────

async def get_avatar_full(user_id: int) -> str:
    key = f"avfull:{user_id}"
    if (v := _get(key)) is not None:
        return v
    r = await _get_req(
        f"{THUMBS_BASE}/users/avatar",
        params={"userIds": str(user_id), "size": "150x200", "format": "Png"},
    )
    if not r:
        return ""  # don't cache a failed fetch (see get_friends)
    data = r.json().get("data", [])
    return _set(key, data[0].get("imageUrl", "") if data else "")


async def get_groups(user_id: int) -> list:
    key = f"groups:{user_id}"
    if (v := _get(key)) is not None:
        return v
    r = await _get_req(f"{GROUPS_BASE}/users/{user_id}/groups/roles")
    if not r:
        return []  # don't cache a failed fetch (see get_friends)
    groups = [
        {
            "id":          entry["group"]["id"],
            "name":        entry["group"]["name"],
            "memberCount": entry["group"].get("memberCount", 0),
            "rank":        entry["role"]["name"],
            "rankLevel":   entry["role"].get("rank", 0),
        }
        for entry in r.json().get("data", [])
    ]
    return _set(key, groups)


async def get_badges(user_id: int, limit: int = 10, oldest_first: bool = True) -> list:
    key = f"badges:{user_id}:{limit}:{oldest_first}"
    if (v := _get(key)) is not None:
        return v
    r = await _get_req(
        f"{BADGES_BASE}/users/{user_id}/badges",
        params={"limit": limit, "sortOrder": "Asc" if oldest_first else "Desc"},
    )
    if not r:
        return []  # don't cache a failed fetch (see get_friends)
    badges = [
        {"id": b["id"], "name": b["name"], "awardedDate": b.get("awardedDate", "")}
        for b in r.json().get("data", [])
    ]
    return _set(key, badges)


async def get_counts(user_id: int) -> dict:
    key = f"counts:{user_id}"
    if (v := _get(key)) is not None:
        return v
    rf, rfol, rfow = await asyncio.gather(
        _get_req(f"{FRIENDS_BASE}/users/{user_id}/friends/count"),
        _get_req(f"{FRIENDS_BASE}/users/{user_id}/followers/count"),
        _get_req(f"{FRIENDS_BASE}/users/{user_id}/followings/count"),
    )
    counts = {
        "friends":   rf.json().get("count",  0) if rf   else 0,
        "followers": rfol.json().get("count", 0) if rfol else 0,
        "following": rfow.json().get("count", 0) if rfow else 0,
    }
    # Only cache if at least one request succeeded — otherwise a rate-limit blip
    # would pin this profile to all-zeros for the full TTL (see get_friends).
    if rf or rfol or rfow:
        _set(key, counts)
    return counts


async def get_presence(user_id: int) -> dict:
    # Short TTL — presence changes frequently
    key = f"presence:{user_id}"
    entry = _cache.get(key)
    if entry and time.time() - entry[1] < 30:
        return entry[0]
    r = await _post_req(f"{PRESENCE_BASE}/presence/users", json={"userIds": [user_id]})
    if not r:
        return {}  # don't cache a failed fetch (see get_friends)
    presences = r.json().get("userPresences", [])
    if not presences:
        return _set(key, {})
    p = presences[0]
    type_map = {0: "Offline", 1: "Online", 2: "In-Game", 3: "In Studio"}
    return _set(key, {
        "type":      p.get("userPresenceType", 0),
        "label":     type_map.get(p.get("userPresenceType", 0), "Unknown"),
        "lastOnline": p.get("lastOnline", ""),
        "location":  p.get("lastLocation", ""),
    })


async def get_avatars(user_ids: list) -> dict:
    results: dict = {}
    chunks = [user_ids[i:i + 100] for i in range(0, len(user_ids), 100)]
    for chunk in chunks:
        ids_str = ",".join(str(i) for i in chunk)
        key = f"av:{ids_str}"
        if (v := _get(key)) is not None:
            results.update(v)
            continue
        r = await _get_req(
            f"{THUMBS_BASE}/users/avatar-headshot",
            params={"userIds": ids_str, "size": "48x48", "format": "Png"},
        )
        if r:
            batch = {
                item["targetId"]: item.get("imageUrl", "")
                for item in r.json().get("data", [])
                if item.get("state") == "Completed" and item.get("imageUrl")
            }
            _set(key, batch)
            results.update(batch)
    return results
