const AUTH_TOKEN_STORAGE_KEY = "ragApiBearerToken";

function getAuthToken() {
  const input = document.getElementById("apiBearerToken");
  if (input && typeof input.value === "string") {
    return input.value.trim();
  }
  return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || "";
}

function buildHeaders() {
  const headers = { "Content-Type": "application/json" };
  const token = getAuthToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: buildHeaders(),
    body: JSON.stringify(body),
  });
  const payload = await res.json();
  if (!res.ok) {
    throw new Error(payload.detail || "Request failed");
  }
  return payload;
}

async function apiGet(path) {
  const res = await fetch(path, {
    method: "GET",
    headers: buildHeaders(),
  });
  const payload = await res.json();
  if (!res.ok) {
    throw new Error(payload.detail || "Request failed");
  }
  return payload;
}

const pollers = {};

function escapeHtml(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}


function statusClass(status) {
  return `status-${status || "idle"}`;
}

function jobState(job) {
  return job?.lifecycle_state || job?.status || "idle";
}

function statusHeader(job, label) {
  const status = jobState(job);
  const running = status === "running" || status === "cancelling";
  return `
    <div class="status-line">
      ${running ? '<span class="spinner" aria-hidden="true"></span>' : ""}
      <strong>${label}</strong>
      <span class="status-pill ${statusClass(status)}">${escapeHtml(status)}</span>
    </div>
  `;
}

function progressBlock(job) {
  const pct = Number(job?.progress_percent || 0);
  const message = job?.progress_message || "";
  return `
    <div class="progress">
      <div class="progress-track">
        <div class="progress-fill" style="width:${Math.max(0, Math.min(100, pct))}%"></div>
      </div>
      <div class="progress-label">${escapeHtml(pct.toFixed(1))}% ${message ? `- ${escapeHtml(message)}` : ""}</div>
    </div>
  `;
}

function renderSimpleMessage(el, title, status, message) {
  el.innerHTML = `
    <div class="status-line">
      ${status === "running" || status === "cancelling" ? '<span class="spinner"></span>' : ""}
      <strong>${escapeHtml(title)}</strong>
      <span class="status-pill ${statusClass(status)}">${escapeHtml(status)}</span>
    </div>
    <div class="empty">${escapeHtml(message)}</div>
  `;
}

function startPolling(name, onUpdate) {
  stopPolling(name);
  pollers[name] = setInterval(async () => {
    try {
      const payload = await apiGet(`/api/${name}/status`);
      onUpdate(payload);
      const state = payload.lifecycle_state || payload.status;
      if (state !== "running" && state !== "cancelling") {
        stopPolling(name);
      }
    } catch (err) {
      stopPolling(name);
    }
  }, 1000);
}

function stopPolling(name) {
  if (pollers[name]) {
    clearInterval(pollers[name]);
    delete pollers[name];
  }
}

function initDocumentationTabs() {
  const tabButtons = Array.from(document.querySelectorAll(".tab-btn[data-tab-target]"));
  if (!tabButtons.length) return;
  const panes = Array.from(document.querySelectorAll(".tab-content"));
  for (const btn of tabButtons) {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab-target");
      for (const b of tabButtons) b.classList.remove("active");
      btn.classList.add("active");
      for (const p of panes) {
        p.classList.toggle("active", p.id === targetId);
      }
    });
  }
}

function renderHealth(payload) {
  const out = document.getElementById("healthOut");
  const stats = payload?.stats || {};
  const appVersion = String(payload?.version || "").trim();
  const badge = document.getElementById("appVersionBadge");
  if (badge) {
    badge.textContent = appVersion ? `v${appVersion}` : "v-";
  }
  out.innerHTML = `
    ${statusHeader({ status: "completed" }, "System Health")}
    <div class="kv">
      <strong>Status</strong><span>${escapeHtml(payload?.status || "unknown")}</span>
      <strong>Version</strong><span>${escapeHtml(appVersion || "-")}</span>
      <strong>Neo4j URI</strong><span>${escapeHtml(payload?.neo4j_uri || "")}</span>
      <strong>Articles</strong><span>${escapeHtml(stats.articles ?? 0)}</span>
      <strong>Chunks</strong><span>${escapeHtml(stats.chunks ?? 0)}</span>
      <strong>Tokens</strong><span>${escapeHtml(stats.tokens ?? 0)}</span>
      <strong>References</strong><span>${escapeHtml(stats.references ?? 0)}</span>
      <strong>Citations</strong><span>${escapeHtml(stats.cites ?? 0)}</span>
    </div>
  `;
}

async function refreshHealth() {
  renderSimpleMessage(document.getElementById("healthOut"), "System Health", "running", "Loading health data...");
  const res = await fetch("/api/health");
  const payload = await res.json();
  renderHealth(payload);
}

function renderSyncJob(job) {
  const out = document.getElementById("syncOut");
  if (!job) {
    renderSimpleMessage(out, "Sync", "idle", "Not started.");
    return;
  }
  const state = jobState(job);
  const result = job.result || {};
  const sourceStats = result.source_stats || {};
  const ingest = result.ingest_summary || {};
  const reconcile = result.reconcile_summary || {};
  const unmatched = result.unmatched_sample || [];
  const detectedInitial = sourceStats.zotero_missing_detected_initial ?? sourceStats.zotero_missing_in_neo4j ?? "-";
  const reconciledExisting = sourceStats.zotero_reconciled_existing ?? reconcile.matched ?? "-";
  const unresolvedAfterReconcile = sourceStats.zotero_missing_in_neo4j_after_reconcile ?? sourceStats.zotero_missing_in_neo4j ?? "-";
  const remainingAfterIngest = sourceStats.zotero_missing_in_neo4j_after_ingest ?? unresolvedAfterReconcile;
  const ingestCandidates = result.ingest_candidate_count ?? sourceStats.zotero_paths_found ?? "-";
  const failedPdfs = Array.isArray(ingest.failed_pdfs) ? ingest.failed_pdfs.length : 0;
  out.innerHTML = `
    ${statusHeader(job, "PDF Sync")}
    ${progressBlock(job)}
    <div class="kv">
      <strong>Lifecycle</strong><span>${escapeHtml(state)}</span>
      <strong>Success</strong><span>${escapeHtml(result.ok ?? job.status === "completed")}</span>
      <strong>Source Mode</strong><span>${escapeHtml(result.source_mode ?? "-")}</span>
      <strong>Zotero PDFs</strong><span>${escapeHtml(result.pdfs_total ?? "-")}</span>
      <strong>Missing Detected</strong><span>${escapeHtml(detectedInitial)}</span>
      <strong>Reconciled Existing</strong><span>${escapeHtml(reconciledExisting)}</span>
      <strong>Need Ingest</strong><span>${escapeHtml(ingestCandidates)}</span>
      <strong>Ingest Ran</strong><span>${escapeHtml(result.ingest_ran ?? false)}</span>
      <strong>Ingested Articles</strong><span>${escapeHtml(ingest.ingested_articles ?? "-")}</span>
      <strong>Ingest Failed PDFs</strong><span>${escapeHtml(failedPdfs)}</span>
      <strong>Remaining Missing</strong><span>${escapeHtml(remainingAfterIngest)}</span>
      <strong>Terminal Reason</strong><span>${escapeHtml(job.terminal_reason ?? "-")}</span>
      <strong>Stop State</strong><span>${escapeHtml(job.stop_state ?? "-")}</span>
    </div>
    ${job.error ? `<div class="empty">Error: ${escapeHtml(job.error)}</div>` : ""}
    ${Object.keys(reconcile).length ? `<details><summary>Reconcile Summary</summary><pre>${escapeHtml(JSON.stringify(reconcile, null, 2))}</pre></details>` : ""}
    ${Object.keys(sourceStats).length ? `<details><summary>Source Stats</summary><pre>${escapeHtml(JSON.stringify(sourceStats, null, 2))}</pre></details>` : ""}
    ${unmatched.length ? `<details><summary>Unmatched Sample (${unmatched.length})</summary><ul class="list-box">${unmatched.slice(0, 30).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
  `;
}

function renderQueryJob(job) {
  const results = document.getElementById("queryResults");
  if (!job) {
    renderSimpleMessage(results, "Query", "idle", "No query executed yet.");
    return;
  }
  const state = jobState(job);
  if (state === "running" || state === "cancelling") {
    renderSimpleMessage(results, "Query", state, state === "cancelling" ? "Cancelling..." : "Searching...");
    return;
  }
  if (state === "cancelled") {
    renderSimpleMessage(results, "Query", "cancelled", "Query cancelled.");
    return;
  }
  if (state === "failed") {
    renderSimpleMessage(results, "Query", "failed", job.error || "Query failed.");
    return;
  }

  const payload = job.result || {};
  const rows = payload.results || [];
  const limitScope = payload.limit_scope || "chunks";
  if (!rows.length) {
    renderSimpleMessage(results, "Query", "completed", "No results.");
    return;
  }

  results.innerHTML = `
    ${statusHeader(job, "Query Results")}
    ${progressBlock(job)}
    <div class="meta">Scope: ${escapeHtml(limitScope)} | Requested limit: ${escapeHtml(payload.limit ?? rows.length)}</div>
    ${rows
      .map((r, i) => {
        const scope = r.result_scope || limitScope;
        const score = Number(r.paper_score ?? r.rerank_score ?? r.combined_score ?? 0);
        const highlights = Array.isArray(r.highlight_chunks) ? r.highlight_chunks : [];
        const topChunk = highlights[0] || r;
        const chunkId = topChunk.chunk_id || r.chunk_id || "";
        const pageStart = topChunk.page_start || r.page_start || "";
        const pageEnd = topChunk.page_end || r.page_end || "";
        const chunkText = topChunk.chunk_text || r.chunk_text || "";
        const cites = (r.cites_out || []).join(", ");
        const citedBy = (r.cited_by || []).join(", ");
        const matchedChunks = r.paper_chunk_count ?? highlights.length ?? 1;
        const extraHighlights = highlights
          .slice(1)
          .map((h) => `#${h.chunk_index ?? "?"} p.${h.page_start ?? "?"}-${h.page_end ?? "?"}`)
          .join("; ");
        return `
          <article class="result">
            <strong>[${i + 1}] ${escapeHtml(r.article_title || "Untitled")} (${escapeHtml(r.article_year || "")})</strong>
            <div class="meta">Author: ${escapeHtml(r.author || "")} | ${escapeHtml(scope === "paper" ? "Paper Score" : "Score")}: ${escapeHtml(score.toFixed(4))}</div>
            <div class="meta">Chunk: ${escapeHtml(chunkId)} | Pages: ${escapeHtml(pageStart)}-${escapeHtml(pageEnd)}</div>
            ${scope === "paper" ? `<div class="meta">Matched chunks in paper: ${escapeHtml(matchedChunks)}</div>` : ""}
            ${extraHighlights ? `<div class="meta"><strong>Extra highlights:</strong> ${escapeHtml(extraHighlights)}</div>` : ""}
            <p>${escapeHtml(chunkText.slice(0, 650))}...</p>
            ${cites ? `<div class="meta"><strong>Cites:</strong> ${escapeHtml(cites)}</div>` : ""}
            ${citedBy ? `<div class="meta"><strong>Cited by:</strong> ${escapeHtml(citedBy)}</div>` : ""}
          </article>
        `;
      })
      .join("")}
  `;
}

function renderDiagnostics(payload) {
  const out = document.getElementById("diagOut");
  const checks = payload?.checks || [];
  const details = payload?.details || {};
  out.innerHTML = `
    ${statusHeader({ status: payload?.ok ? "completed" : "failed" }, "Diagnostics")}
    <div class="kv">
      <strong>Overall</strong><span class="${payload?.ok ? "ok" : "bad"}">${escapeHtml(payload?.ok ? "PASS" : "FAIL")}</span>
      <strong>Local PDFs</strong><span>${escapeHtml(details.pdfs_total ?? 0)}</span>
      <strong>With Metadata</strong><span>${escapeHtml(details.pdfs_with_metadata ?? 0)}</span>
      <strong>Neo4j Articles</strong><span>${escapeHtml(details?.neo4j_stats?.articles ?? "n/a")}</span>
    </div>
    <table class="preview-table">
      <thead><tr><th>Check</th><th>Status</th><th>Details</th></tr></thead>
      <tbody>
        ${checks.map((c) => `
          <tr>
            <td>${escapeHtml(c.name)}</td>
            <td class="${c.ok ? "ok" : "bad"}">${escapeHtml(c.ok ? "OK" : "FAIL")}</td>
            <td><pre>${escapeHtml(typeof c.details === "string" ? c.details : JSON.stringify(c.details, null, 2))}</pre></td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}


document.getElementById("healthBtn").addEventListener("click", async () => {
  try {
    await refreshHealth();
  } catch (err) {
    renderSimpleMessage(document.getElementById("healthOut"), "System Health", "failed", err.message);
  }
});

  const apiTokenInput = document.getElementById("apiBearerToken");
  if (apiTokenInput) {
    apiTokenInput.value = localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || "";
    const persistToken = () => {
      localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, apiTokenInput.value.trim());
    };
    apiTokenInput.addEventListener("input", persistToken);
    apiTokenInput.addEventListener("change", persistToken);
  }

document.getElementById("syncBtn").addEventListener("click", async () => {
  try {
    const dryRun = document.getElementById("syncDryRun").checked;
    const runIngest = document.getElementById("syncRunIngest").checked && !dryRun;
    await api("/api/sync", {
      dry_run: dryRun,
      source_mode: document.getElementById("syncSourceMode").value || "zotero_db",
      run_ingest: runIngest,
      ingest_skip_existing: document.getElementById("syncSkipExisting").checked,
    });
    renderSimpleMessage(document.getElementById("syncOut"), "Sync + Ingest", "running", "Starting workflow...");
    startPolling("sync", async (payload) => {
      renderSyncJob(payload);
      if (payload.status !== "running") {
        await refreshHealth();
      }
    });
  } catch (err) {
    renderSimpleMessage(document.getElementById("syncOut"), "Sync + Ingest", "failed", err.message);
  }
});

document.getElementById("syncStopBtn").addEventListener("click", async () => {
  try {
    const payload = await api("/api/sync/stop", {});
    renderSyncJob(payload);
  } catch (err) {
    renderSimpleMessage(document.getElementById("syncOut"), "PDF Sync", "failed", err.message);
  }
});

document.getElementById("queryBtn").addEventListener("click", async () => {
  const query = document.getElementById("queryText").value.trim();
  const limit = parseInt(document.getElementById("queryLimit").value || "20", 10);
  const limitScope = document.getElementById("queryLimitScope").value || "papers";
  const chunksPerPaper = parseInt(document.getElementById("queryChunksPerPaper").value || "8", 10);
  const normalizedChunksPerPaper = Number.isNaN(chunksPerPaper) ? 8 : Math.max(1, Math.min(20, chunksPerPaper));
  const requestChunksPerPaper = limitScope === "papers" ? normalizedChunksPerPaper : 1;
  try {
    await api("/api/query", {
      query,
      limit,
      limit_scope: limitScope,
      chunks_per_paper: requestChunksPerPaper,
    });
    renderSimpleMessage(document.getElementById("queryResults"), "Query", "running", "Starting query...");
    startPolling("query", (job) => {
      renderQueryJob(job);
    });
  } catch (err) {
    renderSimpleMessage(document.getElementById("queryResults"), "Query", "failed", err.message);
  }
});

function updateQueryScopeControls() {
  const limitScope = document.getElementById("queryLimitScope").value || "papers";
  const chunksInput = document.getElementById("queryChunksPerPaper");
  const chunksLabel = document.getElementById("queryChunksPerPaperLabel");
  const paperMode = limitScope === "papers";
  chunksInput.disabled = !paperMode;
  chunksLabel.style.opacity = paperMode ? "1" : "0.6";
  chunksInput.title = paperMode
    ? "Used only when Count Results By = Papers"
    : "Disabled because Count Results By = Chunks";
}

document.getElementById("queryLimitScope").addEventListener("change", updateQueryScopeControls);
updateQueryScopeControls();

document.getElementById("queryStopBtn").addEventListener("click", async () => {
  try {
    const payload = await api("/api/query/stop", {});
    renderQueryJob(payload);
  } catch (err) {
    renderSimpleMessage(document.getElementById("queryResults"), "Query", "failed", err.message);
  }
});

document.getElementById("diagBtn").addEventListener("click", async () => {
  const out = document.getElementById("diagOut");
  renderSimpleMessage(out, "Diagnostics", "running", "Running checks...");
  try {
    const res = await fetch("/api/diagnostics");
    const payload = await res.json();
    renderDiagnostics(payload);
  } catch (err) {
    renderSimpleMessage(out, "Diagnostics", "failed", err.message);
  }
});

renderSyncJob({ status: "idle" });
renderQueryJob({ status: "idle" });
renderSimpleMessage(document.getElementById("diagOut"), "Diagnostics", "idle", "Click Run Diagnostics.");
initDocumentationTabs();
refreshHealth().catch((err) => {
  renderSimpleMessage(document.getElementById("healthOut"), "System Health", "failed", err.message);
});
