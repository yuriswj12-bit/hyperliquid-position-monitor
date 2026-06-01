const DEFAULT_ENDPOINT = "https://api.hyperliquid.xyz/info";

const state = {
  timer: null,
  running: false,
  lastPositions: [],
  watchlist: [],
};

const els = {
  wallet: document.querySelector("#walletInput"),
  endpoint: document.querySelector("#endpointInput"),
  refresh: document.querySelector("#refreshInput"),
  risk: document.querySelector("#riskInput"),
  start: document.querySelector("#startButton"),
  status: document.querySelector("#connectionStatus"),
  accountValue: document.querySelector("#accountValue"),
  positionValue: document.querySelector("#positionValue"),
  marginUsed: document.querySelector("#marginUsed"),
  unrealizedPnl: document.querySelector("#unrealizedPnl"),
  withdrawable: document.querySelector("#withdrawable"),
  positionCount: document.querySelector("#positionCount"),
  lastUpdated: document.querySelector("#lastUpdated"),
  positionsBody: document.querySelector("#positionsBody"),
  alertsList: document.querySelector("#alertsList"),
  changesList: document.querySelector("#changesList"),
  watchWallet: document.querySelector("#watchWalletInput"),
  watchName: document.querySelector("#watchNameInput"),
  watchTags: document.querySelector("#watchTagsInput"),
  addWallet: document.querySelector("#addWalletButton"),
  reloadWallets: document.querySelector("#reloadWalletsButton"),
  watchlist: document.querySelector("#watchlist"),
};

function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function money(value, maximumFractionDigits = 2) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits,
  }).format(toNumber(value));
}

function compact(value) {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 6,
  }).format(toNumber(value));
}

function percent(value) {
  return `${toNumber(value).toFixed(2)}%`;
}

function signedClass(value) {
  return toNumber(value) >= 0 ? "positive" : "negative";
}

function validateWallet(address) {
  return /^0x[a-fA-F0-9]{40}$/.test(address);
}

function setStatus(text, mode = "") {
  els.status.textContent = text;
  els.status.className = `status-pill ${mode}`.trim();
}

function shortWallet(wallet) {
  return wallet.length > 12 ? `${wallet.slice(0, 6)}...${wallet.slice(-4)}` : wallet;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizedEndpoint() {
  return els.endpoint.value.trim() || DEFAULT_ENDPOINT;
}

async function fetchPositionState() {
  const user = els.wallet.value.trim();
  if (!validateWallet(user)) {
    throw new Error("Enter a valid 0x wallet address");
  }

  const response = await fetch("/api/state", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      endpoint: normalizedEndpoint(),
      user,
    }),
  });

  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || payload.detail || `Request failed with ${response.status}`);
  }

  return payload;
}

async function loadWatchlist() {
  const response = await fetch("/api/watched-wallets");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with ${response.status}`);
  }
  state.watchlist = payload;
  renderWatchlist();
}

async function saveWatchWallet() {
  const user = els.watchWallet.value.trim();
  if (!validateWallet(user)) {
    setStatus("Error", "error");
    els.watchlist.innerHTML = '<div class="alert-item"><strong>Invalid wallet</strong><span>Enter a valid 0x wallet address.</span></div>';
    return;
  }

  const response = await fetch("/api/watched-wallets", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      user,
      name: els.watchName.value.trim() || null,
      tags: els.watchTags.value.trim() || null,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with ${response.status}`);
  }

  els.watchWallet.value = "";
  els.watchName.value = "";
  els.watchTags.value = "";
  await loadWatchlist();
}

async function deleteWatchWallet(user) {
  const response = await fetch(`/api/watched-wallets/${encodeURIComponent(user)}`, { method: "DELETE" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed with ${response.status}`);
  }
  await loadWatchlist();
}

function liquidationDistance(position) {
  const liq = toNumber(position.liquidationPx);
  const currentValue = toNumber(position.positionValue);
  const size = Math.abs(toNumber(position.szi));
  const mark = size > 0 ? currentValue / size : 0;

  if (!liq || !mark) {
    return null;
  }

  const isLong = toNumber(position.szi) > 0;
  const distance = isLong ? ((mark - liq) / mark) * 100 : ((liq - mark) / mark) * 100;
  return Number.isFinite(distance) ? distance : null;
}

function riskClass(distance, threshold) {
  if (distance === null) return "";
  if (distance <= threshold) return "risk-high";
  if (distance <= threshold * 2) return "risk-medium";
  return "risk-low";
}

function positionRows(assetPositions, threshold) {
  if (!assetPositions.length) {
    return '<tr><td colspan="9" class="empty-cell">No open positions.</td></tr>';
  }

  return assetPositions
    .map(({ position }) => {
      const size = toNumber(position.szi);
      const side = size >= 0 ? "Long" : "Short";
      const distance = liquidationDistance(position);
      const distanceText = distance === null ? "-" : percent(distance);
      const liqClass = riskClass(distance, threshold);
      const leverage = position.leverage?.value ? `${position.leverage.value}x` : "-";

      return `
        <tr>
          <td><strong>${position.coin || "-"}</strong></td>
          <td><span class="side ${side.toLowerCase()}">${side}</span></td>
          <td>${compact(Math.abs(size))}</td>
          <td>${money(position.entryPx, 6)}</td>
          <td>${money(position.positionValue)}</td>
          <td class="${signedClass(position.unrealizedPnl)}">${money(position.unrealizedPnl)}</td>
          <td class="${signedClass(position.returnOnEquity)}">${percent(position.returnOnEquity)}</td>
          <td>${position.liquidationPx ? money(position.liquidationPx, 6) : "-"}</td>
          <td class="${liqClass}"><strong>${distanceText}</strong> <span>${leverage}</span></td>
        </tr>
      `;
    })
    .join("");
}

function renderAlerts(assetPositions, threshold) {
  const alerts = assetPositions
    .map(({ position }) => ({ position, distance: liquidationDistance(position) }))
    .filter((item) => item.distance !== null && item.distance <= threshold)
    .sort((a, b) => a.distance - b.distance);

  if (!alerts.length) {
    els.alertsList.innerHTML = '<div class="quiet">No active alerts.</div>';
    return;
  }

  els.alertsList.innerHTML = alerts
    .map(({ position, distance }) => {
      const side = toNumber(position.szi) >= 0 ? "Long" : "Short";
      return `
        <div class="alert-item">
          <strong>${position.coin} ${side}</strong>
          <span>${percent(distance)} from liquidation at ${money(position.liquidationPx, 6)}</span>
        </div>
      `;
    })
    .join("");
}

function renderChanges(changes) {
  if (!Array.isArray(changes) || !changes.length) {
    els.changesList.innerHTML = '<div class="quiet">No position changes yet.</div>';
    return;
  }

  els.changesList.innerHTML = changes
    .map((change) => {
      const changePercent = change.change_percent === null || change.change_percent === undefined ? "" : ` (${percent(change.change_percent)})`;
      return `
        <div class="change-item">
          <strong>${change.coin} ${change.change_type}${changePercent}</strong>
          <span>${compact(change.previous_size)} -> ${compact(change.current_size)}</span>
        </div>
      `;
    })
    .join("");
}

function renderWatchlist() {
  if (!state.watchlist.length) {
    els.watchlist.innerHTML = '<div class="quiet">No database watchlist wallets yet.</div>';
    return;
  }

  els.watchlist.innerHTML = state.watchlist
    .map((wallet) => {
      const label = escapeHtml(wallet.name || shortWallet(wallet.user));
      const tags = wallet.tags ? `<span class="tag">${escapeHtml(wallet.tags)}</span>` : "";
      const user = escapeHtml(wallet.user);
      return `
        <div class="watch-item">
          <div>
            <strong>${label}</strong>
            <span>${escapeHtml(shortWallet(wallet.user))} ${tags}</span>
          </div>
          <div class="watch-actions">
            <button type="button" data-use-wallet="${user}">Use</button>
            <button type="button" data-delete-wallet="${user}">Delete</button>
          </div>
        </div>
      `;
    })
    .join("");
}

function render(payload) {
  const raw = payload.snapshot?.raw || payload;
  const positions = Array.isArray(raw.assetPositions) ? raw.assetPositions : [];
  const marginSummary = raw.marginSummary || {};
  const threshold = Math.max(1, Number(els.risk.value) || 12);
  const totalPnl = positions.reduce((sum, item) => sum + toNumber(item.position?.unrealizedPnl), 0);
  state.lastPositions = positions;

  els.accountValue.textContent = money(marginSummary.accountValue);
  els.positionValue.textContent = money(marginSummary.totalNtlPos);
  els.marginUsed.textContent = money(marginSummary.totalMarginUsed);
  els.unrealizedPnl.textContent = money(totalPnl);
  els.unrealizedPnl.className = signedClass(totalPnl);
  els.withdrawable.textContent = money(raw.withdrawable);
  els.positionCount.textContent = String(positions.length);
  els.positionsBody.innerHTML = positionRows(positions, threshold);
  els.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  renderAlerts(positions, threshold);
  renderChanges(payload.changes);
}

async function refreshNow() {
  setStatus("Syncing");
  try {
    const payload = await fetchPositionState();
    render(payload);
    setStatus("Live", "live");
  } catch (error) {
    setStatus("Error", "error");
    els.alertsList.innerHTML = `<div class="alert-item"><strong>Request failed</strong><span>${error.message}</span></div>`;
  }
}

function stopMonitor() {
  window.clearInterval(state.timer);
  state.timer = null;
  state.running = false;
  els.start.textContent = "Start";
  els.start.classList.remove("stop");
  setStatus("Idle");
}

function startMonitor() {
  if (state.running) {
    stopMonitor();
    return;
  }

  if (!validateWallet(els.wallet.value.trim())) {
    setStatus("Error", "error");
    els.alertsList.innerHTML = '<div class="alert-item"><strong>Request failed</strong><span>Enter a valid 0x wallet address</span></div>';
    return;
  }

  state.running = true;
  els.start.textContent = "Stop";
  els.start.classList.add("stop");
  refreshNow();
  state.timer = window.setInterval(refreshNow, Number(els.refresh.value));
}

els.start.addEventListener("click", startMonitor);
els.addWallet.addEventListener("click", () => {
  saveWatchWallet().catch((error) => {
    setStatus("Error", "error");
    els.watchlist.innerHTML = `<div class="alert-item"><strong>Save failed</strong><span>${error.message}</span></div>`;
  });
});
els.reloadWallets.addEventListener("click", () => {
  loadWatchlist().catch((error) => {
    setStatus("Error", "error");
    els.watchlist.innerHTML = `<div class="alert-item"><strong>Load failed</strong><span>${error.message}</span></div>`;
  });
});
els.watchlist.addEventListener("click", (event) => {
  const useButton = event.target.closest("[data-use-wallet]");
  const deleteButton = event.target.closest("[data-delete-wallet]");
  if (useButton) {
    els.wallet.value = useButton.dataset.useWallet;
  }
  if (deleteButton) {
    deleteWatchWallet(deleteButton.dataset.deleteWallet).catch((error) => {
      setStatus("Error", "error");
      els.watchlist.innerHTML = `<div class="alert-item"><strong>Delete failed</strong><span>${error.message}</span></div>`;
    });
  }
});
els.refresh.addEventListener("change", () => {
  if (!state.running) return;
  window.clearInterval(state.timer);
  state.timer = window.setInterval(refreshNow, Number(els.refresh.value));
});
els.risk.addEventListener("change", () => {
  if (state.lastPositions.length) {
    const threshold = Math.max(1, Number(els.risk.value) || 12);
    els.positionsBody.innerHTML = positionRows(state.lastPositions, threshold);
    renderAlerts(state.lastPositions, threshold);
  }
});

loadWatchlist().catch((error) => {
  els.watchlist.innerHTML = `<div class="alert-item"><strong>Load failed</strong><span>${error.message}</span></div>`;
});
