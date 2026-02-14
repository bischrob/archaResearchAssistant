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
let lastAskReport = null;
let askLoadingTimer = null;

function escapeHtml(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function markdownToHtml(markdown) {
  let text = escapeHtml(String(markdown || "").replaceAll("\r\n", "\n"));
  const codeBlocks = [];
  text = text.replace(/```([\s\S]*?)```/g, (_, code) => {
    const token = `@@CODEBLOCK_${codeBlocks.length}@@`;
    codeBlocks.push(`<pre><code>${code}</code></pre>`);
    return token;
  });
  text = text.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  text = text.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  text = text.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/\*(.+?)\*/g, "<em>$1</em>");
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  text = text.replace(/(?:^|\n)((?:- .*(?:\n|$))+)/g, (m, list) => {
    const items = list
      .trim()
      .split("\n")
      .map((line) => line.replace(/^- /, "").trim())
      .map((item) => `<li>${item}</li>`)
      .join("");
    return `\n<ul>${items}</ul>\n`;
  });
  const blocks = text
    .split(/\n{2,}/)
    .map((b) => b.trim())
    .filter(Boolean)
    .map((b) => {
      if (/^<(h1|h2|h3|ul|pre)/.test(b) || /^@@CODEBLOCK_\d+@@$/.test(b)) {
        return b;
      }
      return `<p>${b.replaceAll("\n", "<br />")}</p>`;
    });
  let html = blocks.join("\n");
  for (let i = 0; i < codeBlocks.length; i += 1) {
    html = html.replace(`@@CODEBLOCK_${i}@@`, codeBlocks[i]);
  }
  return html;
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
    ${progressBlock(job)}
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
  const skippedMeta = summary.skipped_no_metadata_pdfs || [];
  const failed = summary.failed_pdfs || [];
  const batchResults = summary.batch_results || [];
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
    </div>
    ${job.error ? `<div class="empty">Error: ${escapeHtml(job.error)}</div>` : ""}
    ${batchResults.length ? `
      <details open>
        <summary>Batch Results (${batchResults.length})</summary>
        <table class="preview-table">
          <thead>
            <tr>
              <th>Batch</th><th>Input PDFs</th><th>Ingested</th><th>Chunks</th><th>References</th><th>Skipped Existing</th><th>Skipped No Metadata</th><th>Failed</th>
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
                <td>${escapeHtml(b.skipped_existing_count ?? 0)}</td>
                <td>${escapeHtml(b.skipped_no_metadata_count ?? 0)}</td>
                <td>${escapeHtml(b.failed_count ?? 0)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </details>
    ` : ""}
    ${selected.length ? `<details><summary>Selected PDFs (${selected.length})</summary><ul class="list-box">${selected.slice(0, 100).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
    ${skipped.length ? `<details><summary>Skipped Existing PDFs (${skipped.length})</summary><ul class="list-box">${skipped.slice(0, 100).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
    ${skippedMeta.length ? `<details><summary>Skipped No Metadata PDFs (${skippedMeta.length})</summary><ul class="list-box">${skippedMeta.slice(0, 100).map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></details>` : ""}
    ${failed.length ? `<details><summary>Failed PDFs (${failed.length})</summary><ul class="list-box">${failed.slice(0, 100).map((x) => `<li>${escapeHtml(x.pdf)}: ${escapeHtml(x.error)}</li>`).join("")}</ul></details>` : ""}
    ${job.status === "running" ? '<div class="empty">Ingest is running. Use Stop to cancel.</div>' : ""}
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
    ${progressBlock(job)}
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

function renderAskResult(payload) {
  const out = document.getElementById("askOut");
  const used = payload?.used_citations || [];
  const allCites = payload?.all_citations || [];
  const answer = payload?.answer || "";
  const audit = payload?.audit || {};
  const preprocess = payload?.query_preprocess || {};
  out.innerHTML = `
    ${statusHeader({ status: "completed" }, "LLM Answer")}
    <div class="kv">
      <strong>Model</strong><span>${escapeHtml(payload?.model || "")}</span>
      <strong>Search Query Used</strong><span>${escapeHtml(payload?.search_query_used || payload?.question || "")}</span>
      <strong>Preprocess Method</strong><span>${escapeHtml(preprocess.method || "identity")}</span>
      <strong>RAG Results Used</strong><span>${escapeHtml(payload?.rag_results_count ?? 0)}</span>
      <strong>Citations Referenced</strong><span>${escapeHtml(used.length)}</span>
      <strong>Citation Enforcement</strong><span>${escapeHtml(payload?.citation_enforced ?? true)}</span>
      <strong>Risk</strong><span>${escapeHtml(audit.risk_label || "n/a")} (${escapeHtml(audit.risk_score ?? "n/a")})</span>
    </div>
    ${preprocess.error ? `<div class="empty">Preprocess fallback: ${escapeHtml(preprocess.error)}</div>` : ""}
    ${audit.unsupported_sentence_count ? `<details><summary>Potentially Unsupported Sentences (${escapeHtml(audit.unsupported_sentence_count)})</summary><ul class="list-box">${(audit.unsupported_sentences || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul></details>` : ""}
    <details open>
      <summary>Answer</summary>
      <article class="markdown-body">${markdownToHtml(answer)}</article>
    </details>
    ${used.length ? `
      <details open>
        <summary>Used Citations (${used.length})</summary>
        <table class="preview-table">
          <thead>
            <tr>
              <th>ID</th><th>Title</th><th>Year</th><th>Authors</th><th>Citekey</th><th>Pages</th><th>Chunk</th>
            </tr>
          </thead>
          <tbody>
            ${used.map((c) => `
              <tr>
                <td>${escapeHtml(c.citation_id)}</td>
                <td>${escapeHtml(c.article_title || "")}</td>
                <td>${escapeHtml(c.article_year || "")}</td>
                <td>${escapeHtml((c.authors || []).join(", "))}</td>
                <td>${escapeHtml(c.citekey || "")}</td>
                <td>${escapeHtml(c.page_start || "")}-${escapeHtml(c.page_end || "")}</td>
                <td>${escapeHtml(c.chunk_id || "")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </details>
    ` : '<div class="empty">No inline [C#] citations were detected in the model output.</div>'}
    <details>
      <summary>All Provided Context Citations (${allCites.length})</summary>
      <ul class="list-box">
        ${allCites.slice(0, 200).map((c) => `<li>${escapeHtml(c.citation_id)} - ${escapeHtml(c.article_title || "")}</li>`).join("")}
      </ul>
    </details>
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

function initTabs() {
  const buttons = Array.from(document.querySelectorAll(".tab-btn"));
  const tabs = Array.from(document.querySelectorAll(".tab-content"));
  for (const btn of buttons) {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab");
      buttons.forEach((b) => b.classList.remove("active"));
      tabs.forEach((t) => t.classList.remove("active"));
      btn.classList.add("active");
      const tab = document.getElementById(target);
      if (tab) tab.classList.add("active");
    });
  }
}

async function downloadReport(format, filename) {
  if (!lastAskReport) {
    renderSimpleMessage(document.getElementById("askOut"), "LLM Answer", "failed", "No report to export yet.");
    return;
  }
  const res = await fetch("/api/ask/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report: lastAskReport, format }),
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt || "Export failed");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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
  const partialCount = parseInt(document.getElementById("partialCount").value || "3", 10);
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
      source_dir: document.getElementById("sourceDir").value.trim() || "pdfs",
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

document.getElementById("askBtn").addEventListener("click", async () => {
  const out = document.getElementById("askOut");
  const question = document.getElementById("askQuestion").value.trim();
  const ragResults = parseInt(document.getElementById("askRagResults").value || "8", 10);
  const model = document.getElementById("askModel").value.trim();
  if (!question) {
    renderSimpleMessage(out, "LLM Answer", "failed", "Question cannot be empty.");
    return;
  }
  const loadingSteps = [
    "Parsing question and extracting likely search terms...",
    "Running pre-LLM query rewrite...",
    "Searching Neo4j with the rewritten query...",
    "Compiling grounded citation context...",
    "Calling model for final grounded answer...",
  ];
  let loadingIndex = 0;
  renderSimpleMessage(out, "LLM Answer", "running", loadingSteps[loadingIndex]);
  if (askLoadingTimer) clearInterval(askLoadingTimer);
  askLoadingTimer = setInterval(() => {
    loadingIndex = Math.min(loadingIndex + 1, loadingSteps.length - 1);
    renderSimpleMessage(out, "LLM Answer", "running", loadingSteps[loadingIndex]);
  }, 1400);
  try {
    const payload = await api("/api/ask", {
      question,
      rag_results: ragResults,
      model: model || null,
      enforce_citations: document.getElementById("askEnforceCitations").checked,
      preprocess_search: document.getElementById("askPreprocessSearch").checked,
    });
    if (askLoadingTimer) {
      clearInterval(askLoadingTimer);
      askLoadingTimer = null;
    }
    lastAskReport = payload;
    renderAskResult(payload);
  } catch (err) {
    if (askLoadingTimer) {
      clearInterval(askLoadingTimer);
      askLoadingTimer = null;
    }
    renderSimpleMessage(out, "LLM Answer", "failed", err.message);
  }
});

document.getElementById("askExportMdBtn").addEventListener("click", async () => {
  try {
    await downloadReport("markdown", "rag_answer_report.md");
  } catch (err) {
    renderSimpleMessage(document.getElementById("askOut"), "LLM Answer", "failed", err.message);
  }
});

document.getElementById("askExportCsvBtn").addEventListener("click", async () => {
  try {
    await downloadReport("csv", "rag_used_citations.csv");
  } catch (err) {
    renderSimpleMessage(document.getElementById("askOut"), "LLM Answer", "failed", err.message);
  }
});

document.getElementById("askExportPdfBtn").addEventListener("click", async () => {
  try {
    await downloadReport("pdf", "rag_answer_report.pdf");
  } catch (err) {
    renderSimpleMessage(document.getElementById("askOut"), "LLM Answer", "failed", err.message);
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
renderSimpleMessage(document.getElementById("askOut"), "LLM Answer", "idle", "Ask a grounded question.");
renderSimpleMessage(document.getElementById("diagOut"), "Diagnostics", "idle", "Click Run Diagnostics.");
initTabs();
refreshHealth().catch((err) => {
  renderSimpleMessage(document.getElementById("healthOut"), "System Health", "failed", err.message);
});
