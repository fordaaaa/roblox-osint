import {
  initGraph, renderGraph, mergeGraph,
  updateLegend, updateStats, onNodeClick,
  highlightNode, exportSVG,
} from "./graph.js";

import { openDossier, closeDossier, onDossierExpand } from "./profile.js";

// ── State ──
let _currentUsername = null;
let _compareMode = false;
let _selectedDepth = 2;

// ── Init ──
document.addEventListener("DOMContentLoaded", () => {
  initGraph(document.getElementById("graph-canvas"));

  // Home: single search
  document.getElementById("home-search-form").addEventListener("submit", async e => {
    e.preventDefault();
    const u = document.getElementById("home-username").value.trim();
    if (!u) return;
    _compareMode = false;
    await goToGraph(u);
  });

  // Home: compare search
  document.getElementById("home-compare-form").addEventListener("submit", async e => {
    e.preventDefault();
    const u1 = document.getElementById("compare-user1").value.trim();
    const u2 = document.getElementById("compare-user2").value.trim();
    if (!u1 || !u2) return;
    _compareMode = true;
    await goToCompare(u1, u2);
  });

  // Graph header: back
  document.getElementById("back-btn").addEventListener("click", () => showView("home"));

  // Graph header: reload
  document.getElementById("reload-btn").addEventListener("click", async () => {
    if (_currentUsername) await loadGraph(_currentUsername);
  });

  // Graph header: depth buttons
  document.querySelectorAll(".depth-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      _selectedDepth = parseInt(btn.dataset.depth);
      document.querySelectorAll(".depth-btn").forEach(b => b.classList.remove("selected"));
      btn.classList.add("selected");
    });
  });
  // Set default selected state
  document.querySelector(`.depth-btn[data-depth="2"]`).classList.add("selected");
  document.querySelectorAll(".depth-btn").forEach(b => b.classList.remove("active")); // remove leftover class from old code

  // Graph header: export
  document.getElementById("export-btn").addEventListener("click", exportSVG);

  // Dossier: close
  document.getElementById("dossier-close-btn").addEventListener("click", closeDossier);

  // Node click → open dossier
  onNodeClick(node => openDossier(node));

  // Dossier expand button → load that node's connections
  onDossierExpand(async profile => {
    await expandNode(profile.username);
  });

  // Sidebar: search within graph
  document.getElementById("node-search").addEventListener("input", e => {
    highlightNode(e.target.value.trim());
  });
});

// ── View switching ──
function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
}

// ── Graph loading ──
async function goToGraph(username) {
  showView("graph");
  _currentUsername = username;
  await loadGraph(username);
}

async function goToCompare(u1, u2) {
  showView("graph");
  _currentUsername = u1;
  await loadCompare(u1, u2);
}

async function loadGraph(username) {
  setLoading(true, `Mapping ${username}'s network…`);
  try {
    const params = new URLSearchParams({
      depth:     _selectedDepth,
      followers: document.getElementById("toggle-followers").checked,
      following: document.getElementById("toggle-following").checked,
    });

    const res = await fetch(`/api/graph/${enc(username)}?${params}`);
    if (!res.ok) throw new Error(await errText(res));
    const data = await res.json();

    renderGraph(data);
    updateLegend(data.communities, false);
    updateStats(data.stats);
    updateSubjectHeader(username, data.nodes);
  } catch (e) {
    toast(e.message);
  } finally {
    setLoading(false);
  }
}

async function loadCompare(u1, u2) {
  setLoading(true, `Comparing ${u1} vs ${u2}…`);
  try {
    const params = new URLSearchParams({ user1: u1, user2: u2, depth: _selectedDepth });
    const res = await fetch(`/api/compare?${params}`);
    if (!res.ok) throw new Error(await errText(res));
    const data = await res.json();

    renderGraph(data, { compareMode: true });
    updateLegend(data.communities, true);
    updateStats(data.stats);

    const n1 = data.nodes.find(n => n.isSeed && n.username.toLowerCase() === u1.toLowerCase());
    if (n1) updateSubjectHeader(`${u1} vs ${u2}`, data.nodes, n1.avatarUrl);
  } catch (e) {
    toast(e.message);
  } finally {
    setLoading(false);
  }
}

async function expandNode(username) {
  setLoading(true, `Expanding ${username}…`);
  try {
    const params = new URLSearchParams({
      depth: 1,
      followers: document.getElementById("toggle-followers").checked,
      following: document.getElementById("toggle-following").checked,
    });
    const res = await fetch(`/api/graph/${enc(username)}?${params}`);
    if (!res.ok) return;
    const data = await res.json();
    mergeGraph(data);
    updateLegend(data.communities, _compareMode);
    updateStats(data.stats);
  } catch (e) {
    console.error("Expand failed:", e);
  } finally {
    setLoading(false);
  }
}

// ── Subject header update ──
function updateSubjectHeader(username, nodes, avatarUrl) {
  const seed = nodes?.find(n => n.isSeed);
  const name = seed?.displayName || username;
  const uname = seed?.username || username;
  const avatar = avatarUrl || seed?.avatarUrl || "";

  document.getElementById("subject-name").textContent = name;
  document.getElementById("subject-username").textContent = `@${uname}`;

  const img = document.getElementById("subject-avatar");
  const ph  = document.getElementById("subject-avatar-placeholder");
  if (avatar) {
    img.src = avatar;
    img.style.display = "block";
    ph.style.display = "none";
  } else {
    img.style.display = "none";
    ph.style.display = "block";
  }
}

// ── Helpers ──
function enc(s) { return encodeURIComponent(s); }

async function errText(res) {
  try { const j = await res.json(); return j.detail ?? res.statusText; }
  catch { return res.statusText; }
}

function setLoading(on, msg = "") {
  const el = document.getElementById("loading-overlay");
  el.style.display = on ? "flex" : "none";
  if (msg) document.getElementById("loading-text").textContent = msg;
}

function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.style.display = "block";
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.display = "none"; }, 5000);
}
