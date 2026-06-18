// CIA-style dossier modal for a Roblox subject

let _expandCallback = null;
export function onDossierExpand(cb) { _expandCallback = cb; }

export function openDossier(nodeData) {
  const panel = document.getElementById("dossier-panel");
  const body  = document.getElementById("dossier-body");

  // Show immediately with basic data we already have
  body.innerHTML = _skeletonHTML(nodeData);
  panel.classList.add("open");

  // Then fetch the full profile
  fetch(`/api/profile/${encodeURIComponent(nodeData.username)}`)
    .then(r => { if (!r.ok) throw new Error("Profile unavailable"); return r.json(); })
    .then(data => { body.innerHTML = _dossierHTML(data); _bindButtons(data); })
    .catch(() => { body.innerHTML += `<div class="dossier-error">Could not load full profile.</div>`; });
}

export function closeDossier() {
  document.getElementById("dossier-panel").classList.remove("open");
}

function _bindButtons(data) {
  document.getElementById("dossier-expand-btn")?.addEventListener("click", () => {
    closeDossier();
    if (_expandCallback) _expandCallback(data);
  });
  document.getElementById("dossier-roblox-btn")?.addEventListener("click", () => {
    window.open(`https://www.roblox.com/users/${data.id}/profile`, "_blank");
  });
}

function _skeletonHTML(node) {
  return `
    <div class="dossier-stamp">CLASSIFIED</div>
    <div class="dossier-header">
      <div class="dossier-photo-wrap">
        ${node.avatarUrl ? `<img class="dossier-photo" src="${node.avatarUrl}" alt="">` : `<div class="dossier-photo-placeholder"></div>`}
      </div>
      <div class="dossier-id">
        <div class="dossier-field"><span class="dossier-label">DISPLAY NAME</span><span class="dossier-value">${node.displayName || node.username}</span></div>
        <div class="dossier-field"><span class="dossier-label">USERNAME</span><span class="dossier-value">@${node.username}</span></div>
        <div class="dossier-field"><span class="dossier-label">USER ID</span><span class="dossier-value">${node.id}</span></div>
        <div class="dossier-field"><span class="dossier-label">STATUS</span><span class="dossier-value dossier-loading">Loading…</span></div>
      </div>
    </div>
    <div class="dossier-loading-bar">Fetching intelligence data…</div>
  `;
}

function _dossierHTML(d) {
  const fileNum = String(d.id).padStart(8, "0");
  const createdStr = d.created ? new Date(d.created).toISOString().slice(0, 10) : "UNKNOWN";
  const firstBadgeStr = d.firstBadge
    ? `${new Date(d.firstBadge.awardedDate).toISOString().slice(0, 10)} — ${d.firstBadge.name}`
    : "NO BADGES ON RECORD";
  const presenceLabel = _presenceLabel(d.presence);
  const groupsHTML = d.groups.length
    ? d.groups.slice(0, 8).map(g => `
        <div class="dossier-group">
          <span class="dossier-group-name">${_esc(g.name)}</span>
          <span class="dossier-group-meta">Rank: ${_esc(g.rank)} &nbsp;·&nbsp; ${_fmt(g.memberCount)} members</span>
        </div>`).join("")
    : `<div class="dossier-none">NO KNOWN AFFILIATIONS</div>`;

  const threatDots = Array.from({length: 5}, (_, i) =>
    `<span class="threat-dot ${i < d.threatLevel.score ? 'filled' : ''}" style="${i < d.threatLevel.score ? `background:${d.threatLevel.color}` : ''}"></span>`
  ).join("");

  return `
    <div class="dossier-stamp">CLASSIFIED</div>
    <div class="dossier-file-num">FILE NO. ${fileNum}</div>

    <div class="dossier-header">
      <div class="dossier-photo-wrap">
        ${d.avatarFull ? `<img class="dossier-photo" src="${d.avatarFull}" alt="">` : `<div class="dossier-photo-placeholder"></div>`}
        <div class="dossier-photo-label">SUBJECT PHOTO</div>
      </div>
      <div class="dossier-id">
        <div class="dossier-section-title">SUBJECT IDENTIFICATION</div>
        <div class="dossier-field"><span class="dossier-label">DISPLAY NAME</span><span class="dossier-value">${_esc(d.displayName)}</span></div>
        <div class="dossier-field"><span class="dossier-label">USERNAME</span><span class="dossier-value">@${_esc(d.username)}</span></div>
        <div class="dossier-field"><span class="dossier-label">USER ID</span><span class="dossier-value">${d.id}</span></div>
        <div class="dossier-field"><span class="dossier-label">CURRENT STATUS</span><span class="dossier-value ${_presenceClass(d.presence)}">${presenceLabel}</span></div>
        ${d.presence?.location ? `<div class="dossier-field"><span class="dossier-label">LOCATION</span><span class="dossier-value">${_esc(d.presence.location)}</span></div>` : ""}
        ${d.presence?.lastOnline ? `<div class="dossier-field"><span class="dossier-label">LAST ONLINE</span><span class="dossier-value">${_reltime(d.presence.lastOnline)}</span></div>` : ""}
      </div>
    </div>

    <div class="dossier-divider"></div>

    <div class="dossier-section-title">ACCOUNT TIMELINE</div>
    <div class="dossier-grid">
      <div class="dossier-field"><span class="dossier-label">DATE CREATED</span><span class="dossier-value">${createdStr}</span></div>
      <div class="dossier-field"><span class="dossier-label">ACCOUNT AGE</span><span class="dossier-value">${d.accountAgeFormatted}</span></div>
      <div class="dossier-field"><span class="dossier-label">FIRST ACTIVITY</span><span class="dossier-value">${firstBadgeStr}</span></div>
      <div class="dossier-field"><span class="dossier-label">BADGES ON FILE</span><span class="dossier-value">${d.badgeCount}${d.badgesHaveMore ? "+" : ""}</span></div>
    </div>

    <div class="dossier-divider"></div>

    <div class="dossier-section-title">SOCIAL NETWORK ANALYSIS</div>
    <div class="dossier-social-row">
      <div class="dossier-social-stat">
        <span class="dossier-social-num">${_fmt(d.friendCount)}</span>
        <span class="dossier-social-lbl">FRIENDS</span>
      </div>
      <div class="dossier-social-stat">
        <span class="dossier-social-num">${_fmt(d.followerCount)}</span>
        <span class="dossier-social-lbl">FOLLOWERS</span>
      </div>
      <div class="dossier-social-stat">
        <span class="dossier-social-num">${_fmt(d.followingCount)}</span>
        <span class="dossier-social-lbl">FOLLOWING</span>
      </div>
    </div>

    <div class="dossier-divider"></div>

    <div class="dossier-section-title">KNOWN AFFILIATIONS</div>
    <div class="dossier-groups">${groupsHTML}</div>
    ${d.groups.length > 8 ? `<div class="dossier-none">…and ${d.groups.length - 8} more</div>` : ""}

    <div class="dossier-divider"></div>

    <div class="dossier-footer">
      <div class="dossier-threat">
        <div class="dossier-section-title">SUSPICION INDEX</div>
        <div class="dossier-threat-row">
          <div class="dossier-threat-dots">${threatDots}</div>
          <span class="dossier-threat-label" style="color:${d.threatLevel.color}">${d.threatLevel.label}</span>
        </div>
      </div>
      <div class="dossier-actions">
        <button id="dossier-expand-btn">Expand Connections</button>
        <button id="dossier-roblox-btn" class="secondary">View on Roblox ↗</button>
      </div>
    </div>
  `;
}

function _presenceLabel(p) {
  if (!p || !p.label) return "UNKNOWN";
  return p.label.toUpperCase();
}

function _presenceClass(p) {
  if (!p) return "";
  const t = p.type ?? 0;
  if (t === 2) return "status-ingame";
  if (t === 1) return "status-online";
  if (t === 3) return "status-studio";
  return "status-offline";
}

function _reltime(iso) {
  if (!iso) return "Unknown";
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins  = Math.floor(diff / 60000);
    const hours = Math.floor(mins / 60);
    const days  = Math.floor(hours / 24);
    if (days > 0)  return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
    if (mins > 0)  return `${mins}m ago`;
    return "Just now";
  } catch { return iso.slice(0, 10); }
}

function _fmt(n) {
  if (n == null) return "0";
  return Number(n).toLocaleString();
}

function _esc(s) {
  return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
