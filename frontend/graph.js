import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7/+esm";

export const COMMUNITY_COLORS = [
  "#7c6aed", "#e85d7a", "#f5a623", "#50c878", "#00b4d8",
  "#ff6b35", "#c77dff", "#06d6a0", "#ffd166", "#ef476f",
];

const COMPARE_COLORS = {
  user1: "#7c6aed",
  user2: "#e85d7a",
  common: "#ffd700",
};

let _svg, _zoomGroup, _linkLayer, _nodeLayer, _defs;
let _simulation;
let _currentData = null;
let _compareMode = false;
let _expandCallback = null;
let _nodeDataMap = new Map(); // id → node data (for expand on click)

export function initGraph(container) {
  _svg = d3.select(container)
    .append("svg")
    .attr("width", "100%")
    .attr("height", "100%");

  _defs = _svg.append("defs");

  // Arrow markers for directed "follows" edges
  for (const [id, color] of [["follows", "#4fc3f7"], ["friend", "#455a64"]]) {
    _defs.append("marker")
      .attr("id", `arrow-${id}`)
      .attr("viewBox", "0 -4 8 8")
      .attr("refX", 18)
      .attr("refY", 0)
      .attr("markerWidth", 5)
      .attr("markerHeight", 5)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-4L8,0L0,4")
      .attr("fill", color);
  }

  const zoom = d3.zoom()
    .scaleExtent([0.05, 5])
    .on("zoom", (e) => _zoomGroup.attr("transform", e.transform));

  _svg.call(zoom).on("dblclick.zoom", null);

  _zoomGroup = _svg.append("g");
  _linkLayer = _zoomGroup.append("g").attr("class", "links");
  _nodeLayer = _zoomGroup.append("g").attr("class", "nodes");

  const w = container.clientWidth;
  const h = container.clientHeight;

  _simulation = d3.forceSimulation()
    .force("link", d3.forceLink().id(d => d.id).distance(90).strength(0.4))
    .force("charge", d3.forceManyBody().strength(-280))
    .force("center", d3.forceCenter(w / 2, h / 2))
    .force("collision", d3.forceCollide().radius(d => _radius(d) + 6));
}

function _radius(d) {
  if (d.isSeed) return 24;
  return Math.max(8, 5 + Math.sqrt(Math.max(d.degree || 1, 1)) * 2.5);
}

function _color(d) {
  if (_compareMode && d.group) return COMPARE_COLORS[d.group] ?? COMMUNITY_COLORS[0];
  return COMMUNITY_COLORS[(d.community ?? 0) % COMMUNITY_COLORS.length];
}

function _clipId(d) { return `clip-${d.id}`; }

export function renderGraph(data, options = {}) {
  _currentData = data;
  _compareMode = options.compareMode ?? false;
  _nodeDataMap = new Map(data.nodes.map(n => [n.id, n]));

  // Keep existing node positions when merging
  const existingPos = new Map();
  _simulation.nodes().forEach(n => {
    if (n.x != null) existingPos.set(n.id, { x: n.x, y: n.y });
  });

  data.nodes.forEach(n => {
    const pos = existingPos.get(n.id);
    if (pos) { n.x = pos.x; n.y = pos.y; }
  });

  // ── Links ──
  const link = _linkLayer
    .selectAll("line")
    .data(data.edges, d => `${d.source.id ?? d.source}-${d.target.id ?? d.target}-${d.type}`)
    .join("line")
    .attr("stroke", d => d.type === "friend" ? "#2d3748" : "#1a4f6e")
    .attr("stroke-width", d => d.type === "friend" ? 1.5 : 1)
    .attr("stroke-opacity", 0.8)
    .attr("marker-end", d => d.type === "follows" ? "url(#arrow-follows)" : null);

  // ── Node groups ──
  const node = _nodeLayer
    .selectAll("g.node")
    .data(data.nodes, d => d.id)
    .join(
      enter => enter.append("g").attr("class", "node").call(_setupNode),
      update => update,
      exit => exit.remove(),
    );

  // Update colour on all nodes (community may have changed after merge)
  node.select("circle.bg").attr("fill", d => _color(d));
  node.select("circle.ring")
    .attr("stroke", d => d.isSeed ? "#fff" : "none")
    .attr("r", d => _radius(d));
  node.select("text").text(d => _label(d));

  // ── Simulation ──
  _simulation
    .nodes(data.nodes)
    .on("tick", () => {
      link
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);
      node.attr("transform", d => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

  _simulation.force("link").links(data.edges);
  _simulation.alpha(0.6).restart();
}

function _label(d) {
  const name = d.displayName || d.username || "";
  return name.length > 14 ? name.slice(0, 12) + "…" : name;
}

function _setupNode(selection) {
  selection
    .call(d3.drag()
      .on("start", (e, d) => { if (!e.active) _simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on("end", (e, d) => { if (!e.active) _simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    )
    .on("mouseenter", _showCard)
    .on("mouseleave", _hideCard)
    .on("click", (e, d) => { e.stopPropagation(); if (_expandCallback) _expandCallback(d); });

  // Background fill circle
  selection.append("circle")
    .attr("class", "bg")
    .attr("r", d => _radius(d))
    .attr("fill", d => _color(d));

  // Clip path for avatar
  selection.each(function(d) {
    _defs.append("clipPath")
      .attr("id", _clipId(d))
      .append("circle")
      .attr("r", d => _radius(d) - 1);
  });

  // Avatar image (set later; placeholder empty)
  selection.append("image")
    .attr("class", "avatar")
    .attr("clip-path", d => `url(#${_clipId(d)})`)
    .attr("x", d => -(_radius(d) - 1))
    .attr("y", d => -(_radius(d) - 1))
    .attr("width", d => (_radius(d) - 1) * 2)
    .attr("height", d => (_radius(d) - 1) * 2)
    .attr("href", d => d.avatarUrl || "")
    .attr("preserveAspectRatio", "xMidYMid slice");

  // Seed ring
  selection.append("circle")
    .attr("class", "ring")
    .attr("r", d => _radius(d))
    .attr("fill", "none")
    .attr("stroke", d => d.isSeed ? "#fff" : "none")
    .attr("stroke-width", 2.5);

  // Label
  selection.append("text")
    .attr("y", d => _radius(d) + 13)
    .attr("text-anchor", "middle")
    .attr("font-size", "10px")
    .attr("fill", "#8b949e")
    .attr("pointer-events", "none")
    .text(d => _label(d));
}

// ── Hover card ──
function _showCard(event, d) {
  const card = document.getElementById("hover-card");
  card.innerHTML = `
    <div class="card-avatar">
      ${d.avatarUrl ? `<img src="${d.avatarUrl}" alt="">` : ""}
    </div>
    <div class="card-info">
      <div class="card-display">${d.displayName || d.username}</div>
      <div class="card-username">@${d.username}</div>
      ${d.created ? `<div class="card-joined">Joined ${new Date(d.created).getFullYear()}</div>` : ""}
      <div class="card-degree">${d.degree} connection${d.degree !== 1 ? "s" : ""}</div>
      ${d.group ? `<div class="card-joined" style="color:${COMPARE_COLORS[d.group]}">${d.group === "common" ? "Shared" : d.group === "user1" ? "User 1 only" : "User 2 only"}</div>` : ""}
    </div>
  `;
  card.style.display = "flex";
  card.style.left = (event.pageX + 14) + "px";
  card.style.top  = (event.pageY - 10) + "px";
}

function _hideCard() {
  document.getElementById("hover-card").style.display = "none";
}

// ── Public helpers ──
export function mergeGraph(newData) {
  if (!_currentData) { renderGraph(newData); return; }

  const existingIds  = new Set(_currentData.nodes.map(n => n.id));
  const existingEdgeKeys = new Set(
    _currentData.edges.map(e => `${e.source.id ?? e.source}-${e.target.id ?? e.target}-${e.type}`)
  );

  const addedNodes = newData.nodes.filter(n => !existingIds.has(n.id));
  const addedEdges = newData.edges.filter(e => {
    const key = `${e.source}-${e.target}-${e.type}`;
    return !existingEdgeKeys.has(key);
  });

  _currentData = {
    ..._currentData,
    nodes: [..._currentData.nodes, ...addedNodes],
    edges: [..._currentData.edges, ...addedEdges],
    communities: { ..._currentData.communities, ...newData.communities },
    stats: newData.stats,
  };

  renderGraph(_currentData, { compareMode: _compareMode });
}

export function onNodeExpand(cb) { _expandCallback = cb; }

export function getNodeData(id) { return _nodeDataMap.get(id); }

export function updateLegend(communities, compareMode = false) {
  const list = document.getElementById("legend-list");
  list.innerHTML = "";

  if (compareMode) {
    const wrap = document.createElement("div");
    wrap.className = "compare-legend";
    for (const [key, label, color] of [
      ["user1", "User 1", COMPARE_COLORS.user1],
      ["user2", "User 2", COMPARE_COLORS.user2],
      ["common", "Shared", COMPARE_COLORS.common],
    ]) {
      const s = document.createElement("span");
      s.innerHTML = `<span class="legend-dot" style="background:${color}"></span>${label}`;
      wrap.appendChild(s);
    }
    list.appendChild(wrap);
    return;
  }

  Object.entries(communities)
    .sort((a, b) => b[1].length - a[1].length)
    .forEach(([cid, members]) => {
      const color = COMMUNITY_COLORS[parseInt(cid) % COMMUNITY_COLORS.length];
      const li = document.createElement("li");
      li.title = members.slice(0, 15).join(", ") + (members.length > 15 ? "…" : "");
      li.innerHTML = `
        <span class="legend-dot" style="background:${color}"></span>
        <span class="legend-label">Cluster ${parseInt(cid) + 1}</span>
        <span class="legend-count">${members.length}</span>
      `;
      list.appendChild(li);
    });
}

export function updateStats(stats) {
  document.getElementById("stats").innerHTML = `
    <strong>${stats.nodeCount}</strong> nodes &nbsp;·&nbsp;
    <strong>${stats.edgeCount}</strong> edges<br>
    <strong>${stats.clusterCount}</strong> cluster${stats.clusterCount !== 1 ? "s" : ""}
  `;
}

export function exportSVG() {
  const svgEl = document.querySelector("#graph-container svg");
  const src = new XMLSerializer().serializeToString(svgEl);
  const blob = new Blob([src], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: "roblox-graph.svg" });
  a.click();
  URL.revokeObjectURL(url);
}
