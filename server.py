"""
Roblox OSINT — web UI.
Run:  venv/bin/python3 server.py
Then visit http://localhost:7390 in your browser.
"""
import asyncio
import json
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import roblox_api as api
import graph as graph_module

PORT    = 7390
UI_FILE = Path(__file__).parent / "ui.html"


async def _resolve(username: str) -> int:
    uid = await api.resolve_username(username)
    if uid is None:
        raise ValueError(f"'{username}' not found on Roblox")
    if uid == -1:
        raise ValueError("Roblox API is rate-limited — wait a moment and retry")
    return uid


async def _profile(p):
    u = p.get("username", [""])[0].strip()
    if not u:
        raise ValueError("username is required")
    uid = await _resolve(u)
    user, counts, groups, badges, presence = await asyncio.gather(
        api.get_user(uid), api.get_counts(uid), api.get_groups(uid),
        api.get_badges(uid, limit=10, oldest_first=True), api.get_presence(uid),
    )
    if not user:
        raise ValueError("Failed to fetch user — Roblox may be rate-limiting")
    av = await api.get_avatar_full(uid)
    return {
        "id": uid,
        "username": user["username"],
        "displayName": user["displayName"],
        "created": user.get("created", ""),
        "isBanned": user.get("isBanned", False),
        "avatarUrl": av,
        "counts": counts,
        "groups": groups[:25],
        "badges": badges,
        "presence": presence,
    }


async def _friends(p):
    u = p.get("username", [""])[0].strip()
    if not u:
        raise ValueError("username is required")
    uid = await _resolve(u)
    friends = await api.get_friends(uid)
    return {"username": u, "uid": uid, "friends": friends}


async def _circle(p):
    u = p.get("username", [""])[0].strip()
    if not u:
        raise ValueError("username is required")
    uid = await _resolve(u)
    return await graph_module.build_inner_circle(uid)


async def _explore(p):
    u = p.get("username", [""])[0].strip()
    depth = max(1, min(3, int(p.get("depth", ["2"])[0])))
    if not u:
        raise ValueError("username is required")
    uid = await _resolve(u)
    G = await graph_module.build_graph(uid, depth=depth)
    return graph_module.graph_to_json(G, seed_ids=[uid])


async def _compare(p):
    u1 = p.get("user1", [""])[0].strip()
    u2 = p.get("user2", [""])[0].strip()
    if not u1 or not u2:
        raise ValueError("both user1 and user2 are required")
    uid1, uid2 = await asyncio.gather(_resolve(u1), _resolve(u2))
    return await graph_module.compare_graphs(uid1, uid2)


async def _alts(p):
    u        = p.get("username", [""])[0].strip()
    window   = max(1, int(p.get("window",   ["30"])[0]))
    min_size = max(2, int(p.get("min_size", ["3"])[0]))
    if not u:
        raise ValueError("username is required")
    uid     = await _resolve(u)
    friends = await api.get_friends(uid)
    if not friends:
        return {"username": u, "checked": 0, "groups": []}

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
                dated.append({**f, "created": user["created"], "_ts": dt.timestamp()})
            except ValueError:
                pass

    dated.sort(key=lambda x: x["_ts"])
    win    = window * 86400
    groups, used = [], set()
    for i, anchor in enumerate(dated):
        if anchor["id"] in used:
            continue
        grp = [anchor]
        for item in dated[i + 1:]:
            if item["_ts"] - anchor["_ts"] <= win:
                grp.append(item)
            else:
                break
        if len(grp) >= min_size:
            for m in grp:
                used.add(m["id"])
            span = int((grp[-1]["_ts"] - grp[0]["_ts"]) / 86400)
            groups.append({
                "span_days":  span,
                "date_start": grp[0]["created"][:10],
                "date_end":   grp[-1]["created"][:10],
                "members":    [{k: v for k, v in m.items() if k != "_ts"} for m in grp],
            })

    return {"username": u, "checked": len(dated), "groups": groups}


HANDLERS = {
    "profile": _profile,
    "friends": _friends,
    "circle":  _circle,
    "explore": _explore,
    "compare": _compare,
    "alts":    _alts,
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path, params = parsed.path, parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._serve_ui()
        elif path.startswith("/api/"):
            cmd = path[5:].strip("/")
            if cmd not in HANDLERS:
                return self._json(404, {"ok": False, "error": f"unknown command: {cmd}"})
            try:
                data = asyncio.run(HANDLERS[cmd](params))
                self._json(200, {"ok": True, "data": data})
            except Exception as e:
                self._json(400, {"ok": False, "error": str(e)})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def _serve_ui(self):
        try:
            body = UI_FILE.read_bytes()
        except FileNotFoundError:
            self.send_error(500, "ui.html not found — run server.py from the project directory")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url    = f"http://127.0.0.1:{PORT}"
    print(f"Roblox OSINT UI  →  {url}")
    print("Ctrl+C to stop.\n")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
