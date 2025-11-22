const DEFAULT_ORCHESTRATOR_PORT = import.meta.env.VITE_DEFENSE_PORT || "7000";

const API_BASE_CANDIDATES = (() => {
  const bases = [];
  // Try direct connection first (port 7000)
  if (typeof window !== "undefined") {
    bases.push(`http://localhost:${DEFAULT_ORCHESTRATOR_PORT}`);
    const hostWithPort = window.location.origin.replace(
      /:\\d+$/,
      `:${DEFAULT_ORCHESTRATOR_PORT}`
    );
    bases.push(hostWithPort);
  }
  // Then try Vite proxy
  bases.push("/api");
  // Then try environment variable
  if (import.meta.env.VITE_DEFENSE_API) {
    bases.push(import.meta.env.VITE_DEFENSE_API);
  }
  // Finally try port 7700 for backwards compatibility
  if (typeof window !== "undefined") {
    bases.push(`http://localhost:7700`);
  }
  return bases.filter(Boolean);
})();

async function doFetch(path, signal) {
  let lastError;
  const errors = [];
  for (const base of API_BASE_CANDIDATES) {
    const normalizedBase = base.endsWith("/") ? base.slice(0, -1) : base;
    const url = `${normalizedBase}${path.startsWith("/") ? path : `/${path}`}`;
    try {
      console.log(`[API] Trying: ${url}`);
      const response = await fetch(url, { signal });
      if (!response.ok) {
        const text = await response.text();
        const error = new Error(
          text || `Request failed with status ${response.status}`
        );
        error.status = response.status;
        errors.push(`${url}: ${response.status} ${text}`);
        throw error;
      }
      const data = await response.json();
      console.log(`[API] Success from ${url}`);
      return data;
    } catch (err) {
      lastError = err;
      if (err.name !== "AbortError") {
        errors.push(`${url}: ${err.message}`);
        console.warn(`[API] Request to ${url} failed:`, err.message);
      }
    }
  }
  const errorMsg = `All API base candidates failed:\n${errors.join("\n")}`;
  console.error(`[API] ${errorMsg}`);
  throw lastError ?? new Error(errorMsg);
}

export function fetchDefenseScan(signal) {
  return doFetch("/defense-scan", signal);
}

export function fetchAttackLog(limit = 60, signal) {
  const params = new URLSearchParams({ limit: String(limit) });
  return doFetch(`/attack-log?${params.toString()}`, signal);
}

export function fetchReconReport(signal) {
  return doFetch("/recon-report", signal);
}

export function triggerReconInvestigation(signal) {
  return doFetch("/recon-investigate", { method: "POST", signal });
}
