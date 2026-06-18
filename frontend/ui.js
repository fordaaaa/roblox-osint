import {
  initGraph, renderGraph, mergeGraph,
  updateLegend, updateStats,
  onNodeClick, highlightNode, highlightClique,
  exportSVG,
} from "./graph.js";

import { openDossier, closeDossier, onDossierExpand } from "./profile.js";

// ── State ──────────────────────────────────────────────────────────────────
let _username    = null;
let _mode        = "inner-circle";   // inner-circle | followers | following | explore | compare
let _depth       = 2;
let _compareMode = false;

// ── Boot ───────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initGraph(document.getElementById("graph-canvas"));

  // Home: single search
  q("home-search-form").addEventListener("submit", async e => {
    e.preventDefault();
    const u = q("home-username").value.trim();
    if (!u) return;
    _compareMode = false;
    await goToGraph(u, _mode);
  });

  // Home: compare
  q("home-compare-form").addEventListener("submit", async e => {
    e.preventDefault();
    const u1 = q("compare-user1").value.trim();
    const u2 = q("compare-user2").value.trim();
    if (!u1 || !u2) return;
    _compareMode = true;
    await goToCompare(u1, u2);
  });

  // Graph: back
  q("back-btn").addEventListener("click", () => showView("home"));

  // Graph: reload
  q("reload-btn").addEventListener("click", async () => {
    if (_username) await goToGraph(_username, _mode);
  });

  // Graph: mode tabs
  document.querySelectorAll(".mode-tab").forEach(btn => {
    btn.addEventListener("click", async () => {
      _mode = btn.dataset.mode;
      _compareMode = false;
      document.querySelectorAll(".mode-tab").forEach(b => b.classList.remove("selected"));
      btn.classList.add("selected");
      q("depth-control").style.display = _mode === "explore" ? "flex" : "none";
      if (_username) await goToGraph(_username, _mode);
    });
  });

  // Graph: depth
  document.querySelectorAll(".depth-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      _depth = parseInt(btn.dataset.depth);
      document.querySelectorAll(".depth-btn").forEach(b => b.classList.remove("selected"));
      btn.classList.add("selected");
      if (_username && _mode === "explore") goToGraph(_username, "explore");
    });
  });

  // Graph: export
  q("export-btn").addEventListener("click", exportSVG);

  // Dossier close
  q("dossier-close-btn").addEventListener("click", closeDossier);

  // Node click → dossier
  onNodeClick(node => openDossier(node));

  // Expand from dossier
  onDossierExpand(async profile => {
    await expandNode(profile.username);
  });

  // Sidebar: search
  q("node-search").addEventListener("input", e => {
    highlightNode(e.target.value.trim());
  });
});

// ── Navigation ─────────────────────────────────────────────────────────────
function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
}

async function goToGraph(username, mode) {
  _username = username;
  _mode     = mode;
  showView("graph");

  switch (mode) {
    case "inner-circle": await loadInnerCircle(username);  break;
    case "followers":    await loadFollowGraph(username, "followers"); break;
    case "following":    await loadFollowGraph(username, "following"); break;
    case "explore":      await loadExplore(username);      break;
  }
}

async function goToCompare(u1, u2) {
  _username = u1;
  _compareMode = true;
  showView("graph");
  await loadCompare(u1, u2);
}

// ── Graph loaders ──────────────────────────────────────────────────────────
async function loadInnerCircle(username) {
  setLoading(true, `Mapping ${username}'s friend groups…`);
  try {
    const data = await apiFetch(`/api/inner-circle/${enc(username)}`);
    renderGraph(data);
    updateLegend(data.communities, false);
    updateStats(data.stats);
    updateSubjectHeader(username, data.nodes);
    renderCliqueList(data.nodes, data.communities);
  } catch(e) { toast(e.message); }
  finally    { setLoading(false); }
}

async function loadFollowGraph(username, mode) {
  const label = mode === "followers" ? "followers" : "following";
  setLoading(true, `Fetching ${username}'s ${label}…`);
  try {
    const data = await apiFetch(`/api/${label}/${enc(username)}`);
    renderGraph(data);
    updateLegend(data.communities, false);
    updateStats(data.stats);
    updateSubjectHeader(username, data.nodes);
    hideCliqueList();
  } catch(e) { toast(e.message); }
  finally    { setLoading(false); }
}

async function loadExplore(username) {
  setLoading(true, `Exploring ${username}'s network (depth ${_depth})…`);
  try {
    const data = await apiFetch(`/api/explore/${enc(username)}?depth=${_depth}`);
    renderGraph(data);
    updateLegend(data.communities, false);
    updateStats(data.stats);
    updateSubjectHeader(username, data.nodes);
    hideCliqueList();
  } catch(e) { toast(e.message); }
  finally    { setLoading(false); }
}

async function loadCompare(u1, u2) {
  setLoading(true, `Comparing ${u1} vs ${u2}…`);
  try {
    const data = await apiFetch(`/api/compare?user1=${enc(u1)}&user2=${enc(u2)}`);
    renderGraph(data, { compareMode: true });
    updateLegend(data.communities, true);
    updateStats(data.stats);
    const n1 = data.nodes.find(n => n.isSeed && n.username.toLowerCase() === u1.toLowerCase());
    updateSubjectHeader(`${u1} vs ${u2}`, data.nodes, n1?.avatarUrl);
    hideCliqueList();
  } catch(e) { toast(e.message); }
  finally    { setLoading(false); }
}

async function expandNode(username) {
  setLoading(true, `Expanding ${username}…`);
  try {
    const data = await apiFetch(`/api/inner-circle/${enc(username)}`);
    mergeGraph(data);
    updateLegend(data.communities, _compareMode);
    updateStats(data.stats);
  } catch(e) { console.error("Expand failed:", e); }
  finally    { setLoading(false); }
}

// ── Clique sidebar ─────────────────────────────────────────────────────────
function renderCliqueList(nodes, communities) {
  const section = q("clique-section");
  const list    = q("clique-list");
  list.innerHTML = "";

  const cliqued = nodes.filter(n => n.cliqueId != null && !n.isSeed);
  if (!cliqued.length) { section.style.display = "none"; return; }

  section.style.display = "block";

  // Group by cliqueId
  const cliques = {};
  cliqued.forEach(n => {
    const k = n.cliqueId;
    if (!cliques[k]) cliques[k] = [];
    cliques[k].push(n);
  });

  Object.entries(cliques)
    .sort((a, b) => b[1].length - a[1].length)
    .forEach(([cid, members]) => {
      const wrap = document.createElement("div");
      wrap.className = "clique-item";
      wrap.innerHTML = `
        <div class="clique-header">
          <span class="clique-size">${members.length} people</span>
          <span class="clique-badge">all mutual</span>
        </div>
        <div class="clique-names">${members.map(m => m.displayName || m.username).slice(0, 6).join(", ")}${members.length > 6 ? "…" : ""}</div>`;
      wrap.addEventListener("mouseenter", () => highlightClique(parseInt(cid)));
      wrap.addEventListener("mouseleave", () => highlightClique(null));
      list.appendChild(wrap);
    });
}

function hideCliqueList() {
  q("clique-section").style.display = "none";
}

// ── Subject header ─────────────────────────────────────────────────────────
function updateSubjectHeader(username, nodes, avatarUrl) {
  const seed   = nodes?.find(n => n.isSeed);
  const name   = seed?.displayName || username;
  const uname  = seed?.username    || username;
  const avatar = avatarUrl || seed?.avatarUrl || "";

  q("subject-name").textContent    = name;
  q("subject-username").textContent = `@${uname}`;

  const img = q("subject-avatar");
  const ph  = q("subject-avatar-placeholder");
  if (avatar) {
    img.src = avatar; img.style.display = "block"; ph.style.display = "none";
  } else {
    img.style.display = "none"; ph.style.display = "block";
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function q(id) { return document.getElementById(id); }
function enc(s) { return encodeURIComponent(s); }

async function apiFetch(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    throw new Error(j.detail || `Error ${res.status}`);
  }
  return res.json();
}

function setLoading(on, msg = "") {
  q("loading-overlay").style.display = on ? "flex" : "none";
  if (msg) q("loading-text").textContent = msg;
}

function toast(msg) {
  const el = q("toast");
  el.textContent = msg;
  el.style.display = "block";
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.display = "none"; }, 5000);
}
