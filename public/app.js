const DEFAULT_ENDPOINT = "https://api.hyperliquid.xyz/info";

const state = {
  timer: null,
  running: false,
  lastPositions: [],
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

function normalizedEndpoint() {
  return els.endpoint.value.trim() || DEFAULT_ENDPOINT;
}

async function fetchPositionState() {
  const user = els.wallet.value.trim();
  if (!validateWallet(user)) {
    throw new Error("请输入有效的 0x 钱包地址");
  }

  const response = await fetch("/api/info", {
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

function render(payload) {
  const positions = Array.isArray(payload.assetPositions) ? payload.assetPositions : [];
  const marginSummary = payload.marginSummary || {};
  const threshold = Math.max(1, Number(els.risk.value) || 12);
  const totalPnl = positions.reduce((sum, item) => sum + toNumber(item.position?.unrealizedPnl), 0);
  state.lastPositions = positions;

  els.accountValue.textContent = money(marginSummary.accountValue);
  els.positionValue.textContent = money(marginSummary.totalNtlPos);
  els.marginUsed.textContent = money(marginSummary.totalMarginUsed);
  els.unrealizedPnl.textContent = money(totalPnl);
  els.unrealizedPnl.className = signedClass(totalPnl);
  els.withdrawable.textContent = money(payload.withdrawable);
  els.positionCount.textContent = String(positions.length);
  els.positionsBody.innerHTML = positionRows(positions, threshold);
  els.lastUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  renderAlerts(positions, threshold);
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
    els.alertsList.innerHTML = '<div class="alert-item"><strong>Request failed</strong><span>请输入有效的 0x 钱包地址</span></div>';
    return;
  }

  state.running = true;
  els.start.textContent = "Stop";
  els.start.classList.add("stop");
  refreshNow();
  state.timer = window.setInterval(refreshNow, Number(els.refresh.value));
}

els.start.addEventListener("click", startMonitor);
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
