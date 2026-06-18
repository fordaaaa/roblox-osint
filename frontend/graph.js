import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7/+esm";

export const COMMUNITY_COLORS = [
  "#6366f1","#f43f5e","#f59e0b","#10b981","#0ea5e9",
  "#a855f7","#ec4899","#14b8a6","#f97316","#8b5cf6",
];

const COMPARE_COLORS = { user1: "#6366f1", user2: "#f43f5e", common: "#f59e0b" };

let _svg, _zoomGroup, _hullLayer, _linkLayer, _nodeLayer, _defs;
let _simulation;
let _currentData  = null;
let _compareMode  = false;
let _clickCb      = null;
let _nodeMap      = new Map();
let _communityOf  = new Map();  // id → community int
let _tickN        = 0;

// ── Init ──────────────────────────────────────────────────────────────────────
export function initGraph(container) {
  _svg = d3.select(container).append("svg").attr("width", "100%").attr("height", "100%");
  _defs = _svg.append("defs");

  // Blob filter: gaussian blur → colour-matrix threshold = smooth organic group blobs
  const filt = _defs.append("filter").attr("id", "blob").attr("x", "-30%").attr("y", "-30%")
    .attr("width", "160%").attr("height", "160%");
  filt.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "14").attr("result", "blur");
  filt.append("feColorMatrix").attr("in", "blur").attr("mode", "matrix")
    .attr("values", "1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 22 -9");

  // Arrow for follows edges
  _defs.append("marker").attr("id", "arrow-follows")
    .attr("viewBox", "0 -4 8 8").attr("refX", 20).attr("refY", 0)
    .attr("markerWidth", 5).attr("markerHeight", 5).attr("orient", "auto")
    .append("path").attr("d", "M0,-4L8,0L0,4").attr("fill", "#1e6a8a");

  const zoom = d3.zoom().scaleExtent([0.05, 6])
    .on("zoom", e => _zoomGroup.attr("transform", e.transform));
  _svg.call(zoom).on("dblclick.zoom", null);

  _zoomGroup = _svg.append("g");
  _hullLayer = _zoomGroup.append("g").attr("class", "hulls");
  _linkLayer = _zoomGroup.append("g").attr("class", "links");
  _nodeLayer = _zoomGroup.append("g").attr("class", "nodes");

  const w = container.clientWidth;
  const h = container.clientHeight;

  _simulation = d3.forceSimulation()
    .force("link",      d3.forceLink().id(d => d.id))
    .force("charge",    d3.forceManyBody().strength(-380))
    .force("center",    d3.forceCenter(w / 2, h / 2))
    .force("collision", d3.forceCollide().radius(d => _r(d) + 8))
    .force("cluster",   _forceCluster(0.14));
}

// ── Cluster force ─────────────────────────────────────────────────────────────
// Pulls each node gently toward the centroid of its community.
// This is what separates groups without making the layout rigid.
function _forceCluster(strength) {
  let nodes;
  function force(alpha) {
    const cx = new Map(), cy = new Map(), cn = new Map();
    nodes.forEach(d => {
      const c = d.community ?? 0;
      cx.set(c, (cx.get(c) ?? 0) + (d.x ?? 0));
      cy.set(c, (cy.get(c) ?? 0) + (d.y ?? 0));
      cn.set(c, (cn.get(c) ?? 0) + 1);
    });
    cx.forEach((v, c) => cx.set(c, v / cn.get(c)));
    cy.forEach((v, c) => cy.set(c, v / cn.get(c)));

    nodes.forEach(d => {
      if (d.isSeed) return;
      const c = d.community ?? 0;
      d.vx += ((cx.get(c) ?? 0) - (d.x ?? 0)) * strength * alpha;
      d.vy += ((cy.get(c) ?? 0) - (d.y ?? 0)) * strength * alpha;
    });
  }
  force.initialize = n => { nodes = n; };
  return force;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _r(d) {
  if (d.isSeed) return 26;
  return Math.max(8, 5 + Math.sqrt(Math.max(d.degree || 1, 1)) * 2.5);
}

function _color(d) {
  if (_compareMode && d.group) return COMPARE_COLORS[d.group] ?? COMMUNITY_COLORS[0];
  return COMMUNITY_COLORS[(d.community ?? 0) % COMMUNITY_COLORS.length];
}

function _edgeKey(d) {
  const s = d.source?.id ?? d.source;
  const t = d.target?.id ?? d.target;
  return `${s}-${t}-${d.type}`;
}

function _label(d) {
  const n = d.displayName || d.username || "";
  return n.length > 14 ? n.slice(0, 12) + "…" : n;
}

// ── Hull rendering (run every few ticks for perf) ─────────────────────────────
function _updateHulls(nodes) {
  if (_compareMode) { _hullLayer.selectAll("*").remove(); return; }

  const byComm = d3.group(
    nodes.filter(n => !n.isSeed && n.x != null && n.y != null),
    d => d.community ?? 0
  );

  _hullLayer.selectAll("circle.hblob")
    .data(nodes.filter(n => !n.isSeed && n.x != null), d => d.id)
    .join("circle")
    .attr("class", "hblob")
    .attr("cx", d => d.x)
    .attr("cy", d => d.y)
    .attr("r",  d => _r(d) + 18)
    .attr("fill", d => COMMUNITY_COLORS[(d.community ?? 0) % COMMUNITY_COLORS.length]);
}

// ── Render ────────────────────────────────────────────────────────────────────
export function renderGraph(data, options = {}) {
  _currentData = data;
  _compareMode = options.compareMode ?? false;
  _tickN       = 0;
  _nodeMap     = new Map(data.nodes.map(n => [n.id, n]));
  _communityOf = new Map(data.nodes.map(n => [n.id, n.community ?? 0]));

  // Preserve existing positions
  const oldPos = new Map();
  _simulation.nodes().forEach(n => { if (n.x != null) oldPos.set(n.id, { x: n.x, y: n.y }); });
  data.nodes.forEach(n => { const p = oldPos.get(n.id); if (p) { n.x = p.x; n.y = p.y; } });

  // Clean stale clip paths
  _defs.selectAll("clipPath[data-node]").remove();

  // ── Links: tighter within community, looser between ──
  const link = _linkLayer.selectAll("line")
    .data(data.edges, _edgeKey)
    .join("line")
    .attr("stroke",         d => d.type === "friend" ? "#1e1e30" : "#0e3a4e")
    .attr("stroke-width",   d => d.type === "friend" ? 1.5 : 1)
    .attr("stroke-opacity", 0.85)
    .attr("marker-end",     d => d.type === "follows" ? "url(#arrow-follows)" : null);

  _simulation.force("link")
    .links(data.edges)
    .distance(d => {
      const sc = _communityOf.get(d.source?.id ?? d.source);
      const tc = _communityOf.get(d.target?.id ?? d.target);
      return sc === tc ? 55 : 130;
    })
    .strength(d => {
      const sc = _communityOf.get(d.source?.id ?? d.source);
      const tc = _communityOf.get(d.target?.id ?? d.target);
      return sc === tc ? 0.7 : 0.15;
    });

  // ── Nodes ──
  const node = _nodeLayer.selectAll("g.node")
    .data(data.nodes, d => d.id)
    .join(
      enter => {
        const g = enter.append("g").attr("class", "node");

        g.each(function(d) {
          _defs.append("clipPath")
            .attr("id", `clip-${d.id}`).attr("data-node", d.id)
            .append("circle").attr("r", _r(d) - 1);
        });

        g.append("circle").attr("class", "bg").attr("r", _r).attr("fill", _color);

        g.append("image").attr("class", "avatar")
          .attr("clip-path", d => `url(#clip-${d.id})`)
          .attr("x",      d => -(_r(d) - 1)).attr("y",      d => -(_r(d) - 1))
          .attr("width",  d => (_r(d) - 1) * 2).attr("height", d => (_r(d) - 1) * 2)
          .attr("href",   d => d.avatarUrl || "")
          .attr("preserveAspectRatio", "xMidYMid slice");

        g.append("circle").attr("class", "ring").attr("r", _r).attr("fill", "none")
          .attr("stroke", d => d.isSeed ? "#fff" : "none").attr("stroke-width", 2.5);

        g.append("text")
          .attr("y", d => _r(d) + 13).attr("text-anchor", "middle")
          .attr("font-size", "10px").attr("fill", "#6b6b8a")
          .attr("pointer-events", "none").text(_label);

        g.call(d3.drag()
          .on("start", (e, d) => { if (!e.active) _simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag",  (e, d) => { d.fx = e.x; d.fy = e.y; })
          .on("end",   (e, d) => { if (!e.active) _simulation.alphaTarget(0); d.fx = null; d.fy = null; })
        )
        .on("mouseenter", _showHover)
        .on("mouseleave", _hideHover)
        .on("click",      (e, d) => { e.stopPropagation(); if (_clickCb) _clickCb(d); });

        return g;
      },
      update => update,
      exit => {
        exit.each(d => { _defs.select(`#clip-${d.id}`).remove(); });
        exit.remove();
      }
    );

  node.select("circle.bg").attr("fill", _color).attr("r", _r);
  node.select("circle.ring").attr("stroke", d => d.isSeed ? "#fff" : "none").attr("r", _r);
  node.select("text").text(_label);
  node.select("image.avatar").attr("href", d => d.avatarUrl || "");

  // ── Simulation ──
  _simulation.nodes(data.nodes).on("tick", () => {
    _tickN++;
    // Update hulls every 4 ticks — cheap enough, smooth enough
    if (_tickN % 4 === 0) _updateHulls(data.nodes);

    link
      .attr("x1", d => d.source?.x ?? 0).attr("y1", d => d.source?.y ?? 0)
      .attr("x2", d => d.target?.x ?? 0).attr("y2", d => d.target?.y ?? 0);
    node.attr("transform", d => `translate(${d.x ?? 0},${d.y ?? 0})`);
  });

  _simulation.alpha(0.7).restart();
}

// ── Hover card ────────────────────────────────────────────────────────────────
function _showHover(event, d) {
  const card = document.getElementById("hover-card");
  let meta = "";
  if (d.mutualCount != null && !d.isSeed)
    meta = `${d.mutualCount} mutual in group`;
  else if (d.degree != null)
    meta = `${d.degree} connection${d.degree !== 1 ? "s" : ""}`;
  if (d.created) meta += ` · ${new Date(d.created).getFullYear()}`;

  card.innerHTML = `
    <div class="hc-avatar">${d.avatarUrl ? `<img src="${d.avatarUrl}" alt="">` : ""}</div>
    <div class="hc-info">
      <div class="hc-name">${d.displayName || d.username}</div>
      <div class="hc-user">@${d.username}</div>
      <div class="hc-meta">${meta}</div>
    </div>`;
  card.style.cssText = `display:flex; left:${event.pageX + 14}px; top:${event.pageY - 10}px`;
}
function _hideHover() { document.getElementById("hover-card").style.display = "none"; }

// ── Merge ─────────────────────────────────────────────────────────────────────
export function mergeGraph(newData) {
  if (!_currentData) { renderGraph(newData); return; }
  const existIds     = new Set(_currentData.nodes.map(n => n.id));
  const existEdgeKeys = new Set(_currentData.edges.map(_edgeKey));
  _currentData = {
    ..._currentData,
    nodes: [..._currentData.nodes, ...newData.nodes.filter(n => !existIds.has(n.id))],
    edges: [..._currentData.edges, ...newData.edges.filter(e => !existEdgeKeys.has(_edgeKey(e)))],
    communities: { ..._currentData.communities, ...newData.communities },
    stats: newData.stats,
  };
  renderGraph(_currentData, { compareMode: _compareMode });
}

// ── Public API ────────────────────────────────────────────────────────────────
export function onNodeClick(cb)  { _clickCb = cb; }
export function getNodeData(id)  { return _nodeMap.get(id); }
export function getCurrentData() { return _currentData; }

export function highlightNode(query) {
  const q = query.toLowerCase();
  _nodeLayer.selectAll("g.node").select("circle.ring")
    .attr("stroke", d => {
      if (!q) return d.isSeed ? "#fff" : "none";
      return (d.username?.toLowerCase().includes(q) || d.displayName?.toLowerCase().includes(q))
        ? "#f59e0b" : d.isSeed ? "#fff" : "none";
    })
    .attr("stroke-width", d => {
      const hit = q && (d.username?.toLowerCase().includes(q) || d.displayName?.toLowerCase().includes(q));
      return hit ? 3 : 2.5;
    });
}

export function highlightClique(cliqueId) {
  _nodeLayer.selectAll("g.node").select("circle.bg")
    .attr("opacity", d => (cliqueId == null || d.cliqueId === cliqueId || d.isSeed) ? 1 : 0.2);
}

export function updateLegend(communities, compareMode = false) {
  const list = document.getElementById("legend-list");
  list.innerHTML = "";
  if (compareMode) {
    for (const [, label, color] of [
      ["user1","User 1",COMPARE_COLORS.user1],
      ["user2","User 2",COMPARE_COLORS.user2],
      ["common","Shared",COMPARE_COLORS.common],
    ]) {
      const li = document.createElement("li");
      li.innerHTML = `<span class="legend-dot" style="background:${color}"></span><span class="legend-name">${label}</span>`;
      list.appendChild(li);
    }
    return;
  }
  Object.entries(communities)
    .sort((a, b) => b[1].length - a[1].length)
    .forEach(([cid, members]) => {
      const color = COMMUNITY_COLORS[parseInt(cid) % COMMUNITY_COLORS.length];
      const li = document.createElement("li");
      li.title = members.slice(0, 20).join(", ") + (members.length > 20 ? "…" : "");
      li.innerHTML = `
        <span class="legend-dot" style="background:${color}"></span>
        <span class="legend-name">Cluster ${parseInt(cid) + 1}</span>
        <span class="legend-count">${members.length}</span>`;
      list.appendChild(li);
    });
}

export function updateStats(stats) {
  document.getElementById("stats-block").innerHTML = `
    <strong>${stats.nodeCount}</strong> nodes<br>
    <strong>${stats.edgeCount}</strong> edges<br>
    <strong>${stats.clusterCount}</strong> cluster${stats.clusterCount !== 1 ? "s" : ""}`;
}

export function exportSVG() {
  const el = document.querySelector("#graph-canvas svg");
  if (!el) return;
  const src  = new XMLSerializer().serializeToString(el);
  const blob = new Blob([src], { type: "image/svg+xml" });
  const url  = URL.createObjectURL(blob);
  Object.assign(document.createElement("a"), { href: url, download: "roblox-graph.svg" }).click();
  URL.revokeObjectURL(url);
}
