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

function startPolling(name, onUpdate) {
  stopPolling(name);
  pollers[name] = setInterval(async () => {
    const res = await fetch(`/api/${name}/status`);
    const payload = await res.json();
    onUpdate(payload);
    if (payload.status !== "running") {
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

async function refreshHealth() {
  const out = document.getElementById("healthOut");
  out.textContent = "Loading...";
  const res = await fetch("/api/health");
  const payload = await res.json();
  out.textContent = JSON.stringify(payload, null, 2);
}

document.getElementById("healthBtn").addEventListener("click", async () => {
  try {
    await refreshHealth();
  } catch (err) {
    document.getElementById("healthOut").textContent = err.message;
  }
});

document.getElementById("syncBtn").addEventListener("click", async () => {
  const out = document.getElementById("syncOut");
  out.textContent = "Starting sync...";
  try {
    await api("/api/sync", {
      dry_run: document.getElementById("syncDryRun").checked,
    });
    startPolling("sync", async (payload) => {
      out.textContent = JSON.stringify(payload, null, 2);
      if (payload.status !== "running") {
        await refreshHealth();
      }
    });
  } catch (err) {
    out.textContent = err.message;
  }
});

document.getElementById("syncStopBtn").addEventListener("click", async () => {
  const out = document.getElementById("syncOut");
  try {
    const payload = await api("/api/sync/stop", {});
    out.textContent = JSON.stringify(payload, null, 2);
  } catch (err) {
    out.textContent = err.message;
  }
});

document.getElementById("ingestBtn").addEventListener("click", async () => {
  const out = document.getElementById("ingestOut");
  out.textContent = "Starting ingest...";
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
    startPolling("ingest", async (payload) => {
      out.textContent = JSON.stringify(payload, null, 2);
      if (payload.status !== "running") {
        await refreshHealth();
      }
    });
  } catch (err) {
    out.textContent = err.message;
  }
});

document.getElementById("ingestStopBtn").addEventListener("click", async () => {
  const out = document.getElementById("ingestOut");
  try {
    const payload = await api("/api/ingest/stop", {});
    out.textContent = JSON.stringify(payload, null, 2);
  } catch (err) {
    out.textContent = err.message;
  }
});

document.getElementById("queryBtn").addEventListener("click", async () => {
  const results = document.getElementById("queryResults");
  results.textContent = "Starting query...";
  const query = document.getElementById("queryText").value.trim();
  const limit = parseInt(document.getElementById("queryLimit").value || "5", 10);
  try {
    await api("/api/query", { query, limit });
    startPolling("query", (job) => {
      if (job.status === "running") {
        results.textContent = "Searching...";
        return;
      }
      if (job.status === "cancelled") {
        results.textContent = "Query cancelled.";
        return;
      }
      if (job.status === "failed") {
        results.textContent = job.error || "Query failed.";
        return;
      }
      const payload = job.result || {};
      const rows = payload.results || [];
      if (!rows.length) {
        results.textContent = "No results.";
        return;
      }
      results.innerHTML = rows
        .map((r, i) => {
          const cites = (r.cites_out || []).join(", ");
          const citedBy = (r.cited_by || []).join(", ");
          return `
            <article class="result">
              <strong>[${i + 1}] ${r.article_title || "Untitled"} (${r.article_year || ""})</strong>
              <div class="meta">Author: ${r.author || ""} | Score: ${(r.combined_score || 0).toFixed(4)}</div>
              <div class="meta">Chunk: ${r.chunk_id || ""} | Pages: ${r.page_start || ""}-${r.page_end || ""}</div>
              <p>${(r.chunk_text || "").slice(0, 650)}...</p>
              ${cites ? `<div class="meta"><strong>Cites:</strong> ${cites}</div>` : ""}
              ${citedBy ? `<div class="meta"><strong>Cited by:</strong> ${citedBy}</div>` : ""}
            </article>
          `;
        })
        .join("");
    });
  } catch (err) {
    results.textContent = err.message;
  }
});

document.getElementById("queryStopBtn").addEventListener("click", async () => {
  const results = document.getElementById("queryResults");
  try {
    const payload = await api("/api/query/stop", {});
    results.textContent = JSON.stringify(payload, null, 2);
  } catch (err) {
    results.textContent = err.message;
  }
});

refreshHealth().catch(() => {});
