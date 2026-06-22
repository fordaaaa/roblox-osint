import asyncio
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

import roblox_api as api
import graph as graph_module

# hi my name is jeff
app = FastAPI(title="Roblox OSINT Graph")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


def _uid_or_raise(uid, username: str):
    if uid is None:
        raise HTTPException(404, f"'{username}' wasn't found on Roblox — check the spelling")
    if uid == -1:
        raise HTTPException(503, "Roblox's API is busy right now — wait a few seconds and try again")
    return uid


@app.get("/api/user/{username}")
async def get_user(username: str):
    uid = _uid_or_raise(await api.resolve_username(username), username)
    user = await api.get_user(uid)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


@app.get("/api/user-by-id/{user_id}")
async def get_user_by_id(user_id: int):
    user = await api.get_user(user_id)
    if user is None:
        raise HTTPException(404, f"User ID {user_id} not found")
    return user


@app.get("/api/inner-circle/{username}")
async def inner_circle(username: str):
    uid = _uid_or_raise(await api.resolve_username(username), username)
    try:
        return await graph_module.build_inner_circle(uid)
    except Exception as e:
        raise HTTPException(500, f"Graph build failed: {e}")


@app.get("/api/followers/{username}")
async def followers_graph(username: str):
    uid = _uid_or_raise(await api.resolve_username(username), username)
    try:
        return await graph_module.build_follow_graph(uid, mode="followers")
    except Exception as e:
        raise HTTPException(500, f"Failed: {e}")


@app.get("/api/following/{username}")
async def following_graph(username: str):
    uid = _uid_or_raise(await api.resolve_username(username), username)
    try:
        return await graph_module.build_follow_graph(uid, mode="following")
    except Exception as e:
        raise HTTPException(500, f"Failed: {e}")


@app.get("/api/explore/{username}")
async def explore_graph(username: str, depth: int = Query(2, ge=1, le=3)):
    uid = _uid_or_raise(await api.resolve_username(username), username)
    try:
        G = await graph_module.build_graph(uid, depth=depth)
        return graph_module.graph_to_json(G, seed_ids=[uid])
    except Exception as e:
        raise HTTPException(500, f"Failed: {e}")


@app.get("/api/compare")
async def compare_users(user1: str = Query(...), user2: str = Query(...)):
    # Sequential — avoids hitting Roblox rate limits
    uid1 = _uid_or_raise(await api.resolve_username(user1.strip()), user1)
    uid2 = _uid_or_raise(await api.resolve_username(user2.strip()), user2)
    try:
        return await graph_module.compare_graphs(uid1, uid2)
    except Exception as e:
        raise HTTPException(500, f"Compare failed: {e}")


@app.get("/api/profile-by-id/{user_id}")
async def get_profile_by_id(user_id: int):
    return await _build_profile(user_id)


@app.get("/api/profile/{username}")
async def get_profile(username: str):
    uid = _uid_or_raise(await api.resolve_username(username), username)
    return await _build_profile(uid)


async def _build_profile(uid: int):
    # get_user first — retry once if it fails (almost always a transient rate-limit)
    user = await api.get_user(uid)
    if user is None:
        await asyncio.sleep(1.2)
        user = await api.get_user(uid)
    if user is None:
        raise HTTPException(503, "Roblox is rate-limiting us — click the node again in a moment")

    results = await asyncio.gather(
        api.get_counts(uid),
        api.get_groups(uid),
        api.get_badges(uid, limit=10, oldest_first=True),
        api.get_presence(uid),
        api.get_avatar_full(uid),
        return_exceptions=True,
    )
    counts, groups, badges, presence, avatar_full = [
        r if not isinstance(r, Exception) else None for r in results
    ]

    counts      = counts      or {"friends": 0, "followers": 0, "following": 0}
    groups      = groups      or []
    badges      = badges      or []
    presence    = presence    or {}
    avatar_full = avatar_full or ""
    age_days, age_fmt = _account_age(user.get("created", ""))

    return {
        "id":                  uid,
        "username":            user["username"],
        "displayName":         user["displayName"],
        "created":             user.get("created", ""),
        "accountAgeDays":      age_days,
        "accountAgeFormatted": age_fmt,
        "avatarFull":          avatar_full,
        "friendCount":         counts.get("friends",   0),
        "followerCount":       counts.get("followers", 0),
        "followingCount":      counts.get("following", 0),
        "presence":            presence,
        "groups":              groups,
        "firstBadge":          badges[0] if badges else None,
        "badgeCount":          len(badges),
        "badgesHaveMore":      len(badges) == 10,
        "threatLevel":         _threat_score(age_days, counts, groups, badges),
    }


def _account_age(created: str):
    if not created:
        return 0, "Unknown"
    try:
        raw = created.replace("Z", "").split("+")[0].split(".")[0]
        dt  = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        d   = (datetime.now(timezone.utc) - dt).days
        y, rem = divmod(d, 365)
        m = rem // 30
        parts = []
        if y: parts.append(f"{y} year{'s' if y != 1 else ''}")
        if m: parts.append(f"{m} month{'s' if m != 1 else ''}")
        return d, (", ".join(parts) if parts else f"{d} days")
    except Exception:
        return 0, "Unknown"


def _threat_score(age_days, counts, groups, badges):
    score = 0
    if   age_days < 7:   score += 4
    elif age_days < 30:  score += 3
    elif age_days < 180: score += 2
    elif age_days < 365: score += 1
    friends = (counts or {}).get("friends", 0)
    if age_days > 90  and len(badges) == 0: score += 2
    elif age_days > 30 and len(badges) == 0: score += 1
    if age_days > 60  and friends == 0: score += 2
    elif age_days > 30 and friends < 3: score += 1
    if age_days > 180 and len(groups) == 0: score += 1
    score  = min(score, 5)
    labels = ["MINIMAL","LOW","MODERATE","ELEVATED","HIGH","CRITICAL"]
    colors = ["#10b981","#6ee7b7","#f59e0b","#f97316","#f43f5e","#dc2626"]
    return {"score": score, "label": labels[score], "color": colors[score]}


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
