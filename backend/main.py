import asyncio
import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

import roblox_api as api
import graph as graph_module

app = FastAPI(title="Roblox OSINT Graph")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


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


@app.get("/api/graph/{username}")
async def get_graph(
    username: str,
    depth: int = Query(2, ge=1, le=3),
    followers: bool = True,
    following: bool = True,
):
    uid = await api.resolve_username(username)
    if uid is None:
        raise HTTPException(404, f"User '{username}' not found")

    G = await graph_module.build_graph(
        uid,
        depth=depth,
        include_followers=followers,
        include_following=following,
    )
    return graph_module.graph_to_json(G, seed_ids=[uid])


@app.get("/api/compare")
async def compare_users(
    user1: str = Query(...),
    user2: str = Query(...),
    depth: int = Query(2, ge=1, le=3),
):
    uid1, uid2 = await asyncio.gather(
        api.resolve_username(user1),
        api.resolve_username(user2),
    )
    if uid1 is None:
        raise HTTPException(404, f"User '{user1}' not found")
    if uid2 is None:
        raise HTTPException(404, f"User '{user2}' not found")

    return await graph_module.compare_graphs(uid1, uid2, depth=depth)


@app.get("/api/profile/{username}")
async def get_profile(username: str):
    uid = await api.resolve_username(username)
    if uid is None:
        raise HTTPException(404, f"User '{username}' not found")

    user, counts, groups, badges, presence, avatar_full = await asyncio.gather(
        api.get_user(uid),
        api.get_counts(uid),
        api.get_groups(uid),
        api.get_badges(uid, limit=10, oldest_first=True),
        api.get_presence(uid),
        api.get_avatar_full(uid),
    )
    if user is None:
        raise HTTPException(404, f"User '{username}' not found")

    # Account age
    age_days = 0
    age_formatted = "Unknown"
    if user.get("created"):
        try:
            # Strip timezone and fractional seconds for Python 3.9 compat
            raw = user["created"].replace("Z", "").split("+")[0].split(".")[0]
            created = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
            delta = datetime.now(timezone.utc) - created
            age_days = delta.days
            years, rem = divmod(age_days, 365)
            months = rem // 30
            parts = []
            if years:
                parts.append(f"{years} year{'s' if years != 1 else ''}")
            if months:
                parts.append(f"{months} month{'s' if months != 1 else ''}")
            if not parts:
                parts.append(f"{age_days} days")
            age_formatted = ", ".join(parts)
        except Exception:
            pass

    # Threat assessment (fun metric — based on suspicious account patterns)
    score = _threat_score(age_days, counts, groups, badges)

    return {
        "id": uid,
        "username": user["username"],
        "displayName": user["displayName"],
        "created": user.get("created", ""),
        "accountAgeDays": age_days,
        "accountAgeFormatted": age_formatted,
        "avatarFull": avatar_full,
        "friendCount": counts.get("friends", 0),
        "followerCount": counts.get("followers", 0),
        "followingCount": counts.get("following", 0),
        "presence": presence,
        "groups": groups,
        "firstBadge": badges[0] if badges else None,
        "badgeCount": len(badges),
        "badgesHaveMore": len(badges) == 10,
        "threatLevel": score,
    }


def _threat_score(age_days: int, counts: dict, groups: list, badges: list) -> dict:
    score = 0

    # New accounts are more suspicious
    if age_days < 7:     score += 4
    elif age_days < 30:  score += 3
    elif age_days < 180: score += 2
    elif age_days < 365: score += 1

    # Old account with zero badges is suspicious
    if age_days > 90 and len(badges) == 0:
        score += 2
    elif age_days > 30 and len(badges) == 0:
        score += 1

    # No friends on an older account
    friends = counts.get("friends", 0)
    if age_days > 60 and friends == 0:
        score += 2
    elif age_days > 30 and friends < 3:
        score += 1

    # No group membership on older account
    if age_days > 180 and len(groups) == 0:
        score += 1

    score = min(score, 5)
    labels = ["MINIMAL", "LOW", "MODERATE", "ELEVATED", "HIGH", "CRITICAL"]
    colors = ["#50c878", "#7bc67e", "#f5a623", "#ff6b35", "#e85d7a", "#ff0040"]
    return {"score": score, "label": labels[score], "color": colors[score]}


# Mount frontend — this must come last so API routes take priority
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
