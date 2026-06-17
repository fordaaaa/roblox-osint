# Roblox OSINT — Social Graph Mindmap

A personal tool to visualize Roblox social connections as an interactive force-directed graph (Obsidian-style). Fetches friends/followers/following up to 2 levels deep via the public Roblox API, detects tight-knit clusters via Louvain community detection, and renders an explorable mindmap in the browser.

## Stack
- **Backend**: Python + FastAPI + httpx + NetworkX + python-louvain
- **Frontend**: HTML/CSS + D3.js v7 force simulation (ES modules, no build step)

## Project Structure
```
roblox-osint/
├── backend/
│   ├── main.py          # FastAPI app + API routes
│   ├── roblox_api.py    # Async Roblox API client with TTL cache
│   ├── graph.py         # Graph building + Louvain community detection
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── graph.js         # D3 force simulation, node/edge rendering
│   ├── ui.js            # Controls, search, compare mode
│   └── style.css
└── plan.md
```

## Setup & Run
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```
Then open http://localhost:8000

## API Endpoints
| Route | Description |
|---|---|
| `GET /api/graph/{username}?depth=2&followers=true&following=true` | Full graph for one user |
| `GET /api/compare?user1=x&user2=y&depth=2` | Merged comparison graph |
| `GET /api/user/{username}` | Quick profile lookup |
| `GET /api/user-by-id/{id}` | Profile by numeric ID |

## Features
- Force-directed graph with zoom, pan, drag
- Nodes coloured by Louvain community (friend clusters)
- Node size scales with connection count; seed node is largest
- Avatar thumbnails on every node
- Hover card: display name, username, join year, connection count
- Click any node to expand its 1-hop connections and merge into current view
- Compare mode: overlay two users' graphs, shared nodes glow gold
- Depth 1–3 selector
- Followers / Following toggles
- Export SVG button
- Sidebar: cluster list with member count, graph stats

## Roblox API Notes
All endpoints used are public (no auth required). In-memory cache with 5-minute TTL prevents hammering. Graph is capped at 300 nodes.
