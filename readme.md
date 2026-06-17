# Roblox Social Graph

Interactive force-directed mindmap of Roblox social connections — friends, followers, and following — with automatic friend-group cluster detection.

## Features

- **Graph view** — Obsidian-style force graph with zoom, pan, drag
- **Clusters** — Louvain community detection colours friend groups automatically
- **Avatars** — Roblox headshots rendered on every node
- **Hover cards** — display name, username, join year, connection count
- **Expand on click** — click any node to load and merge their connections
- **Compare mode** — overlay two users' graphs; shared connections glow gold
- **Followers / Following** — toggle directional edges on/off
- **Depth 1–3** — control how many hops out to explore
- **Export SVG** — save the current graph

## Setup

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

Open **http://localhost:8000**

No API keys needed — all Roblox endpoints used are public.

## Usage

1. Type a Roblox username and hit **Search**
2. The graph loads with friends coloured by cluster
3. Click any node to expand their connections into the current view
4. Toggle **Compare** and enter a second username to see shared connections
5. Use the depth selector to go deeper (depth 3 can be large — use with a capped account)
