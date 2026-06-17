import {
  initGraph,
  renderGraph,
  mergeGraph,
  updateLegend,
  updateStats,
  onNodeExpand,
  exportSVG,
} from "./graph.js";

let _compareMode = false;

document.addEventListener("DOMContentLoaded", () => {
  initGraph(document.getElementById("graph-container"));

  document.getElementById("search-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    await loadGraph();
  });

  document.getElementById("compare-toggle").addEventListener("change", (e) => {
    _compareMode = e.target.checked;
    document.getElementById("compare-input-wrap").style.display = _compareMode ? "flex" : "none";
  });

  document.getElementById("export-btn").addEventListener("click", exportSVG);

  onNodeExpand(async (nodeData) => {
    await expandNode(nodeData);
  });
});

async function loadGraph() {
  const username = document.getElementById("username-input").value.trim();
  if (!username) return;

  setLoading(true);
  hideEmpty();

  try {
    if (_compareMode) {
      const username2 = document.getElementById("username2-input").value.trim();
      if (!username2) { showError("Enter a second username for compare mode"); return; }
      const depth = document.getElementById("depth-select").value;

      const res = await fetch(
        `/api/compare?user1=${enc(username)}&user2=${enc(username2)}&depth=${depth}`
      );
      if (!res.ok) throw new Error(await errorText(res));
      const data = await res.json();

      renderGraph(data, { compareMode: true });
      updateLegend(data.communities, true);
      updateStats(data.stats);
    } else {
      const params = buildParams();
      const res = await fetch(`/api/graph/${enc(username)}?${params}`);
      if (!res.ok) throw new Error(await errorText(res));
      const data = await res.json();

      renderGraph(data);
      updateLegend(data.communities);
      updateStats(data.stats);
    }
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
}

async function expandNode(nodeData) {
  setLoading(true);
  try {
    const params = new URLSearchParams({
      depth: 1,
      followers: document.getElementById("toggle-followers").checked,
      following: document.getElementById("toggle-following").checked,
    });
    const res = await fetch(`/api/graph/${enc(nodeData.username)}?${params}`);
    if (!res.ok) return;
    const data = await res.json();
    mergeGraph(data);
    updateLegend(data.communities, _compareMode);
    updateStats(data.stats);
  } catch (err) {
    console.error("Expand failed:", err);
  } finally {
    setLoading(false);
  }
}

function buildParams() {
  return new URLSearchParams({
    depth:     document.getElementById("depth-select").value,
    followers: document.getElementById("toggle-followers").checked,
    following: document.getElementById("toggle-following").checked,
  });
}

function enc(s) { return encodeURIComponent(s); }

async function errorText(res) {
  try {
    const j = await res.json();
    return j.detail ?? res.statusText;
  } catch {
    return res.statusText;
  }
}

function setLoading(on) {
  document.getElementById("loading").style.display = on ? "flex" : "none";
}

function hideEmpty() {
  const el = document.getElementById("empty-state");
  if (el) el.style.display = "none";
}

function showError(msg) {
  const el = document.getElementById("error-msg");
  el.textContent = msg;
  el.style.display = "block";
  setTimeout(() => { el.style.display = "none"; }, 5000);
}
