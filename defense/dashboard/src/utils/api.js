const DEFAULT_ORCHESTRATOR_PORT = import.meta.env.VITE_DEFENSE_PORT || "7700";

const API_BASE_CANDIDATES = (() => {
  const bases = [import.meta.env.VITE_DEFENSE_API, "/api"];
  if (typeof window !== "undefined") {
    const hostWithPort = window.location.origin.replace(/:\\d+$/, `:${DEFAULT_ORCHESTRATOR_PORT}`);
    bases.push(hostWithPort);
    bases.push(`http://localhost:${DEFAULT_ORCHESTRATOR_PORT}`);
  }
  return bases.filter(Boolean);
})();

async function doFetch(path, signal, init = {}) {
  let lastError;
  for (const base of API_BASE_CANDIDATES) {
    const normalizedBase = base.endsWith("/") ? base.slice(0, -1) : base;
    const url = `${normalizedBase}${path.startsWith("/") ? path : `/${path}`}`;
    try {
      const response = await fetch(url, { signal, ...init });
      if (!response.ok) {
        const text = await response.text();
        const error = new Error(text || `Request failed with status ${response.status}`);
        error.status = response.status;
        throw error;
      }
      return response.json();
    } catch (err) {
      lastError = err;
      console.warn(`API request to ${url} failed (${err.message}). Trying next fallback...`);
    }
  }
  throw lastError ?? new Error("All API base candidates failed");
}

export function fetchDefenseScan(signal) {
  return doFetch("/defense-scan", signal);
}

export function fetchAttackLog(limit = 60, signal) {
  const params = new URLSearchParams({ limit: String(limit) });
  return doFetch(`/attack-log?${params.toString()}`, signal);
}

export function armHoneypots(payload = {}, signal) {
  return doFetch("/honeypots/arm", signal, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchHoneypots(signal) {
  return doFetch("/honeypots", signal);
}

export function fetchReconReport(signal) {
  return doFetch("/reports/latest?fmt=json", signal);
}

export function runRecon(context = {}, signal) {
  return doFetch("/recon/run", signal, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ context }),
  });
}

