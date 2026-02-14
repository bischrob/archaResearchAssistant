async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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

function statusHeader(job, label) {
  const running = job?.status === "running";
  return `
    <div class="status-line">
      ${running ? '<span class="spinner" aria-hidden="true"></span>' : ""}
      <strong>${label}</strong>
      <span class="status-pill ${statusClass(job?.status)}">${escapeHtml(job?.status || "idle")}</span>
    </div>
  `;
}

function renderSimpleMessage(el, title, status, message) {
  el.innerHTML = `
    <div class="status-line">
      ${status === "running" ? '<span class="spinner"></span>' : ""}
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
      const res = await fetch(`/api/${name}/status`);
      const payload = await res.json();
      onUpdate(payload);
      if (payload.status !== "running") {
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
  const result = job.result || {};
  const stdout = result.stdout || "";
  const stderr = result.stderr || "";
  out.innerHTML = `
    ${statusHeader(job, "PDF Sync")}
    <div class="kv">
      <strong>Return Code</strong><span>${escapeHtml(result.returncode ?? "-")}</span>
      <strong>Success</strong><span>${escapeHtml(result.ok ?? job.status === "completed")}</span>
    </div>
    ${job.error ? `<div class="empty">Error: ${escapeHtml(job.error)}</div>` : ""}
    ${stdout ? `<details><summary>Stdout</summary><pre>${escapeHtml(stdout)}</pre></details>` : ""}
    ${stderr ? `<details><summary>Stderr</summary><pre>${escapeHtml(stderr)}</pre></details>` : ""}
    ${!stdout && !stderr && job.status !== "running" ? '<div class="empty">No output.</div>' : ""}
  `;
}

function renderIngestJob(job) {
  const out = document.getElementById("ingestOut");
  if (!job) {
    renderSimpleMessage(out, "Ingest", "idle", "Not started.");
    return;
  }
  const summary = job.result?.summary || {};
  const selected = summary.selected_pdfs || [];
  const skipped = summary.skipped_existing_pdfs || [];
  const failed = summary.failed_pdfs || [];
  out.innerHTML = `
    ${statusHeader(job, "Ingest Job")}
    <div class="kv">
      <strong>Ingested Articles</strong><span>${escapeHtml(summary.ingested_articles ?? 0)}</span>
      <strong>Total Chunks</strong><span>${escapeHtml(summary.total_chunks ?? 0)}</span>
      <strong>Total References</strong><span>${escapeHtml(summary.total_references ?? 0)}</span>
      <strong>Skipped Existing</strong><span>${escapeHtml(skipped.length)}</span>
      <strong>Failed Files</strong><span>${escapeHtml(failed.length)}</span>
    </div>
    ${job.error ? `<div class="empty">Error: ${escapeHtml(job.error)}</div>` : ""}
    ${selected.length ? `<details><summary>Selected PDFs (${selected.length})</summary><ul class="list-box">${selected.slice(0, 100).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
    ${skipped.length ? `<details><summary>Skipped Existing PDFs (${skipped.length})</summary><ul class="list-box">${skipped.slice(0, 100).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
    ${failed.length ? `<details><summary>Failed PDFs (${failed.length})</summary><ul class="list-box">${failed.slice(0, 100).map((x) => `<li>${escapeHtml(x.pdf)}: ${escapeHtml(x.error)}</li>`).join("")}</ul></details>` : ""}
    ${job.status === "running" ? '<div class="empty">Ingest is running. Use Stop to cancel.</div>' : ""}
  `;
}

function renderQueryJob(job) {
  const results = document.getElementById("queryResults");
  if (!job) {
    renderSimpleMessage(results, "Query", "idle", "No query executed yet.");
    return;
  }
  if (job.status === "running") {
    renderSimpleMessage(results, "Query", "running", "Searching...");
    return;
  }
  if (job.status === "cancelled") {
    renderSimpleMessage(results, "Query", "cancelled", "Query cancelled.");
    return;
  }
  if (job.status === "failed") {
    renderSimpleMessage(results, "Query", "failed", job.error || "Query failed.");
    return;
  }

  const payload = job.result || {};
  const rows = payload.results || [];
  if (!rows.length) {
    renderSimpleMessage(results, "Query", "completed", "No results.");
    return;
  }

  results.innerHTML = `
    ${statusHeader(job, "Query Results")}
    ${rows
      .map((r, i) => {
        const cites = (r.cites_out || []).join(", ");
        const citedBy = (r.cited_by || []).join(", ");
        return `
          <article class="result">
            <strong>[${i + 1}] ${escapeHtml(r.article_title || "Untitled")} (${escapeHtml(r.article_year || "")})</strong>
            <div class="meta">Author: ${escapeHtml(r.author || "")} | Score: ${escapeHtml((r.combined_score || 0).toFixed(4))}</div>
            <div class="meta">Chunk: ${escapeHtml(r.chunk_id || "")} | Pages: ${escapeHtml(r.page_start || "")}-${escapeHtml(r.page_end || "")}</div>
            <p>${escapeHtml((r.chunk_text || "").slice(0, 650))}...</p>
            ${cites ? `<div class="meta"><strong>Cites:</strong> ${escapeHtml(cites)}</div>` : ""}
            ${citedBy ? `<div class="meta"><strong>Cited by:</strong> ${escapeHtml(citedBy)}</div>` : ""}
          </article>
        `;
      })
      .join("")}
  `;
}

document.getElementById("healthBtn").addEventListener("click", async () => {
  try {
    await refreshHealth();
  } catch (err) {
    renderSimpleMessage(document.getElementById("healthOut"), "System Health", "failed", err.message);
  }
});

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
  const lines = document.getElementById("customPdfs").value
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  try {
    await api("/api/ingest", {
      mode,
      source_dir: document.getElementById("sourceDir").value.trim() || "pdfs",
      pdfs: lines,
      override_existing: document.getElementById("overrideExisting").checked,
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
  const limit = parseInt(document.getElementById("queryLimit").value || "5", 10);
  try {
    await api("/api/query", { query, limit });
    renderSimpleMessage(document.getElementById("queryResults"), "Query", "running", "Starting query...");
    startPolling("query", (job) => {
      renderQueryJob(job);
    });
  } catch (err) {
    renderSimpleMessage(document.getElementById("queryResults"), "Query", "failed", err.message);
  }
});

document.getElementById("queryStopBtn").addEventListener("click", async () => {
  try {
    const payload = await api("/api/query/stop", {});
    renderQueryJob(payload);
  } catch (err) {
    renderSimpleMessage(document.getElementById("queryResults"), "Query", "failed", err.message);
  }
});

renderSyncJob({ status: "idle" });
renderIngestJob({ status: "idle" });
renderQueryJob({ status: "idle" });
refreshHealth().catch((err) => {
  renderSimpleMessage(document.getElementById("healthOut"), "System Health", "failed", err.message);
});

