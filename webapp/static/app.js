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

function renderHealth(payload) {
  const out = document.getElementById("healthOut");
  const stats = payload?.stats || {};
  out.innerHTML = `
    ${statusHeader({ status: "completed" }, "System Health")}
    <div class="kv">
      <strong>Status</strong><span>${escapeHtml(payload?.status || "unknown")}</span>
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
  const unmatched = result.unmatched_sample || [];
  out.innerHTML = `
    ${statusHeader(job, "PDF Sync")}
    ${progressBlock(job)}
    <div class="kv">
      <strong>Lifecycle</strong><span>${escapeHtml(state)}</span>
      <strong>Success</strong><span>${escapeHtml(result.ok ?? job.status === "completed")}</span>
      <strong>Source Mode</strong><span>${escapeHtml(result.source_mode ?? "-")}</span>
      <strong>PDFs Total</strong><span>${escapeHtml(result.pdfs_total ?? "-")}</span>
      <strong>With Metadata</strong><span>${escapeHtml(result.pdfs_with_metadata ?? "-")}</span>
      <strong>Unmatched</strong><span>${escapeHtml(result.pdfs_unmatched ?? "-")}</span>
      <strong>Ingest Ran</strong><span>${escapeHtml(result.ingest_ran ?? false)}</span>
      <strong>Ingested Articles</strong><span>${escapeHtml(ingest.ingested_articles ?? "-")}</span>
      <strong>Ingest Failed PDFs</strong><span>${escapeHtml((ingest.failed_pdfs || []).length)}</span>
      <strong>Terminal Reason</strong><span>${escapeHtml(job.terminal_reason ?? "-")}</span>
      <strong>Stop State</strong><span>${escapeHtml(job.stop_state ?? "-")}</span>
    </div>
    ${job.error ? `<div class="empty">Error: ${escapeHtml(job.error)}</div>` : ""}
    ${Object.keys(sourceStats).length ? `<details><summary>Source Stats</summary><pre>${escapeHtml(JSON.stringify(sourceStats, null, 2))}</pre></details>` : ""}
    ${unmatched.length ? `<details><summary>Unmatched Sample (${unmatched.length})</summary><ul class="list-box">${unmatched.slice(0, 30).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
  `;
}

function renderIngestJob(job) {
  const out = document.getElementById("ingestOut");
  if (!job) {
    renderSimpleMessage(out, "Ingest", "idle", "Not started.");
    return;
  }
  const state = jobState(job);
  const summary = job.result?.summary || {};
  const selected = summary.selected_pdfs || [];
  const skipped = summary.skipped_existing_pdfs || [];
  const skippedMeta = summary.skipped_no_metadata_pdfs || [];
  const failed = summary.failed_pdfs || [];
  const batchResults = summary.batch_results || [];
  const anystyleAttempted = summary.anystyle_attempted_pdfs ?? 0;
  const anystyleApplied = summary.anystyle_applied_pdfs ?? 0;
  const anystyleEmpty = summary.anystyle_empty_pdfs ?? 0;
  const anystyleFailed = summary.anystyle_failed_pdfs ?? 0;
  const anystyleDisabledReason = summary.anystyle_disabled_reason || "";
  const anystyleFailureSamples = summary.anystyle_failure_samples || [];
  const qwenAttempted = summary.qwen_attempted_pdfs ?? 0;
  const qwenApplied = summary.qwen_applied_pdfs ?? 0;
  const qwenEmpty = summary.qwen_empty_pdfs ?? 0;
  const qwenFailed = summary.qwen_failed_pdfs ?? 0;
  const qwenDisabledReason = summary.qwen_disabled_reason || "";
  const qwenFailureSamples = summary.qwen_failure_samples || [];
  out.innerHTML = `
    ${statusHeader(job, "Ingest Job")}
    ${progressBlock(job)}
    <div class="kv">
      <strong>Mode</strong><span>${escapeHtml(summary.mode ?? "-")}</span>
      <strong>Batch Size</strong><span>${escapeHtml(summary.batch_size ?? "-")}</span>
      <strong>Batches</strong><span>${escapeHtml(summary.batch_total ?? "-")}</span>
      <strong>Ingested Articles</strong><span>${escapeHtml(summary.ingested_articles ?? 0)}</span>
      <strong>Total Chunks</strong><span>${escapeHtml(summary.total_chunks ?? 0)}</span>
      <strong>Total References</strong><span>${escapeHtml(summary.total_references ?? 0)}</span>
      <strong>Skipped Existing</strong><span>${escapeHtml(skipped.length)}</span>
      <strong>Skipped No Metadata</strong><span>${escapeHtml(skippedMeta.length)}</span>
      <strong>Failed Files</strong><span>${escapeHtml(failed.length)}</span>
      <strong>Anystyle Attempted</strong><span>${escapeHtml(anystyleAttempted)}</span>
      <strong>Anystyle Applied</strong><span>${escapeHtml(anystyleApplied)}</span>
      <strong>Anystyle Empty</strong><span>${escapeHtml(anystyleEmpty)}</span>
      <strong>Anystyle Failed</strong><span>${escapeHtml(anystyleFailed)}</span>
      <strong>Qwen Attempted</strong><span>${escapeHtml(qwenAttempted)}</span>
      <strong>Qwen Applied</strong><span>${escapeHtml(qwenApplied)}</span>
      <strong>Qwen Empty</strong><span>${escapeHtml(qwenEmpty)}</span>
      <strong>Qwen Failed</strong><span>${escapeHtml(qwenFailed)}</span>
      <strong>Lifecycle</strong><span>${escapeHtml(state)}</span>
    </div>
    ${job.error ? `<div class="empty">Error: ${escapeHtml(job.error)}</div>` : ""}
    ${anystyleDisabledReason ? `<div class="empty">Anystyle disabled for remainder of ingest: ${escapeHtml(anystyleDisabledReason)}</div>` : ""}
    ${qwenDisabledReason ? `<div class="empty">Qwen disabled for remainder of ingest: ${escapeHtml(qwenDisabledReason)}</div>` : ""}
    ${batchResults.length ? `
      <details open>
        <summary>Batch Results (${batchResults.length})</summary>
        <table class="preview-table">
          <thead>
            <tr>
              <th>Batch</th><th>Input PDFs</th><th>Ingested</th><th>Chunks</th><th>References</th><th>Anystyle Applied</th><th>Anystyle Failed</th><th>Qwen Applied</th><th>Qwen Failed</th><th>Skipped Existing</th><th>Skipped No Metadata</th><th>Failed</th>
            </tr>
          </thead>
          <tbody>
            ${batchResults.map((b) => `
              <tr>
                <td>${escapeHtml(`${b.batch_number}/${b.batch_total}`)}</td>
                <td>${escapeHtml(b.input_pdfs ?? 0)}</td>
                <td>${escapeHtml(b.ingested_articles ?? 0)}</td>
                <td>${escapeHtml(b.total_chunks ?? 0)}</td>
                <td>${escapeHtml(b.total_references ?? 0)}</td>
                <td>${escapeHtml(b.anystyle_applied_pdfs ?? 0)}</td>
                <td>${escapeHtml(b.anystyle_failed_pdfs ?? 0)}</td>
                <td>${escapeHtml(b.qwen_applied_pdfs ?? 0)}</td>
                <td>${escapeHtml(b.qwen_failed_pdfs ?? 0)}</td>
                <td>${escapeHtml(b.skipped_existing_count ?? 0)}</td>
                <td>${escapeHtml(b.skipped_no_metadata_count ?? 0)}</td>
                <td>${escapeHtml(b.failed_count ?? 0)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </details>
    ` : ""}
    ${anystyleFailureSamples.length ? `<details><summary>Anystyle Failures (${anystyleFailureSamples.length})</summary><ul class="list-box">${anystyleFailureSamples.slice(0, 100).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
    ${qwenFailureSamples.length ? `<details><summary>Qwen Failures (${qwenFailureSamples.length})</summary><ul class="list-box">${qwenFailureSamples.slice(0, 100).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
    ${selected.length ? `<details><summary>Selected PDFs (${selected.length})</summary><ul class="list-box">${selected.slice(0, 100).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
    ${skipped.length ? `<details><summary>Skipped Existing PDFs (${skipped.length})</summary><ul class="list-box">${skipped.slice(0, 100).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
    ${skippedMeta.length ? `<details><summary>Skipped No Metadata PDFs (${skippedMeta.length})</summary><ul class="list-box">${skippedMeta.slice(0, 100).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
    ${failed.length ? `<details><summary>Failed PDFs (${failed.length})</summary><ul class="list-box">${failed.slice(0, 100).map((x) => `<li>${escapeHtml(x.pdf)}: ${escapeHtml(x.error)}</li>`).join("")}</ul></details>` : ""}
    ${state === "running" || state === "cancelling" ? '<div class="empty">Ingest is running. Use Stop to cancel.</div>' : ""}
  `;
}

function renderIngestPreview(payload) {
  const out = document.getElementById("ingestPreviewOut");
  const summary = payload?.summary || {};
  const rows = payload?.rows || [];
  if (!rows.length) {
    renderSimpleMessage(out, "Ingest Preview", "completed", "No files to preview.");
    return;
  }
  out.innerHTML = `
    ${statusHeader({ status: "completed" }, "Ingest Preview")}
    <div class="kv">
      <strong>Total Resolved</strong><span>${escapeHtml(summary.total_resolved ?? rows.length)}</span>
      <strong>Will Ingest</strong><span>${escapeHtml(summary.will_ingest_count ?? 0)}</span>
      <strong>Already In Graph</strong><span>${escapeHtml(summary.existing_count ?? 0)}</span>
      <strong>Metadata Found</strong><span>${escapeHtml(summary.metadata_found_count ?? 0)}</span>
      <strong>Previewed Rows</strong><span>${escapeHtml(summary.total_previewed ?? rows.length)}</span>
    </div>
    ${summary.truncated ? '<div class="empty">Preview truncated to first 300 files.</div>' : ""}
    <details open>
      <summary>Preview Rows</summary>
      <table class="preview-table">
        <thead>
          <tr>
            <th>File</th>
            <th>Will Ingest</th>
            <th>In Graph</th>
            <th>Metadata</th>
            <th>Title / Year / Authors</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((r) => {
              const titleYear = `${r.title || "(no title)"}${r.year ? ` (${r.year})` : ""}`;
              const authors = (r.authors || []).slice(0, 4).join(", ");
              return `
                <tr>
                  <td>${escapeHtml(r.file || r.path)}</td>
                  <td>${escapeHtml(r.will_ingest ? "yes" : "no")}</td>
                  <td>${escapeHtml(r.exists_in_graph ? "yes" : "no")}</td>
                  <td>${escapeHtml(r.metadata_found ? "yes" : "no")}</td>
                  <td>${escapeHtml(titleYear)}${authors ? `<br><span class="meta">${escapeHtml(authors)}</span>` : ""}</td>
                </tr>
              `;
            })
            .join("")}
        </tbody>
      </table>
    </details>
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
    await api("/api/sync", {
      dry_run: document.getElementById("syncDryRun").checked,
    });
    renderSimpleMessage(document.getElementById("syncOut"), "PDF Sync", "running", "Starting sync...");
    startPolling("sync", async (payload) => {
      renderSyncJob(payload);
      if (payload.status !== "running") {
        await refreshHealth();
      }
    });
  } catch (err) {
    renderSimpleMessage(document.getElementById("syncOut"), "PDF Sync", "failed", err.message);
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

document.getElementById("ingestBtn").addEventListener("click", async () => {
  const mode = document.getElementById("ingestMode").value;
  const partialCount = parseInt(document.getElementById("partialCount").value || "3", 10);
  const lines = document.getElementById("customPdfs").value
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  try {
    await api("/api/ingest", {
      mode,
      source_dir: document.getElementById("sourceDir").value.trim() || "\\\\192.168.0.37\\pooled\\media\\Books\\pdfs",
      pdfs: lines,
      override_existing: document.getElementById("overrideExisting").checked,
      partial_count: Number.isNaN(partialCount) ? 3 : Math.max(1, partialCount),
    });
    renderSimpleMessage(document.getElementById("ingestOut"), "Ingest Job", "running", "Starting ingest...");
    startPolling("ingest", async (payload) => {
      renderIngestJob(payload);
      if (payload.status !== "running") {
        await refreshHealth();
      }
    });
  } catch (err) {
    renderSimpleMessage(document.getElementById("ingestOut"), "Ingest Job", "failed", err.message);
  }
});

document.getElementById("ingestPreviewBtn").addEventListener("click", async () => {
  const mode = document.getElementById("ingestMode").value;
  const partialCount = parseInt(document.getElementById("partialCount").value || "3", 10);
  const lines = document.getElementById("customPdfs").value
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  const out = document.getElementById("ingestPreviewOut");
  renderSimpleMessage(out, "Ingest Preview", "running", "Building preview...");
  try {
    const payload = await api("/api/ingest/preview", {
      mode,
      source_dir: document.getElementById("sourceDir").value.trim() || "\\\\192.168.0.37\\pooled\\media\\Books\\pdfs",
      pdfs: lines,
      override_existing: document.getElementById("overrideExisting").checked,
      partial_count: Number.isNaN(partialCount) ? 3 : Math.max(1, partialCount),
    });
    renderIngestPreview(payload);
  } catch (err) {
    renderSimpleMessage(out, "Ingest Preview", "failed", err.message);
  }
});

document.getElementById("ingestStopBtn").addEventListener("click", async () => {
  try {
    const payload = await api("/api/ingest/stop", {});
    renderIngestJob(payload);
  } catch (err) {
    renderSimpleMessage(document.getElementById("ingestOut"), "Ingest Job", "failed", err.message);
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
renderSimpleMessage(document.getElementById("ingestPreviewOut"), "Ingest Preview", "idle", "Click Preview Selection.");
renderIngestJob({ status: "idle" });
renderQueryJob({ status: "idle" });
renderSimpleMessage(document.getElementById("diagOut"), "Diagnostics", "idle", "Click Run Diagnostics.");
refreshHealth().catch((err) => {
  renderSimpleMessage(document.getElementById("healthOut"), "System Health", "failed", err.message);
});
