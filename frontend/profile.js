let _expandCb = null;
export function onDossierExpand(cb) { _expandCb = cb; }

export function openDossier(nodeData) {
  const panel = document.getElementById("dossier-panel");
  const body  = document.getElementById("dossier-body");

  body.innerHTML = _skeleton(nodeData);
  panel.classList.add("open");

  // Use ID-based endpoint — username lookup can 404 for renamed/privacy accounts
  fetch(`/api/profile-by-id/${nodeData.id}`)
    .then(r => {
      if (!r.ok) throw new Error(`${r.status} — profile unavailable`);
      return r.json();
    })
    .then(data => {
      body.innerHTML = _render(data);
      document.getElementById("p-expand-btn")?.addEventListener("click", () => {
        closeDossier();
        if (_expandCb) _expandCb(data);
      });
      document.getElementById("p-roblox-btn")?.addEventListener("click", () => {
        window.open(`https://www.roblox.com/users/${data.id}/profile`, "_blank");
      });
    })
    .catch(err => {
      console.error("Profile fetch failed:", err);
      body.innerHTML = _skeleton(nodeData, `Could not load profile: ${err.message}`);
    });
}

export function closeDossier() {
  document.getElementById("dossier-panel").classList.remove("open");
}

// ── Skeleton shown immediately while fetching ──────────────────────────────
function _skeleton(node, errorMsg) {
  return `
    <div class="p-hero">
      ${node.avatarUrl
        ? `<img class="p-avatar" src="${node.avatarUrl}" alt="">`
        : `<div class="p-avatar p-avatar-ph"></div>`}
      <div class="p-hero-info">
        <div class="p-display">${_esc(node.displayName || node.username)}</div>
        <div class="p-username">@${_esc(node.username)}</div>
      </div>
    </div>
    ${errorMsg
      ? `<div class="p-error">${_esc(errorMsg)}</div>`
      : `<div class="p-loading-msg">Loading profile…</div>`}
  `;
}

// ── Full profile card ───────────────────────────────────────────────────────
function _render(d) {
  const status  = _statusInfo(d.presence);
  const ageBar  = _ageBar(d.accountAgeDays);
  const groups  = d.groups?.slice(0, 6) ?? [];
  const threat  = d.threatLevel ?? { score: 0, label: "Unknown", color: "#6b6b8a" };

  return `
    <!-- Hero -->
    <div class="p-hero">
      ${d.avatarFull
        ? `<img class="p-avatar p-avatar-lg" src="${d.avatarFull}" alt="">`
        : `<div class="p-avatar p-avatar-lg p-avatar-ph"></div>`}
      <div class="p-hero-info">
        <div class="p-display">${_esc(d.displayName)}</div>
        <div class="p-username">@${_esc(d.username)}</div>
        <div class="p-status ${status.cls}">
          <span class="p-status-dot"></span>${status.label}
          ${d.presence?.location && d.presence.location !== "Website"
            ? `<span class="p-status-loc">· ${_esc(d.presence.location)}</span>` : ""}
        </div>
      </div>
    </div>

    <!-- Account age -->
    <div class="p-section">
      <div class="p-section-label">Account age</div>
      <div class="p-age-row">
        <span class="p-age-value">${_esc(d.accountAgeFormatted)}</span>
        ${d.created ? `<span class="p-age-since">since ${new Date(d.created).getFullYear()}</span>` : ""}
      </div>
      <div class="p-age-bar-track">
        <div class="p-age-bar-fill" style="width:${ageBar}%; background: ${threat.color}"></div>
      </div>
    </div>

    <!-- Stats grid -->
    <div class="p-stats">
      ${_stat(d.friendCount,   "Friends")}
      ${_stat(d.followerCount, "Followers")}
      ${_stat(d.followingCount,"Following")}
      ${_stat(d.badgeCount + (d.badgesHaveMore ? "+" : ""), "Badges")}
    </div>

    <!-- First activity -->
    ${d.firstBadge ? `
    <div class="p-section">
      <div class="p-section-label">First badge</div>
      <div class="p-first-badge">
        <span class="p-badge-name">${_esc(d.firstBadge.name)}</span>
        <span class="p-badge-date">${_reltime(d.firstBadge.awardedDate)}</span>
      </div>
    </div>` : ""}

    <!-- Last seen -->
    ${d.presence?.lastOnline ? `
    <div class="p-section">
      <div class="p-section-label">Last seen</div>
      <div class="p-last-seen">${_reltime(d.presence.lastOnline)}</div>
    </div>` : ""}

    <!-- Groups -->
    ${groups.length ? `
    <div class="p-section">
      <div class="p-section-label">Groups <span class="p-section-count">${d.groups.length}</span></div>
      <div class="p-groups">
        ${groups.map(g => `
          <div class="p-group">
            <div class="p-group-name">${_esc(g.name)}</div>
            <div class="p-group-meta">${_esc(g.rank)} · ${_fmt(g.memberCount)} members</div>
          </div>`).join("")}
        ${d.groups.length > 6 ? `<div class="p-group-more">+${d.groups.length - 6} more</div>` : ""}
      </div>
    </div>` : ""}

    <!-- Risk score -->
    <div class="p-section">
      <div class="p-section-label">Account risk score</div>
      <div class="p-risk-row">
        <div class="p-risk-dots">
          ${Array.from({length: 5}, (_, i) =>
            `<div class="p-risk-dot ${i < threat.score ? "on" : ""}" style="${i < threat.score ? `background:${threat.color}` : ""}"></div>`
          ).join("")}
        </div>
        <span class="p-risk-label" style="color:${threat.color}">${threat.label}</span>
      </div>
      <div class="p-risk-hint">Based on account age, badges, friends and group activity</div>
    </div>

    <!-- Actions -->
    <div class="p-actions">
      <button id="p-expand-btn" class="btn-primary" style="flex:1">Expand connections</button>
      <button id="p-roblox-btn" class="btn-secondary">Roblox ↗</button>
    </div>
  `;
}

// ── Helpers ────────────────────────────────────────────────────────────────
function _stat(value, label) {
  return `
    <div class="p-stat">
      <div class="p-stat-num">${_fmt(value)}</div>
      <div class="p-stat-lbl">${label}</div>
    </div>`;
}

function _statusInfo(presence) {
  if (!presence) return { cls: "status-offline", label: "Offline" };
  const t = presence.type ?? 0;
  if (t === 2) return { cls: "status-ingame",  label: "In Game" };
  if (t === 3) return { cls: "status-studio",  label: "In Studio" };
  if (t === 1) return { cls: "status-online",  label: "Online" };
  return { cls: "status-offline", label: "Offline" };
}

function _ageBar(days) {
  // Map 0–10 years to 0–100%
  return Math.min(100, Math.round((days / 3650) * 100));
}

function _reltime(iso) {
  if (!iso) return "Unknown";
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    const h = Math.floor(m / 60);
    const d = Math.floor(h / 24);
    const y = Math.floor(d / 365);
    if (y > 0)  return `${y}y ago`;
    if (d > 0)  return `${d}d ago`;
    if (h > 0)  return `${h}h ago`;
    if (m > 0)  return `${m}m ago`;
    return "just now";
  } catch { return iso.slice(0, 10); }
}

function _fmt(n) {
  if (n == null) return "0";
  const num = parseInt(n);
  if (isNaN(num)) return String(n);
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + "M";
  if (num >= 1_000)     return (num / 1_000).toFixed(1) + "K";
  return num.toLocaleString();
}

function _esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
