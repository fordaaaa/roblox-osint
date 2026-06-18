import asyncio
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

import roblox_api as api
import graph as graph_module

app = FastAPI(title="Roblox OSINT Graph")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


# ── User lookup ───────────────────────────────────────────────────────────────

@app.get("/api/user/{username}")
async def get_user(username: str):
    uid = await api.resolve_username(username)
    if uid is None:
        raise HTTPException(404, f"User '{username}' not found")
    user = await api.get_user(uid)
    if user is None:
        raise HTTPException(404, f"User '{username}' not found")
    return user


@app.get("/api/user-by-id/{user_id}")
async def get_user_by_id(user_id: int):
    user = await api.get_user(user_id)
    if user is None:
        raise HTTPException(404, f"User ID {user_id} not found")
    return user


# ── Graph modes ───────────────────────────────────────────────────────────────

@app.get("/api/inner-circle/{username}")
async def inner_circle(username: str):
    """Default mode: seed's friends + edges between mutual friends."""
    uid = await api.resolve_username(username)
    if uid is None:
        raise HTTPException(404, f"User '{username}' not found")
    return await graph_module.build_inner_circle(uid)


@app.get("/api/followers/{username}")
async def followers_graph(username: str):
    uid = await api.resolve_username(username)
    if uid is None:
        raise HTTPException(404, f"User '{username}' not found")
    return await graph_module.build_follow_graph(uid, mode="followers")


@app.get("/api/following/{username}")
async def following_graph(username: str):
    uid = await api.resolve_username(username)
    if uid is None:
        raise HTTPException(404, f"User '{username}' not found")
    return await graph_module.build_follow_graph(uid, mode="following")


@app.get("/api/explore/{username}")
async def explore_graph(
    username: str,
    depth: int = Query(2, ge=1, le=3),
):
    """Full BFS exploration to given depth."""
    uid = await api.resolve_username(username)
    if uid is None:
        raise HTTPException(404, f"User '{username}' not found")
    G = await graph_module.build_graph(uid, depth=depth)
    return graph_module.graph_to_json(G, seed_ids=[uid])


@app.get("/api/compare")
async def compare_users(
    user1: str = Query(...),
    user2: str = Query(...),
):
    uid1, uid2 = await asyncio.gather(
        api.resolve_username(user1),
        api.resolve_username(user2),
    )
    if uid1 is None:
        raise HTTPException(404, f"User '{user1}' not found")
    if uid2 is None:
        raise HTTPException(404, f"User '{user2}' not found")
    return await graph_module.compare_graphs(uid1, uid2)


# ── Profile / Dossier ─────────────────────────────────────────────────────────

@app.get("/api/profile-by-id/{user_id}")
async def get_profile_by_id(user_id: int):
    return await _build_profile(user_id)


@app.get("/api/profile/{username}")
async def get_profile(username: str):
    uid = await api.resolve_username(username)
    if uid is None:
        raise HTTPException(404, f"User '{username}' not found")
    return await _build_profile(uid)


async def _build_profile(uid: int):

    # Fetch everything concurrently; use return_exceptions so one failing
    # sub-call (e.g. badges 401) doesn't kill the whole response.
    results = await asyncio.gather(
        api.get_user(uid),
        api.get_counts(uid),
        api.get_groups(uid),
        api.get_badges(uid, limit=10, oldest_first=True),
        api.get_presence(uid),
        api.get_avatar_full(uid),
        return_exceptions=True,
    )

    user, counts, groups, badges, presence, avatar_full = [
        r if not isinstance(r, Exception) else None
        for r in results
    ]

    if user is None:
        raise HTTPException(404, f"User {uid} not found")

    counts     = counts   or {"friends": 0, "followers": 0, "following": 0}
    groups     = groups   or []
    badges     = badges   or []
    presence   = presence or {}
    avatar_full = avatar_full or ""

    age_days, age_formatted = _account_age(user.get("created", ""))

    return {
        "id":                 uid,
        "username":           user["username"],
        "displayName":        user["displayName"],
        "created":            user.get("created", ""),
        "accountAgeDays":     age_days,
        "accountAgeFormatted": age_formatted,
        "avatarFull":         avatar_full,
        "friendCount":        counts.get("friends",   0),
        "followerCount":      counts.get("followers", 0),
        "followingCount":     counts.get("following", 0),
        "presence":           presence,
        "groups":             groups,
        "firstBadge":         badges[0] if badges else None,
        "badgeCount":         len(badges),
        "badgesHaveMore":     len(badges) == 10,
        "threatLevel":        _threat_score(age_days, counts, groups, badges),
    }


def _account_age(created: str):
    if not created:
        return 0, "Unknown"
    try:
        raw = created.replace("Z", "").split("+")[0].split(".")[0]
        created_dt = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        delta  = datetime.now(timezone.utc) - created_dt
        age_d  = delta.days
        years, rem = divmod(age_d, 365)
        months = rem // 30
        parts  = []
        if years:  parts.append(f"{years} year{'s' if years != 1 else ''}")
        if months: parts.append(f"{months} month{'s' if months != 1 else ''}")
        if not parts: parts.append(f"{age_d} days")
        return age_d, ", ".join(parts)
    except Exception:
        return 0, "Unknown"


def _threat_score(age_days: int, counts: dict, groups: list, badges: list) -> dict:
    score = 0
    if age_days < 7:     score += 4
    elif age_days < 30:  score += 3
    elif age_days < 180: score += 2
    elif age_days < 365: score += 1

    if age_days > 90  and len(badges) == 0: score += 2
    elif age_days > 30 and len(badges) == 0: score += 1

    friends = counts.get("friends", 0) if counts else 0
    if age_days > 60 and friends == 0:    score += 2
    elif age_days > 30 and friends < 3:   score += 1
    if age_days > 180 and len(groups) == 0: score += 1

    score  = min(score, 5)
    labels = ["MINIMAL", "LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"]
    colors = ["#10b981",  "#6ee7b7", "#f59e0b", "#f97316", "#f43f5e", "#dc2626"]
    return {"score": score, "label": labels[score], "color": colors[score]}


# Mount frontend last so API routes take priority
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
