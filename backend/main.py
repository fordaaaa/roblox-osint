import asyncio
import os

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


# Mount frontend — this must come last so API routes take priority
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
