# Roblox OSINT Tool — Roadmap

All data used is from Roblox's public API. No authentication, no scraping — if it's visible on someone's profile, it's available here.

---

## What's already built

- Search any username → force-directed graph of their friends/followers/following
- Friend cluster detection (Louvain algorithm — auto colour-codes tight friend groups)
- Hover cards with avatar, username, join date
- Click any node to expand their connections into the same graph
- Compare two users — shared connections glow gold
- Depth 1–3 selector
- Export SVG

---

## Phase 1 — Make the graph actually usable
*The foundation needs to be solid before building on top.*

- [ ] **Sidebar node list** — list every person in the graph with their avatar, click to highlight them
- [ ] **Search within graph** — type a name, that node pulses/zooms to
- [ ] **Filter by edge type** — toggle friend/follower/following edges live without re-fetching
- [ ] **Node info panel** — click a node and get a proper side panel with all their info, not just a hover
- [ ] **Pin nodes** — lock a node in place so the graph doesn't shuffle it around
- [ ] **Mutual count on edges** — show how many mutual friends two connected people share

---

## Phase 2 — Deep profile data
*Turn every node from just a name into a full profile.*

Pull additional public data from Roblox and show it in the node panel:

- **Join date** — already have this; useful for alt detection
- **Last online** — if public on their profile
- **Bio / description**
- **Badge count + earliest badge** — good for estimating real account age vs join date
- **Groups** — which Roblox groups they're in (can reveal communities, clans, game groups)
- **Verified / Premium status**
- **Follower / following counts** (not just the list — the raw numbers)
- **Friend count**

Clicking a node opens all of this. Visually flag things like: account has 0 badges, joined recently, in no groups — potential throwaway/alt.

---

## Phase 3 — OSINT investigation features
*This is where it becomes a proper tool.*

### Mutual path finder
Given two usernames, find the shortest chain of mutual friends connecting them.
"UserA → FriendB → FriendC → UserZ" — like Six Degrees of Kevin Bacon but for Roblox.

### Alt account detector
Flag nodes that match suspicious patterns:
- Same friend group but joined much later / earlier
- Very few badges relative to join date
- Friends only with one or two people in the graph
- Username similar to another node (e.g. "XxUser123" and "XxUser1234")
- No groups, no game history, no bio

Not definitive proof — but useful signals grouped together.

### Group explorer
Search a Roblox **group** instead of a user. Graph all the members and their connections to each other. See which members are actually friends vs just in the same group. Useful for investigating game communities, clans, etc.

### Shared groups / interests overlay
When viewing someone's graph, show which of their friends are also in the same groups as them. Another layer of "how are these people actually connected."

### Account timeline
For a single user: show a chronological view of when they joined, when they got their first badge, when they friended certain people. Can reveal if an account was dormant and then suddenly active, or if a bunch of friends were added at the same time (suggesting they met in a specific game or event).

---

## Phase 4 — Quality of life + export
*Make it shareable and saveable.*

- [ ] **Save investigation** — export a full JSON snapshot of a graph so you can reload it later without re-fetching
- [ ] **Load saved graph** — drag-and-drop or file picker to reload a saved session
- [ ] **Notes on nodes** — annotate any node with your own text ("possible alt", "real name known", etc.)
- [ ] **Export report** — generate a readable HTML or PDF summary of an investigation
- [ ] **Dark/light toggle** — minor but nice
- [ ] **Search history** — remember last 10 searches

---

## Phase 5 — Game-level OSINT (advanced)
*Goes deeper than just social connections.*

Roblox's API exposes game/experience data:

- **Recently played games** — what experiences a user has been playing
- **In-game presence** — if their privacy allows it, what game they're in right now
- **Game-based friend graphs** — two people who aren't friends but always show up in the same game servers are probably connected IRL
- **Favorite games** — can reveal interests, communities they're part of

This is the most powerful layer for actual investigation — social friends are obvious, but game overlap is harder to hide.

---

## What to build next

Suggested order based on impact:

1. **Node info panel** (Phase 1) — makes everything else more useful
2. **Deep profile data** (Phase 2) — join date, badges, groups in the panel
3. **Alt detector flags** (Phase 3) — visual indicators on suspicious nodes
4. **Save/load graph** (Phase 4) — so investigations persist
5. **Mutual path finder** (Phase 3) — genuinely fun and useful
6. **Group explorer** (Phase 3) — big unlock for community investigation

---

## Data available from public Roblox API (no auth needed)

| Data | Endpoint |
|---|---|
| Profile info | `users.roblox.com/v1/users/{id}` |
| Friends list | `friends.roblox.com/v1/users/{id}/friends` |
| Followers | `friends.roblox.com/v1/users/{id}/followers` |
| Following | `friends.roblox.com/v1/users/{id}/followings` |
| Groups | `groups.roblox.com/v1/users/{id}/groups/roles` |
| Badges | `badges.roblox.com/v1/users/{id}/badges` |
| Presence | `presence.roblox.com/v1/presence/users` |
| Avatar headshot | `thumbnails.roblox.com/v1/users/avatar-headshot` |
| Games played | `games.roblox.com/v2/users/{id}/games` |
| Search username → ID | `users.roblox.com/v1/usernames/users` |
