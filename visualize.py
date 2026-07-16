"""
Generates a self-contained HTML mind-map and opens it in the default browser.
No server required — the graph data is embedded directly in the HTML file.
"""
import json
import os
import tempfile
import webbrowser


_COMMUNITY_COLORS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
]

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d0d11;color:#e0e0e0;font-family:system-ui,sans-serif;display:flex;flex-direction:column;height:100vh;overflow:hidden}}

/* ── top bar ── */
#topbar{{
  display:flex;align-items:center;gap:10px;
  padding:8px 14px;background:#16161e;border-bottom:1px solid #2a2a3a;
  flex-shrink:0;
}}
#topbar h1{{font-size:13px;font-weight:600;color:#aaa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:340px}}
#search{{
  flex:1;max-width:240px;padding:5px 10px;border-radius:6px;
  background:#0d0d11;border:1px solid #333;color:#e0e0e0;font-size:13px;outline:none;
}}
#search:focus{{border-color:#4e79a7}}
#search::placeholder{{color:#555}}
.btn{{
  padding:5px 12px;border-radius:6px;border:1px solid #333;
  background:#1e1e2a;color:#ccc;font-size:12px;cursor:pointer;white-space:nowrap;
}}
.btn:hover{{background:#2a2a3a;color:#fff}}
#legend-toggle{{margin-left:auto}}

/* ── main area ── */
#main{{display:flex;flex:1;min-height:0}}

/* ── sidebar ── */
#sidebar{{
  width:260px;flex-shrink:0;background:#12121a;border-right:1px solid #1e1e2a;
  display:flex;flex-direction:column;overflow:hidden;
}}
#sidebar-head{{padding:10px 12px 6px;border-bottom:1px solid #1e1e2a;flex-shrink:0}}
#sidebar-head h2{{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#666;margin-bottom:6px}}
#cluster-sort{{
  width:100%;padding:4px 6px;background:#0d0d11;border:1px solid #222;
  color:#bbb;font-size:11px;border-radius:4px;outline:none;
}}
#cluster-list{{flex:1;overflow-y:auto;padding:6px 0}}
.cluster-item{{
  padding:7px 12px;cursor:pointer;border-left:3px solid transparent;
  transition:background .12s;
}}
.cluster-item:hover{{background:#1a1a26}}
.cluster-item.active{{background:#1a2030;border-left-color:var(--color)}}
.cluster-item .cl-header{{display:flex;align-items:center;gap:6px;font-size:12px}}
.cluster-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
.cluster-name{{font-weight:600;color:#ddd}}
.cluster-count{{margin-left:auto;color:#666;font-size:11px}}
.cluster-members{{font-size:11px;color:#666;margin-top:2px;padding-left:16px;line-height:1.5}}
.cluster-item.active .cluster-members{{color:#888}}
#show-all-btn{{margin:6px 12px;width:calc(100% - 24px)}}
#sidebar-footer{{
  padding:8px 12px;border-top:1px solid #1e1e2a;flex-shrink:0;
  display:flex;flex-direction:column;gap:4px;
}}
#bridge-toggle{{width:100%;text-align:left}}
#export-btn{{width:100%;text-align:left}}
#stats-block{{font-size:11px;color:#555;line-height:1.7;margin-top:4px}}

/* ── canvas ── */
#canvas-wrap{{flex:1;position:relative;overflow:hidden}}
svg#canvas{{width:100%;height:100%}}

/* ── graph elements ── */
.link{{stroke:#2a2a3a;stroke-opacity:.8}}
.link.follows{{stroke:#f28e2b;stroke-dasharray:4 2;stroke-opacity:.7}}
.link.highlighted{{stroke:#fff;stroke-opacity:.6}}
.link.dimmed{{stroke-opacity:.08}}

.node circle{{cursor:pointer;transition:opacity .15s}}
.node.dimmed circle{{opacity:.08}}
.node.dimmed text{{opacity:.05}}
.node text{{pointer-events:none;user-select:none}}
.node.highlighted circle{{filter:drop-shadow(0 0 6px #fff)}}

/* ── tooltip ── */
#tooltip{{
  position:fixed;top:0;left:0;pointer-events:none;
  background:rgba(14,14,22,.95);border:1px solid #333;border-radius:8px;
  padding:10px 14px;font-size:12px;max-width:220px;display:none;
  line-height:1.7;z-index:100;
}}
#tooltip img{{width:48px;height:48px;border-radius:50%;display:block;margin-bottom:6px}}
#tooltip .tip-name{{font-weight:700;font-size:13px;color:#fff}}
#tooltip .tip-badge{{
  display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;
  font-weight:600;margin-top:2px;
}}
.badge-veteran{{background:#2a4a2a;color:#7ec87e}}
.badge-mid{{background:#2a3a4a;color:#7eb4c8}}
.badge-new{{background:#4a2a2a;color:#c87e7e}}
.badge-bridge{{background:#3a3020;color:#edc948}}
.badge-seed{{background:#1e2840;color:#6ba3e8}}
</style>
</head>
<body>

<div id="topbar">
  <h1 id="page-title"></h1>
  <input id="search" type="text" placeholder="Search username…" autocomplete="off">
  <button class="btn" id="reset-zoom-btn">Reset zoom</button>
  <button class="btn" id="legend-toggle">Hide legend</button>
</div>

<div id="main">
  <div id="sidebar">
    <div id="sidebar-head">
      <h2>Clusters</h2>
      <select id="cluster-sort">
        <option value="size">Sort by size</option>
        <option value="name">Sort by name</option>
        <option value="oldest">Sort by oldest member</option>
      </select>
    </div>
    <div id="cluster-list"></div>
    <button class="btn" id="show-all-btn">Show all clusters</button>
    <div id="sidebar-footer">
      <button class="btn" id="bridge-toggle">Show bridge nodes</button>
      <button class="btn" id="export-btn">Export JSON</button>
      <div id="stats-block"></div>
    </div>
  </div>

  <div id="canvas-wrap">
    <svg id="canvas"></svg>
  </div>
</div>

<div id="tooltip"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>
// ── data ──────────────────────────────────────────────────────────────────────
const GRAPH  = {graph_json};
const COLORS = {colors_json};
const TITLE  = {title_json};

document.getElementById("page-title").textContent = TITLE;

// ── helpers ───────────────────────────────────────────────────────────────────
function accountAge(created) {{
  if (!created) return null;
  const ms = Date.now() - new Date(created).getTime();
  return ms / (1000 * 60 * 60 * 24 * 365.25); // years
}}
function ageBadge(yrs) {{
  if (yrs === null) return "";
  if (yrs >= 5)  return '<span class="tip-badge badge-veteran">Veteran</span>';
  if (yrs >= 1)  return '<span class="tip-badge badge-mid">Established</span>';
  return              '<span class="tip-badge badge-new">New account</span>';
}}
function nodeRadius(d) {{
  return d.isSeed ? 22 : Math.max(8, Math.min(20, 8 + Math.log1p(d.degree) * 3.5));
}}
function communityColor(cid) {{
  return COLORS[cid % COLORS.length];
}}

// ── svg / zoom ────────────────────────────────────────────────────────────────
const svg  = d3.select("#canvas");
const wrap = document.getElementById("canvas-wrap");
const g    = svg.append("g");
const zoom = d3.zoom().scaleExtent([0.03, 8]).on("zoom", e => g.attr("transform", e.transform));
svg.call(zoom);

function resetZoom() {{
  const W = wrap.clientWidth, H = wrap.clientHeight;
  svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity.translate(W/2, H/2).scale(0.85));
}}
document.getElementById("reset-zoom-btn").addEventListener("click", resetZoom);

// ── defs (avatar patterns) ────────────────────────────────────────────────────
const defs = svg.append("defs");
GRAPH.nodes.forEach(n => {{
  if (!n.avatarUrl) return;
  defs.append("clipPath").attr("id", `clip-${{n.id}}`)
    .append("circle").attr("r", nodeRadius(n));
  defs.append("pattern")
    .attr("id", `img-${{n.id}}`).attr("width", 1).attr("height", 1)
    .attr("patternContentUnits", "objectBoundingBox")
    .append("image")
      .attr("href", n.avatarUrl).attr("width", 1).attr("height", 1)
      .attr("preserveAspectRatio", "xMidYMid slice");
}});

// ── links ─────────────────────────────────────────────────────────────────────
const linkSel = g.append("g").selectAll("line")
  .data(GRAPH.edges).join("line")
  .attr("class", d => "link" + (d.type === "follows" ? " follows" : ""))
  .attr("stroke-width", 1);

// ── nodes ─────────────────────────────────────────────────────────────────────
const nodeSel = g.append("g").selectAll("g.node")
  .data(GRAPH.nodes).join("g")
  .attr("class", "node")
  .call(d3.drag().on("start", dragStart).on("drag", dragged).on("end", dragEnd));

nodeSel.append("circle")
  .attr("r",    d => nodeRadius(d))
  .attr("fill", d => d.avatarUrl ? `url(#img-${{d.id}})` : communityColor(d.community))
  .attr("stroke", d => {{
    if (d.isSeed)    return "#6ba3e8";
    if (d.isBridge)  return "#edc948";
    return communityColor(d.community);
  }})
  .attr("stroke-width", d => (d.isSeed || d.isBridge) ? 3 : 1.5);

// Seed label
nodeSel.filter(d => d.isSeed).append("text")
  .text(d => d.displayName || d.username)
  .attr("text-anchor", "middle").attr("dy", d => nodeRadius(d) + 13)
  .attr("fill", "#ddd").attr("font-size", 11).attr("font-weight", "700");

// ── tooltip ───────────────────────────────────────────────────────────────────
const tip = document.getElementById("tooltip");
nodeSel.on("mousemove", (ev, d) => {{
  const yrs  = accountAge(d.created);
  const cnum = d.community + 1;
  tip.innerHTML = [
    d.avatarUrl ? `<img src="${{d.avatarUrl}}" onerror="this.style.display='none'">` : "",
    `<div class="tip-name">${{d.displayName || d.username}}</div>`,
    `@${{d.username}}`,
    `<span class="tip-badge badge-seed" style="${{d.isSeed?'':'display:none'}}">Seed</span>`,
    `<span class="tip-badge badge-bridge" style="${{d.isBridge?'':'display:none'}}">Bridge node</span>`,
    ageBadge(yrs),
    `<br>ID: ${{d.id}}`,
    d.created ? `Joined: ${{d.created.slice(0,10)}} (${{yrs !== null ? yrs.toFixed(1)+' yrs' : '?'}})` : "",
    `Connections: ${{d.degree}}`,
    d.mutualCount != null ? `Mutuals: ${{d.mutualCount}}` : "",
    d.group ? `Role: ${{d.group}}` : "",
    `Cluster: ${{cnum}}`,
  ].filter(Boolean).join("<br>");
  tip.style.display = "block";
  tip.style.left = (ev.clientX + 16) + "px";
  tip.style.top  = Math.max(8, ev.clientY - 10) + "px";
}}).on("mouseleave", () => tip.style.display = "none");

// ── click to pin ──────────────────────────────────────────────────────────────
nodeSel.on("click", (ev, d) => {{
  ev.stopPropagation();
  d.fx = d.fx != null ? null : d.x;
  d.fy = d.fy != null ? null : d.y;
}});
svg.on("click", () => {{
  GRAPH.nodes.forEach(d => {{ d.fx = null; d.fy = null; }});
  sim.alpha(0.25).restart();
}});

// ── simulation ────────────────────────────────────────────────────────────────
const W = wrap.clientWidth, H = wrap.clientHeight;
const sim = d3.forceSimulation(GRAPH.nodes)
  .force("link",    d3.forceLink(GRAPH.edges).id(d => d.id).distance(70).strength(0.55))
  .force("charge",  d3.forceManyBody().strength(-280))
  .force("center",  d3.forceCenter(0, 0))
  .force("collide", d3.forceCollide(d => nodeRadius(d) + 5))
  .on("tick", () => {{
    linkSel
      .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    nodeSel.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
  }});

setTimeout(resetZoom, 100);

// ── state ─────────────────────────────────────────────────────────────────────
let activeCid     = null;
let showBridges   = false;
let searchTerm    = "";
let showLegend    = true;

function applyHighlight() {{
  const term = searchTerm.trim().toLowerCase();

  nodeSel.each(function(d) {{
    const el = d3.select(this);
    const matchSearch = !term ||
      (d.username||"").toLowerCase().includes(term) ||
      (d.displayName||"").toLowerCase().includes(term);
    const matchCluster = activeCid === null || String(d.community) === String(activeCid);
    const bridgeOnly = showBridges && !d.isBridge && !d.isSeed;

    const dim = !matchSearch || !matchCluster || bridgeOnly;
    el.classed("dimmed", dim).classed("highlighted", matchSearch && !dim && !!term);
  }});

  linkSel.each(function(d) {{
    const sNode = typeof d.source === "object" ? d.source : GRAPH.nodes.find(n=>n.id===d.source);
    const tNode = typeof d.target === "object" ? d.target : GRAPH.nodes.find(n=>n.id===d.target);
    const sDim  = !sNode || (activeCid !== null && String(sNode.community) !== String(activeCid));
    const tDim  = !tNode || (activeCid !== null && String(tNode.community) !== String(activeCid));
    d3.select(this).classed("dimmed", sDim || tDim);
  }});
}}

// ── sidebar ───────────────────────────────────────────────────────────────────
function buildClusterList(sortBy) {{
  const list = document.getElementById("cluster-list");
  list.innerHTML = "";

  const nodeById = Object.fromEntries(GRAPH.nodes.map(n => [n.id, n]));

  let entries = Object.entries(GRAPH.communities).map(([cid, members]) => {{
    const clusterNodes = GRAPH.nodes.filter(n => String(n.community) === String(cid));
    const oldest = clusterNodes
      .map(n => n.created ? new Date(n.created).getTime() : Infinity)
      .reduce((a,b) => Math.min(a,b), Infinity);
    return {{ cid, members, oldest }};
  }});

  if (sortBy === "size")   entries.sort((a,b) => b.members.length - a.members.length);
  if (sortBy === "name")   entries.sort((a,b) => a.cid - b.cid);
  if (sortBy === "oldest") entries.sort((a,b) => a.oldest - b.oldest);

  entries.forEach(({{cid, members}}, i) => {{
    const color   = COLORS[Number(cid) % COLORS.length];
    const preview = members.slice(0, 3).join(", ") + (members.length > 3 ? "…" : "");
    const item    = document.createElement("div");
    item.className = "cluster-item" + (String(cid) === String(activeCid) ? " active" : "");
    item.style.setProperty("--color", color);
    item.innerHTML = `
      <div class="cl-header">
        <span class="cluster-dot" style="background:${{color}}"></span>
        <span class="cluster-name">Cluster ${{Number(cid)+1}}</span>
        <span class="cluster-count">${{members.length}} members</span>
      </div>
      <div class="cluster-members">${{preview}}</div>`;
    item.addEventListener("click", () => {{
      activeCid = String(cid) === String(activeCid) ? null : cid;
      buildClusterList(document.getElementById("cluster-sort").value);
      applyHighlight();
    }});
    list.appendChild(item);
  }});
}}

document.getElementById("cluster-sort").addEventListener("change", e => buildClusterList(e.target.value));
document.getElementById("show-all-btn").addEventListener("click", () => {{
  activeCid = null;
  buildClusterList(document.getElementById("cluster-sort").value);
  applyHighlight();
}});

// ── search ────────────────────────────────────────────────────────────────────
document.getElementById("search").addEventListener("input", e => {{
  searchTerm = e.target.value;
  applyHighlight();
}});

// ── bridge toggle ─────────────────────────────────────────────────────────────
document.getElementById("bridge-toggle").addEventListener("click", function() {{
  showBridges = !showBridges;
  this.textContent = showBridges ? "Show all nodes" : "Show bridge nodes";
  applyHighlight();
}});

// ── legend toggle ─────────────────────────────────────────────────────────────
document.getElementById("legend-toggle").addEventListener("click", function() {{
  showLegend = !showLegend;
  document.getElementById("sidebar").style.display = showLegend ? "" : "none";
  this.textContent = showLegend ? "Hide legend" : "Show legend";
}});

// ── export ────────────────────────────────────────────────────────────────────
document.getElementById("export-btn").addEventListener("click", () => {{
  const blob = new Blob([JSON.stringify(GRAPH, null, 2)], {{type: "application/json"}});
  const a    = document.createElement("a");
  a.href     = URL.createObjectURL(blob);
  a.download = TITLE.replace(/[^a-z0-9]+/gi, "_") + ".json";
  a.click();
}});

// ── stats block ───────────────────────────────────────────────────────────────
(function() {{
  const dates = GRAPH.nodes.map(n => n.created).filter(Boolean).sort();
  const bridges = GRAPH.nodes.filter(n => n.isBridge).length;
  const sb = document.getElementById("stats-block");
  sb.innerHTML = [
    `${{GRAPH.stats.nodeCount}} people · ${{GRAPH.stats.edgeCount}} edges`,
    `${{GRAPH.stats.clusterCount}} clusters · ${{bridges}} bridge nodes`,
    dates.length ? `Oldest: ${{dates[0].slice(0,10)}}` : "",
    dates.length ? `Newest: ${{dates[dates.length-1].slice(0,10)}}` : "",
  ].filter(Boolean).join("<br>");
}})();

// ── drag ──────────────────────────────────────────────────────────────────────
function dragStart(ev, d) {{
  if (!ev.active) sim.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}}
function dragged(ev, d) {{ d.fx = ev.x; d.fy = ev.y; }}
function dragEnd(ev, d) {{
  if (!ev.active) sim.alphaTarget(0);
}}

// ── init ──────────────────────────────────────────────────────────────────────
buildClusterList("size");
</script>
</body>
</html>
"""


def open_graph(data: dict, title: str = "Roblox OSINT"):
    html = _HTML_TEMPLATE.replace("{graph_json}", json.dumps(data)) \
                         .replace("{colors_json}", json.dumps(_COMMUNITY_COLORS)) \
                         .replace("{title_json}", json.dumps(title)) \
                         .replace("{title}", title)
    fd, path = tempfile.mkstemp(suffix=".html", prefix="roblox_osint_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    webbrowser.open(f"file://{path}")
    print(f"\n  Mind-map opened in browser: {path}")
