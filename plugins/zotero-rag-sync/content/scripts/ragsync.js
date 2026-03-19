/* eslint-disable no-undef */

var RAGSync = {
  initialized: false,
  injectedMenuID: 'rag-sync-tools-menu',
  syncInProgress: false,
  progressWindow: null,
  lastSyncStatus: 'never',
  lastSyncMessage: 'No sync run yet',
  lastSyncFinishedAt: null,
  id: null,
  version: null,
  rootURI: null,
  prefBackendURL: 'extensions.zotero-rag-sync.backendURL',
  prefBearerToken: 'extensions.zotero-rag-sync.bearerToken',
  prefSourceMode: 'extensions.zotero-rag-sync.sourceMode',
  prefSourceDir: 'extensions.zotero-rag-sync.sourceDir',
  prefPaused: 'extensions.zotero-rag-sync.paused',
  syncPollIntervalMS: 700,
  syncPollTimeoutMS: 60 * 60 * 1000,
  overlayDismissed: false,

  log(msg) {
    Zotero.debug('RAG Sync: ' + String(msg || ''));
  },

  getMainWindow() {
    return Zotero.getMainWindow && Zotero.getMainWindow();
  },

  getStringPref(prefName, fallback = '') {
    try {
      return Services.prefs.getStringPref(prefName, fallback).trim() || fallback;
    } catch (_err) {
      return fallback;
    }
  },

  getBoolPref(prefName, fallback = false) {
    try {
      return Services.prefs.getBoolPref(prefName, fallback);
    } catch (_err) {
      return fallback;
    }
  },

  setBoolPref(prefName, value) {
    Services.prefs.setBoolPref(prefName, !!value);
  },

  getBackendURL() {
    return this.getStringPref(this.prefBackendURL, 'http://127.0.0.1:8000').replace(/\/+$/, '');
  },

  getBearerToken() {
    return this.getStringPref(this.prefBearerToken, '');
  },

  getSourceDir() {
    return this.getStringPref(this.prefSourceDir, '');
  },

  getSourceMode() {
    const mode = this.getStringPref(this.prefSourceMode, 'zotero_db').toLowerCase();
    return mode === 'filesystem' ? 'filesystem' : 'zotero_db';
  },

  isPaused() {
    return this.getBoolPref(this.prefPaused, false);
  },

  alert(title, msg) {
    Zotero.alert(this.getMainWindow(), title, msg);
  },

  sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  },

  parseResponseJSON(req) {
    try {
      return JSON.parse(req.responseText || '{}');
    } catch (_err) {
      return {};
    }
  },

  getSyncNowLabel() {
    return this.syncInProgress ? 'Sync Now (Running...)' : 'Sync Now';
  },

  getCancelSyncLabel() {
    return this.syncInProgress ? 'Cancel Running Sync' : 'Cancel Sync';
  },

  getNormalizeAttachmentsLabel() {
    return 'Normalize Linked PDFs To Stored Attachments';
  },

  setProgressWindowTerminalState(isTerminal) {
    if (!this.progressWindow) {
      return;
    }
    const terminal = !!isTerminal;
    if (this.progressWindow.bgBtn) {
      this.progressWindow.bgBtn.style.display = terminal ? 'none' : '';
    }
    if (this.progressWindow.cancelBtn) {
      this.progressWindow.cancelBtn.style.display = terminal ? 'none' : '';
    }
    if (this.progressWindow.closeBtn) {
      this.progressWindow.closeBtn.style.display = terminal ? '' : 'none';
    }
  },

  updateMenuState() {
    const win = this.getMainWindow();
    if (!win || !win.document) {
      return;
    }
    const syncItem = win.document.getElementById('rag-sync-menu-sync-now');
    const cancelItem = win.document.getElementById('rag-sync-menu-cancel-sync');
    if (syncItem) {
      syncItem.setAttribute('label', this.getSyncNowLabel());
      if (this.syncInProgress) {
        syncItem.setAttribute('disabled', 'true');
      } else {
        syncItem.removeAttribute('disabled');
      }
    }
    if (cancelItem) {
      cancelItem.setAttribute('label', this.getCancelSyncLabel());
      if (this.syncInProgress) {
        cancelItem.removeAttribute('disabled');
      } else {
        cancelItem.setAttribute('disabled', 'true');
      }
    }
  },

  openProgressWindow(phaseText) {
    this.closeProgressWindow();
    this.overlayDismissed = false;
    const win = this.getMainWindow();
    if (!win || !win.document) {
      return null;
    }
    const doc = win.document;
    const existing = doc.getElementById('rag-sync-overlay-root');
    if (existing && existing.parentNode) {
      existing.parentNode.removeChild(existing);
    }

    const root = doc.createElement('div');
    root.id = 'rag-sync-overlay-root';
    root.setAttribute(
      'style',
      [
        'position:fixed',
        'inset:0',
        'display:flex',
        'align-items:center',
        'justify-content:center',
        'z-index:99999',
        'background:rgba(0,0,0,0.25)',
      ].join(';')
    );

    const panel = doc.createElement('div');
    panel.setAttribute(
      'style',
      [
        'width:min(760px,92vw)',
        'max-height:80vh',
        'overflow:auto',
        'background:#ffffff',
        'border:1px solid #9aa0a6',
        'border-radius:10px',
        'box-shadow:0 14px 40px rgba(0,0,0,0.35)',
        'padding:14px 16px',
        'font:13px sans-serif',
        'color:#1f2937',
      ].join(';')
    );

    const title = doc.createElement('div');
    title.textContent = 'RAG Sync';
    title.setAttribute('style', 'font-weight:700;font-size:15px;margin-bottom:8px;');
    panel.appendChild(title);

    const message = doc.createElement('div');
    message.textContent = phaseText || 'Working...';
    message.setAttribute('style', 'margin-bottom:8px;white-space:pre-wrap;');
    panel.appendChild(message);

    const barWrap = doc.createElement('div');
    barWrap.setAttribute('style', 'height:12px;background:#e5e7eb;border-radius:999px;overflow:hidden;');
    const bar = doc.createElement('div');
    bar.setAttribute('style', 'height:100%;width:0%;background:#2563eb;transition:width 120ms linear;');
    barWrap.appendChild(bar);
    panel.appendChild(barWrap);

    const percent = doc.createElement('div');
    percent.textContent = '0%';
    percent.setAttribute('style', 'margin-top:6px;font-size:12px;color:#374151;');
    panel.appendChild(percent);

    const detail = doc.createElement('div');
    detail.setAttribute('style', 'margin-top:10px;white-space:pre-wrap;font-size:12px;color:#4b5563;');
    panel.appendChild(detail);

    const controls = doc.createElement('div');
    controls.setAttribute('style', 'margin-top:12px;display:flex;justify-content:flex-end;gap:8px;');

    const bgBtn = doc.createElement('button');
    bgBtn.textContent = 'Run in Background';
    bgBtn.setAttribute(
      'style',
      'padding:5px 10px;border:1px solid #9aa0a6;background:#f3f4f6;color:#111827;border-radius:6px;cursor:pointer;'
    );
    bgBtn.addEventListener('click', () => {
      this.overlayDismissed = true;
      this.closeProgressWindow();
    });
    controls.appendChild(bgBtn);

    const cancelBtn = doc.createElement('button');
    cancelBtn.textContent = 'Cancel Sync';
    cancelBtn.setAttribute(
      'style',
      'padding:5px 10px;border:1px solid #b91c1c;background:#dc2626;color:#ffffff;border-radius:6px;cursor:pointer;'
    );
    cancelBtn.addEventListener('click', () => {
      void this.requestSyncStop();
    });
    controls.appendChild(cancelBtn);

    const closeBtn = doc.createElement('button');
    closeBtn.textContent = 'Close';
    closeBtn.setAttribute(
      'style',
      'display:none;padding:5px 10px;border:1px solid #9aa0a6;background:#f9fafb;color:#111827;border-radius:6px;cursor:pointer;'
    );
    closeBtn.addEventListener('click', () => {
      this.closeProgressWindow();
    });
    controls.appendChild(closeBtn);
    panel.appendChild(controls);

    root.appendChild(panel);
    (doc.body || doc.documentElement).appendChild(root);

    this.progressWindow = { root, message, bar, percent, detail, bgBtn, cancelBtn, closeBtn, closeTimer: null };
    this.setProgressWindowTerminalState(false);
    return this.progressWindow;
  },

  closeProgressWindow() {
    if (this.progressWindow) {
      try {
        if (this.progressWindow.closeTimer) {
          clearTimeout(this.progressWindow.closeTimer);
        }
        const { root } = this.progressWindow;
        if (root && root.parentNode) {
          root.parentNode.removeChild(root);
        }
      } catch (_err) {
        // Ignore close errors during shutdown or window changes
      }
    }
    this.progressWindow = null;
  },

  updateProgressWindow(percent, message) {
    if (!this.progressWindow) {
      return;
    }
    const pct = Math.max(0, Math.min(100, Number(percent || 0)));
    this.progressWindow.bar.style.width = `${pct}%`;
    this.progressWindow.percent.textContent = `${Math.round(pct)}%`;
    if (message) {
      this.progressWindow.message.textContent = String(message);
    }
  },

  addProgressDetail(text, isError = false) {
    if (!this.progressWindow || !text) {
      return;
    }
    this.progressWindow.detail.textContent = String(text);
    this.progressWindow.detail.style.color = isError ? '#b91c1c' : '#4b5563';
  },

  markProgressError() {
    if (!this.progressWindow) {
      return;
    }
    this.progressWindow.bar.style.background = '#dc2626';
  },

  startProgressCloseTimer(ms) {
    if (!this.progressWindow) {
      return;
    }
    if (this.progressWindow.closeTimer) {
      clearTimeout(this.progressWindow.closeTimer);
    }
    this.progressWindow.closeTimer = setTimeout(() => this.closeProgressWindow(), ms);
  },

  async requestSyncStop() {
    try {
      const req = await this.postJSON('/api/sync/stop', {});
      const payload = this.parseResponseJSON(req);
      const msg = String(payload.progress_message || 'Cancellation requested.');
      if (!this.overlayDismissed) {
        this.updateProgressWindow(Number(payload.progress_percent || 0), 'Cancelling sync...');
        this.markProgressError();
        this.addProgressDetail(msg, true);
      }
      this.log('Sync cancel requested');
    } catch (err) {
      const message = String(err && err.message ? err.message : err);
      if (!this.overlayDismissed) {
        this.addProgressDetail(`Cancel failed: ${message}`, true);
      }
      this.alert('RAG Sync', `Cancel failed: ${message}`);
      this.log(`Sync cancel failed: ${message}`);
    }
  },

  buildAuthHeaders() {
    const headers = {
      'Content-Type': 'application/json',
    };
    const token = this.getBearerToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    return headers;
  },

  async postJSON(path, payload) {
    const url = this.getBackendURL() + path;
    const headers = this.buildAuthHeaders();

    const req = await Zotero.HTTP.request('POST', url, {
      body: JSON.stringify(payload || {}),
      headers,
      timeout: 60000,
    });

    if (req.status < 200 || req.status >= 300) {
      throw new Error(`HTTP ${req.status} calling ${path}: ${req.responseText || 'no response body'}`);
    }
    return req;
  },

  async getJSON(path) {
    const url = this.getBackendURL() + path;
    const req = await Zotero.HTTP.request('GET', url, {
      headers: this.buildAuthHeaders(),
      timeout: 60000,
    });

    if (req.status < 200 || req.status >= 300) {
      throw new Error(`HTTP ${req.status} calling ${path}: ${req.responseText || 'no response body'}`);
    }
    return this.parseResponseJSON(req);
  },

  formatEpochSeconds(value) {
    if (!value) {
      return 'n/a';
    }
    try {
      return new Date(value * 1000).toLocaleString();
    } catch (_err) {
      return String(value);
    }
  },

  setLastSync(status, message, finishedAt) {
    this.lastSyncStatus = String(status || 'unknown');
    this.lastSyncMessage = String(message || '');
    this.lastSyncFinishedAt = finishedAt || null;
  },

  summarizeSyncResult(result) {
    if (!result || typeof result !== 'object') {
      return 'Sync completed.';
    }
    const total = Number(result.pdfs_total || 0);
    const matched = Number(result.pdfs_with_metadata || 0);
    const unmatched = Number(result.pdfs_unmatched || 0);
    let summary = `Sync complete: ${total} PDFs scanned, ${matched} with metadata, ${unmatched} unmatched.`;
    const sample = Array.isArray(result.unmatched_sample) ? result.unmatched_sample.slice(0, 5) : [];
    if (sample.length) {
      summary += ` Unmatched sample: ${sample.map((x) => String(x).split(/[\\\\/]/).pop()).join(', ')}`;
    }
    if (result.ingest_ran && result.ingest_summary) {
      const ingest = result.ingest_summary || {};
      const ingested = Number(ingest.ingested_articles || 0);
      const chunks = Number(ingest.total_chunks || 0);
      const refs = Number(ingest.total_references || 0);
      const failed = Array.isArray(ingest.failed_pdfs) ? ingest.failed_pdfs.length : 0;
      summary += ` Ingest: ${ingested} articles, ${chunks} chunks, ${refs} references, ${failed} failed PDFs.`;
    }
    return summary;
  },

  async syncNow() {
    if (this.syncInProgress) {
      this.alert('RAG Sync', 'Sync is already running.');
      return;
    }
    if (this.isPaused()) {
      this.alert('RAG Sync', 'RAG Sync is paused. Use Tools > RAG Sync > Pause/Resume to resume.');
      return;
    }

    this.syncInProgress = true;
    this.updateMenuState();

    const pw = this.openProgressWindow('Sync in progress...');
    this.updateProgressWindow(5, 'Submitting sync request');
    let backgroundMode = false;

    try {
      const startReq = await this.postJSON('/api/sync', {
        source_mode: this.getSourceMode(),
        source_dir: this.getSourceDir(),
        run_ingest: true,
        ingest_skip_existing: true,
      });
      const startPayload = this.parseResponseJSON(startReq);
      const requestID = startPayload.request_id ? String(startPayload.request_id) : null;
      this.updateProgressWindow(
        Math.max(10, Number(startPayload.progress_percent || 10)),
        requestID ? `Sync job started (${requestID})` : 'Sync job started'
      );
      if (startPayload.progress_message) {
        this.addProgressDetail(startPayload.progress_message);
      }

      const startedAt = Date.now();
      let terminalStatus = null;
      while (Date.now() - startedAt < this.syncPollTimeoutMS) {
        const status = await this.getJSON('/api/sync/status');
        const pct = Number(status.progress_percent || 0);
        const lifecycle = String(status.lifecycle_state || status.status || 'working');
        const msg = String(status.progress_message || lifecycle || 'Working...');
        if (!this.overlayDismissed) {
          this.updateProgressWindow(pct, msg);
        }

        if (
          lifecycle === 'running' ||
          lifecycle === 'cancelling'
        ) {
          await this.sleep(this.syncPollIntervalMS);
          continue;
        }

        terminalStatus = status;
        break;
      }

      if (!terminalStatus) {
        // Long sync/ingest runs can exceed client-side polling timeout.
        // Treat this as background continuation (not a failure) if backend is still running.
        let liveStatus = null;
        try {
          liveStatus = await this.getJSON('/api/sync/status');
        } catch (_err) {
          liveStatus = null;
        }
        const liveLifecycle = String(liveStatus && (liveStatus.lifecycle_state || liveStatus.status) || '');
        if (liveStatus && (liveLifecycle === 'running' || liveLifecycle === 'cancelling')) {
          const pct = Number(liveStatus.progress_percent || 0);
          const message = String(
            liveStatus.progress_message ||
            'Sync is still running in the background. Use Show Diagnostics to check progress.'
          );
          backgroundMode = true;
          this.syncInProgress = true;
          this.updateMenuState();
          if (!this.overlayDismissed) {
            this.updateProgressWindow(pct, 'Sync continues in background');
            this.addProgressDetail(message);
            this.startProgressCloseTimer(5000);
          }
          this.setLastSync('running', message, null);
          this.log(`Sync still running after polling timeout: ${message}`);
        }
        if (!backgroundMode) {
          throw new Error('Timed out waiting for /api/sync/status to reach terminal state.');
        }
      }

      while (backgroundMode && !terminalStatus) {
        const status = await this.getJSON('/api/sync/status');
        const pct = Number(status.progress_percent || 0);
        const lifecycle = String(status.lifecycle_state || status.status || 'working');
        const msg = String(status.progress_message || lifecycle || 'Working...');
        if (!this.overlayDismissed) {
          this.updateProgressWindow(pct, msg);
        }
        if (
          status.status === 'completed' ||
          status.status === 'failed' ||
          status.status === 'cancelled' ||
          status.status === 'idle'
        ) {
          terminalStatus = status;
          break;
        }
        await this.sleep(this.syncPollIntervalMS);
      }

      if (terminalStatus.status === 'completed' || terminalStatus.status === 'idle') {
        const summary = this.summarizeSyncResult(terminalStatus.result);
        if (!this.overlayDismissed) {
          this.updateProgressWindow(100, 'Sync completed');
          this.addProgressDetail(summary);
          this.setProgressWindowTerminalState(true);
          this.startProgressCloseTimer(6000);
        }
        this.setLastSync('completed', summary, terminalStatus.finished_at);
        this.log(summary);
      } else if (terminalStatus.status === 'cancelled') {
        const message = String(terminalStatus.progress_message || 'Sync cancelled.');
        if (!this.overlayDismissed) {
          this.updateProgressWindow(terminalStatus.progress_percent || 0, 'Sync cancelled');
          this.markProgressError();
          this.addProgressDetail(message, true);
          this.setProgressWindowTerminalState(true);
          this.startProgressCloseTimer(8000);
        }
        this.setLastSync('cancelled', message, terminalStatus.finished_at);
        this.alert('RAG Sync Cancelled', message);
      } else {
        const message = String(terminalStatus.error || terminalStatus.progress_message || 'Sync failed.');
        if (!this.overlayDismissed) {
          this.updateProgressWindow(terminalStatus.progress_percent || 0, 'Sync failed');
          this.markProgressError();
          this.addProgressDetail(message, true);
          this.setProgressWindowTerminalState(true);
          this.startProgressCloseTimer(10000);
        }
        this.setLastSync('failed', message, terminalStatus.finished_at);
        this.alert('RAG Sync Error', message);
        this.log(`Sync request failed: ${message}`);
      }
    } catch (err) {
      const message = String(err && err.message ? err.message : err);
      this.updateProgressWindow(0, 'Sync failed');
      this.markProgressError();
      this.addProgressDetail(message, true);
      this.setProgressWindowTerminalState(true);
      this.startProgressCloseTimer(8000);
      this.alert('RAG Sync Error', message);
      this.setLastSync('failed', message, null);
      this.log(`Sync request failed: ${message}`);
    } finally {
      this.syncInProgress = false;
      this.updateMenuState();
    }
  },

  retryFailed() {
    // Rapid v1 uses the same action as Sync Now until failed-item tracking is added.
    return this.syncNow();
  },

  togglePause() {
    const paused = !this.isPaused();
    this.setBoolPref(this.prefPaused, paused);
    this.alert('RAG Sync', paused ? 'RAG Sync paused.' : 'RAG Sync resumed.');
    this.log(paused ? 'paused' : 'resumed');
  },

  showDiagnostics() {
    const lines = [
      `Plugin: ${this.id || 'unknown'} v${this.version || 'unknown'}`,
      `Backend URL: ${this.getBackendURL()}`,
      `Source mode: ${this.getSourceMode()}`,
      `Source dir: ${this.getSourceDir()}`,
      `Bearer token set: ${this.getBearerToken() ? 'yes' : 'no'}`,
      `Paused: ${this.isPaused() ? 'yes' : 'no'}`,
      `Sync running: ${this.syncInProgress ? 'yes' : 'no'}`,
      `Last sync status: ${this.lastSyncStatus}`,
      `Last sync finished: ${this.formatEpochSeconds(this.lastSyncFinishedAt)}`,
      `Last sync message: ${this.lastSyncMessage}`,
    ];
    this.alert('RAG Sync Diagnostics', lines.join('\n'));
  },

  getSelectedItems() {
    const win = this.getMainWindow();
    if (!win || !win.ZoteroPane || typeof win.ZoteroPane.getSelectedItems !== 'function') {
      return [];
    }
    try {
      const items = win.ZoteroPane.getSelectedItems() || [];
      return Array.isArray(items) ? items : [];
    } catch (_err) {
      return [];
    }
  },

  isPDFItem(item) {
    return !!(
      item &&
      item.isAttachment &&
      item.isAttachment() &&
      String(item.attachmentContentType || '').toLowerCase() === 'application/pdf'
    );
  },

  isLinkedAttachment(item) {
    if (!this.isPDFItem(item)) {
      return false;
    }
    const linkedMode = Zotero.Attachments && typeof Zotero.Attachments.LINK_MODE_LINKED_FILE !== 'undefined'
      ? Zotero.Attachments.LINK_MODE_LINKED_FILE
      : 2;
    return Number(item.attachmentLinkMode) === Number(linkedMode);
  },

  collectLinkedPDFAttachments(items) {
    const candidates = [];
    const seen = new Set();
    for (const item of items || []) {
      if (!item) {
        continue;
      }
      if (this.isLinkedAttachment(item)) {
        if (!seen.has(item.id)) {
          seen.add(item.id);
          candidates.push(item);
        }
        continue;
      }
      if (!(item.isAttachment && item.isAttachment()) && item.getAttachments) {
        for (const childID of item.getAttachments() || []) {
          if (seen.has(childID)) {
            continue;
          }
          const child = Zotero.Items.get(childID);
          if (this.isLinkedAttachment(child)) {
            seen.add(childID);
            candidates.push(child);
          }
        }
      }
    }
    return candidates;
  },

  async normalizeLinkedAttachmentsToStored() {
    const selectedItems = this.getSelectedItems();
    if (!selectedItems.length) {
      this.alert('RAG Sync', 'Select one or more items or linked PDF attachments first.');
      return;
    }

    const attachments = this.collectLinkedPDFAttachments(selectedItems);
    if (!attachments.length) {
      this.alert('RAG Sync', 'No linked PDF attachments were found in the current selection.');
      return;
    }

    const prompt = [
      `Convert ${attachments.length} linked PDF attachment(s) into Zotero-managed stored attachments?`,
      '',
      'This keeps the same parent item and makes the files eligible for Zotero file sync/WebDAV.',
      'The original linked attachment will be deleted only after the stored copy is created successfully.'
    ].join('\n');
    const confirmed = Services.prompt.confirm(
      this.getMainWindow(),
      'RAG Sync',
      prompt
    );
    if (!confirmed) {
      return;
    }

    this.openProgressWindow('Normalizing linked PDF attachments...');
    this.updateProgressWindow(0, `Preparing ${attachments.length} attachment(s)`);
    this.addProgressDetail('Converting linked attachments into Zotero-managed stored attachments.');

    const summary = {
      selected: selectedItems.length,
      candidates: attachments.length,
      converted: 0,
      skipped: 0,
      failed: 0,
    };
    const failures = [];

    for (let index = 0; index < attachments.length; index++) {
      const attachment = attachments[index];
      const pct = ((index + 1) / attachments.length) * 100;
      const title = attachment.getField ? attachment.getField('title') : attachment.key;
      this.updateProgressWindow(pct, `Converting ${index + 1}/${attachments.length}: ${title || attachment.key}`);
      try {
        const filePath = attachment.getFilePath ? attachment.getFilePath() : '';
        if (!filePath) {
          summary.skipped++;
          failures.push(`Skipped ${attachment.key}: no local file path`);
          continue;
        }

        const parentItemID = attachment.parentItemID;
        if (!parentItemID) {
          summary.skipped++;
          failures.push(`Skipped ${attachment.key}: attachment has no parent item`);
          continue;
        }

        const options = {
          file: filePath,
          parentItemID,
          title: title || undefined,
          contentType: 'application/pdf',
        };
        const storedAttachment = await Zotero.Attachments.importFromFile(options);
        if (!storedAttachment || !storedAttachment.id) {
          throw new Error('importFromFile returned no stored attachment');
        }

        try {
          await attachment.eraseTx();
        } catch (eraseErr) {
          throw new Error(`stored copy created (${storedAttachment.key}) but linked attachment delete failed: ${eraseErr}`);
        }

        summary.converted++;
      } catch (err) {
        summary.failed++;
        Zotero.logError(err);
        failures.push(`Failed ${attachment.key}: ${String(err)}`);
      }
    }

    const lines = [
      `Selected items: ${summary.selected}`,
      `Linked PDF candidates: ${summary.candidates}`,
      `Converted to stored attachments: ${summary.converted}`,
      `Skipped: ${summary.skipped}`,
      `Failed: ${summary.failed}`,
    ];
    if (failures.length) {
      lines.push('');
      lines.push('Sample issues:');
      lines.push(...failures.slice(0, 10));
    }

    if (summary.failed) {
      this.markProgressError();
    }
    this.updateProgressWindow(100, 'Attachment normalization complete');
    this.addProgressDetail(lines.join('\n'), summary.failed > 0);
    this.setProgressWindowTerminalState(true);
    this.startProgressCloseTimer(12000);
    this.alert('RAG Sync', lines.join('\n'));
  },

  init({ id, version, rootURI }) {
    if (this.initialized) {
      return;
    }

    this.id = id;
    this.version = version;
    this.rootURI = rootURI;
    this.injectToolsMenu();
    this.updateMenuState();

    this.initialized = true;
    this.log('startup');
  },

  injectToolsMenu() {
    const win = Zotero.getMainWindow && Zotero.getMainWindow();
    if (!win || !win.document) {
      this.log('main window not available');
      return;
    }

    const doc = win.document;
    const toolsPopup = doc.getElementById('menu_ToolsPopup');
    if (!toolsPopup) {
      this.log('tools menu popup not found');
      return;
    }

    if (doc.getElementById(this.injectedMenuID)) {
      return;
    }

    const menu = doc.createXULElement('menu');
    menu.id = this.injectedMenuID;
    menu.setAttribute('label', 'RAG Sync');

    const popup = doc.createXULElement('menupopup');
    menu.appendChild(popup);

    const makeItem = (id, label, onCommand) => {
      const item = doc.createXULElement('menuitem');
      item.id = id;
      item.setAttribute('label', label);
      item.addEventListener('command', onCommand);
      return item;
    };

    popup.appendChild(
      makeItem('rag-sync-menu-sync-now', this.getSyncNowLabel(), () => this.syncNow())
    );
    popup.appendChild(
      makeItem('rag-sync-menu-cancel-sync', this.getCancelSyncLabel(), () => void this.requestSyncStop())
    );
    popup.appendChild(
      makeItem('rag-sync-menu-retry-failed', 'Retry Failed', () => this.retryFailed())
    );
    popup.appendChild(
      makeItem('rag-sync-menu-pause-resume', 'Pause/Resume', () => this.togglePause())
    );
    popup.appendChild(
      makeItem('rag-sync-menu-show-diagnostics', 'Show Diagnostics', () => this.showDiagnostics())
    );
    popup.appendChild(
      makeItem(
        'rag-sync-menu-normalize-linked',
        this.getNormalizeAttachmentsLabel(),
        () => void this.normalizeLinkedAttachmentsToStored()
      )
    );

    const addonsMenu = doc.getElementById('menu_addons');
    if (addonsMenu && addonsMenu.parentNode === toolsPopup) {
      toolsPopup.insertBefore(menu, addonsMenu.nextSibling);
    } else {
      toolsPopup.appendChild(menu);
    }

    this.updateMenuState();
  },

  shutdown() {
    const win = Zotero.getMainWindow && Zotero.getMainWindow();
    if (win && win.document) {
      const menu = win.document.getElementById(this.injectedMenuID);
      if (menu && menu.parentNode) {
        menu.parentNode.removeChild(menu);
      }
    }
    this.closeProgressWindow();

    this.initialized = false;
    this.id = null;
    this.version = null;
    this.rootURI = null;
    this.syncInProgress = false;
  },
};
