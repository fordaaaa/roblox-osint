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

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0f0f13; color: #e0e0e0; font-family: system-ui, sans-serif; overflow: hidden; }}
  #canvas {{ width: 100vw; height: 100vh; }}
  .node circle {{ stroke-width: 2; cursor: pointer; }}
  .node image {{ pointer-events: none; }}
  .link {{ stroke: #444; stroke-opacity: 0.6; }}
  .link.follows {{ stroke: #f28e2b; stroke-dasharray: 4 2; }}
  #tooltip {{
    position: fixed; top: 0; left: 0; pointer-events: none;
    background: rgba(20,20,30,0.92); border: 1px solid #555; border-radius: 8px;
    padding: 10px 14px; font-size: 13px; max-width: 220px; display: none;
    line-height: 1.6;
  }}
  #tooltip img {{ width: 48px; height: 48px; border-radius: 50%; display: block; margin-bottom: 6px; }}
  #info-bar {{
    position: fixed; bottom: 0; left: 0; right: 0; padding: 8px 16px;
    background: rgba(15,15,19,0.85); font-size: 12px; color: #888;
    display: flex; gap: 24px; align-items: center;
  }}
  #legend {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  .legend-dot {{
    display: inline-block; width: 10px; height: 10px;
    border-radius: 50%; margin-right: 4px; vertical-align: middle;
  }}
</style>
</head>
<body>
<svg id="canvas"></svg>
<div id="tooltip"></div>
<div id="info-bar">
  <span id="stats"></span>
  <span id="legend"></span>
  <span style="margin-left:auto;opacity:.5">scroll to zoom · drag to pan · click node to pin</span>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>
const GRAPH = {graph_json};
const COLORS = {colors_json};
const TITLE  = {title_json};

const svg  = d3.select("#canvas");
const W    = window.innerWidth, H = window.innerHeight;
const g    = svg.append("g");

// Zoom
svg.call(d3.zoom().scaleExtent([0.05, 6]).on("zoom", e => g.attr("transform", e.transform)));

// Stats bar
const communityNames = Object.keys(GRAPH.communities || {{}});
document.getElementById("stats").textContent =
  `${{TITLE}} — ${{GRAPH.stats.nodeCount}} people · ${{GRAPH.stats.edgeCount}} connections · ${{GRAPH.stats.clusterCount}} cluster(s)`;

const legend = document.getElementById("legend");
communityNames.slice(0, 10).forEach((cid, i) => {{
  const members = (GRAPH.communities[cid] || []).slice(0, 3).join(", ");
  const label   = members + (GRAPH.communities[cid].length > 3 ? "…" : "");
  legend.innerHTML += `<span><span class="legend-dot" style="background:${{COLORS[i % COLORS.length]}}"></span>Cluster ${{+cid+1}} (${{GRAPH.communities[cid].length}}): ${{label}}</span>`;
}});

// Build maps
const nodeById = Object.fromEntries(GRAPH.nodes.map(n => [n.id, n]));

// Links
const link = g.append("g").selectAll("line")
  .data(GRAPH.edges).join("line")
  .attr("class", d => "link" + (d.type === "follows" ? " follows" : ""))
  .attr("stroke-width", d => d.type === "follows" ? 1 : 1.2);

// Nodes
const defs = svg.append("defs");
GRAPH.nodes.forEach(n => {{
  if (n.avatarUrl) {{
    defs.append("clipPath").attr("id", `clip-${{n.id}}`)
      .append("circle").attr("r", n.isSeed ? 22 : 14);
    defs.append("pattern")
      .attr("id", `img-${{n.id}}`).attr("width", 1).attr("height", 1)
      .attr("patternContentUnits", "objectBoundingBox")
      .append("image")
        .attr("href", n.avatarUrl)
        .attr("width", 1).attr("height", 1)
        .attr("preserveAspectRatio", "xMidYMid slice");
  }}
}});

const node = g.append("g").selectAll("g")
  .data(GRAPH.nodes).join("g")
  .attr("class", "node")
  .call(d3.drag()
    .on("start", dragstarted)
    .on("drag",  dragged)
    .on("end",   dragended));

node.append("circle")
  .attr("r",    d => d.isSeed ? 22 : 14)
  .attr("fill", d => d.avatarUrl ? `url(#img-${{d.id}})` : COLORS[d.community % COLORS.length])
  .attr("stroke", d => d.isSeed ? "#fff" : COLORS[d.community % COLORS.length])
  .attr("stroke-width", d => d.isSeed ? 3 : 1.5)
  .attr("opacity", d => d.isSeed ? 1 : 0.9);

// Label for seed nodes only
node.filter(d => d.isSeed).append("text")
  .text(d => d.displayName || d.username)
  .attr("text-anchor", "middle").attr("dy", 36)
  .attr("fill", "#fff").attr("font-size", 11).attr("font-weight", "600");

// Tooltip
const tip = document.getElementById("tooltip");
node.on("mousemove", (event, d) => {{
  const lines = [
    d.avatarUrl ? `<img src="${{d.avatarUrl}}" onerror="this.style.display='none'">` : "",
    `<strong>${{d.displayName || d.username}}</strong>`,
    `@${{d.username}}`,
    `ID: ${{d.id}}`,
    d.created ? `Joined: ${{d.created.slice(0,10)}}` : "",
    `Connections: ${{d.degree}}`,
    d.mutualCount != null ? `Mutual: ${{d.mutualCount}}` : "",
    d.group ? `Group: ${{d.group}}` : "",
    `Cluster: ${{d.community + 1}}`,
  ].filter(Boolean).join("<br>");
  tip.innerHTML = lines;
  tip.style.display = "block";
  tip.style.left = (event.clientX + 14) + "px";
  tip.style.top  = (event.clientY - 10) + "px";
}}).on("mouseleave", () => tip.style.display = "none");

// Pin on click
node.on("click", (event, d) => {{
  event.stopPropagation();
  if (d.fx != null) {{ d.fx = null; d.fy = null; }}
  else              {{ d.fx = d.x;  d.fy = d.y; }}
}});
svg.on("click", () => {{
  GRAPH.nodes.forEach(d => {{ d.fx = null; d.fy = null; }});
  simulation.alpha(0.3).restart();
}});

// Force simulation
const simulation = d3.forceSimulation(GRAPH.nodes)
  .force("link",   d3.forceLink(GRAPH.edges).id(d => d.id).distance(60).strength(0.6))
  .force("charge", d3.forceManyBody().strength(-220))
  .force("center", d3.forceCenter(W / 2, H / 2))
  .force("collide", d3.forceCollide(d => (d.isSeed ? 22 : 14) + 4))
  .on("tick", () => {{
    link
      .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
  }});

function dragstarted(event, d) {{
  if (!event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x; d.fy = d.y;
}}
function dragged(event, d) {{ d.fx = event.x; d.fy = event.y; }}
function dragended(event, d) {{
  if (!event.active) simulation.alphaTarget(0);
}}

window.addEventListener("resize", () => {{
  simulation.force("center", d3.forceCenter(window.innerWidth/2, window.innerHeight/2)).alpha(0.1).restart();
}});
</script>
</body>
</html>
"""


def open_graph(data: dict, title: str = "Roblox OSINT"):
    html = _HTML_TEMPLATE.format(
        title=title,
        graph_json=json.dumps(data),
        colors_json=json.dumps(_COMMUNITY_COLORS),
        title_json=json.dumps(title),
    )
    fd, path = tempfile.mkstemp(suffix=".html", prefix="roblox_osint_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    webbrowser.open(f"file://{path}")
    print(f"\n  Mind-map opened in browser: {path}")
