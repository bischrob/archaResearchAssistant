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
  prefExternalBridgeEnabled: 'extensions.zotero-rag-sync.externalBridgeEnabled',
  prefExternalBridgeToken: 'extensions.zotero-rag-sync.externalBridgeToken',
  syncPollIntervalMS: 700,
  syncPollTimeoutMS: 60 * 60 * 1000,
  overlayDismissed: false,
  externalBridgePaths: {
    ping: '/rag-sync/bridge/ping',
    importMineruNote: '/rag-sync/bridge/import-mineru-note',
  },

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
    return this.getStringPref(this.prefBackendURL, 'http://127.0.0.1:8001').replace(/\/+$/, '');
  },

  getBearerToken() {
    return this.getStringPref(this.prefBearerToken, '');
  },

  isExternalBridgeEnabled() {
    return this.getBoolPref(this.prefExternalBridgeEnabled, false);
  },

  getExternalBridgeToken() {
    return this.getStringPref(this.prefExternalBridgeToken, '');
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

  getImportPDFURLLabel() {
    return 'Import PDF URL To Stored Attachment';
  },

  getExternalBridgeDiagnosticsLabel() {
    return 'Show External Note Bridge Diagnostics';
  },

  showExternalBridgeDiagnostics() {
    const lines = [
      `External note bridge enabled: ${this.isExternalBridgeEnabled() ? 'yes' : 'no'}`,
      `External note bridge token set: ${this.getExternalBridgeToken() ? 'yes' : 'no'}`,
      `External note bridge ping URL: http://127.0.0.1:23119${this.externalBridgePaths.ping}`,
      `External note bridge import URL: http://127.0.0.1:23119${this.externalBridgePaths.importMineruNote}`,
      'Scope: My Library attachments only',
    ];
    this.alert('RAG Sync External Note Bridge', lines.join('\n'));
  },

  registerConnectorEndpoint(path, handlerCtor) {
    if (!Zotero.Server || !Zotero.Server.Endpoints) {
      throw new Error('Zotero connector HTTP server is unavailable');
    }
    Zotero.Server.Endpoints[path] = handlerCtor;
  },

  unregisterConnectorEndpoint(path) {
    if (!Zotero.Server || !Zotero.Server.Endpoints) {
      return;
    }
    delete Zotero.Server.Endpoints[path];
  },

  parseConnectorJSON(postData) {
    const raw = typeof postData === 'string' ? postData.trim() : '';
    if (!raw) {
      return {};
    }
    return JSON.parse(raw);
  },

  escapeHTML(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },

  renderMineruBridgeNoteText(params) {
    const parentText = params.parentItemId ? String(params.parentItemId) : 'none';
    return [
      'LLM_FOR_ZOTERO_MINERU_NOTE_V1',
      `attachment_id=${params.attachmentId}`,
      `parent_item_id=${parentText}`,
      `parsed_at=${params.parsedAt}`,
      'mineru_version=pipeline',
      `content_hash=${params.contentHash}`,
      '',
      '---',
      '',
      params.mdContent,
    ].join('\n');
  },

  renderMineruBridgeNoteHtml(noteText) {
    return `<pre>${this.escapeHTML(noteText)}</pre>`;
  },

  hashMineruBridgeContent(mdContent) {
    let hash = 0x811c9dc5;
    for (let i = 0; i < mdContent.length; i++) {
      hash ^= mdContent.charCodeAt(i);
      hash = Math.imul(hash, 0x01000193);
    }
    return (hash >>> 0).toString(16).padStart(8, '0');
  },

  noteHtmlToText(noteHTML) {
    try {
      const parsed = new DOMParser().parseFromString(String(noteHTML || ''), 'text/html');
      return typeof parsed.body.textContent === 'string' ? parsed.body.textContent : String(noteHTML || '');
    } catch (_err) {
      return String(noteHTML || '');
    }
  },

  parseExistingMineruBridgeHeader(noteText) {
    const match = String(noteText || '').match(
      /LLM_FOR_ZOTERO_MINERU_NOTE_V1[\s\S]*?attachment_id=(\d+)[\s\S]*?parent_item_id=(\d+|none)[\s\S]*?content_hash=([a-f0-9]{8,64})/i
    );
    if (!match) {
      return null;
    }
    const attachmentId = Number(match[1]);
    const parentRaw = String(match[2] || '').trim().toLowerCase();
    const contentHash = String(match[3] || '').trim().toLowerCase();
    if (!Number.isFinite(attachmentId) || attachmentId <= 0) {
      return null;
    }
    return {
      attachmentId,
      parentItemId: parentRaw === 'none' ? null : Number(parentRaw) || null,
      contentHash,
    };
  },

  async findExistingMineruBridgeNote(attachmentID, parentItemID, libraryID) {
    let candidateIDs = [];
    if (parentItemID) {
      const parentItem = Zotero.Items.get(parentItemID);
      if (parentItem && parentItem.isRegularItem && parentItem.isRegularItem()) {
        candidateIDs = (parentItem.getNotes() || []).slice();
      }
    }

    if (!candidateIDs.length) {
      const search = new Zotero.Search({ libraryID });
      search.addCondition('itemType', 'is', 'note');
      search.addCondition('quicksearch-everything', 'contains', 'LLM_FOR_ZOTERO_MINERU_NOTE_V1');
      candidateIDs = await search.search();
    }

    let fallback = null;
    for (const noteID of candidateIDs || []) {
      const noteItem = Zotero.Items.get(noteID);
      if (!noteItem || !noteItem.isNote || !noteItem.isNote()) {
        continue;
      }
      const header = this.parseExistingMineruBridgeHeader(this.noteHtmlToText(noteItem.getNote()));
      if (!header || header.attachmentId !== attachmentID) {
        continue;
      }
      if ((header.parentItemId || null) === (parentItemID || null)) {
        return noteItem;
      }
      if (!fallback) {
        fallback = noteItem;
      }
    }
    return fallback;
  },

  async importExternalMineruNote(payload) {
    const attachmentKey = String(payload.attachment_key || '').trim().toUpperCase();
    const attachmentID = Number(payload.attachment_id || 0);
    const mdContent = String(payload.md_content || payload.note_markdown || '').trim();

    if (!mdContent) {
      throw new Error('md_content is required');
    }

    let attachment = null;
    if (attachmentKey) {
      attachment = Zotero.Items.getByLibraryAndKey(Zotero.Libraries.userLibraryID, attachmentKey);
    } else if (Number.isFinite(attachmentID) && attachmentID > 0) {
      attachment = Zotero.Items.get(attachmentID);
    }

    if (!attachment || !attachment.isAttachment || !attachment.isAttachment()) {
      throw new Error('Matching Zotero attachment not found');
    }
    if (attachment.libraryID !== Zotero.Libraries.userLibraryID) {
      throw new Error('Matching Zotero attachment not found in My Library');
    }

    const parentItemID = attachment.parentID && attachment.parentID > 0 ? attachment.parentID : null;
    const parsedAt = String(payload.parsed_at || new Date().toISOString());
    const contentHash = this.hashMineruBridgeContent(mdContent);
    const noteText = this.renderMineruBridgeNoteText({
      attachmentId: attachment.id,
      parentItemId: parentItemID,
      parsedAt,
      contentHash,
      mdContent,
    });
    const noteHTML = this.renderMineruBridgeNoteHtml(noteText);
    const existing = await this.findExistingMineruBridgeNote(attachment.id, parentItemID, attachment.libraryID);

    if (existing) {
      const header = this.parseExistingMineruBridgeHeader(this.noteHtmlToText(existing.getNote()));
      if (header && header.contentHash === contentHash) {
        return {
          status: 'unchanged',
          attachment_key: attachment.key,
          attachment_id: attachment.id,
          parent_item_id: parentItemID,
          note_item_id: existing.id,
        };
      }
      existing.setNote(noteHTML);
      await existing.saveTx();
      return {
        status: 'updated',
        attachment_key: attachment.key,
        attachment_id: attachment.id,
        parent_item_id: parentItemID,
        note_item_id: existing.id,
      };
    }

    const note = new Zotero.Item('note');
    note.libraryID = attachment.libraryID;
    if (parentItemID) {
      note.parentID = parentItemID;
    }
    note.setNote(noteHTML);
    const noteID = await note.saveTx();
    return {
      status: 'created',
      attachment_key: attachment.key,
      attachment_id: attachment.id,
      parent_item_id: parentItemID,
      note_item_id: noteID || note.id,
    };
  },

  registerExternalBridge() {
    const self = this;

    function PingEndpoint() {}
    PingEndpoint.prototype = {
      supportedMethods: ['GET'],
      init(_options) {
        return [200, 'application/json', JSON.stringify({
          ok: true,
          plugin: 'zotero-rag-sync',
          version: self.version || 'unknown',
          bridge_enabled: self.isExternalBridgeEnabled(),
          endpoint: self.externalBridgePaths.importMineruNote,
        })];
      },
    };

    function ImportMineruNoteEndpoint() {}
    ImportMineruNoteEndpoint.prototype = {
      supportedMethods: ['POST'],
      supportedDataTypes: ['application/json'],
      async init(options) {
        try {
          const result = await self.handleExternalBridgeImport(options);
          return [200, 'application/json', JSON.stringify(result)];
        } catch (err) {
          return [400, 'application/json', JSON.stringify({
            ok: false,
            error: String(err && err.message ? err.message : err),
          })];
        }
      },
    };

    this.registerConnectorEndpoint(this.externalBridgePaths.ping, PingEndpoint);
    this.registerConnectorEndpoint(this.externalBridgePaths.importMineruNote, ImportMineruNoteEndpoint);
  },

  unregisterExternalBridge() {
    this.unregisterConnectorEndpoint(this.externalBridgePaths.ping);
    this.unregisterConnectorEndpoint(this.externalBridgePaths.importMineruNote);
  },

  async handleExternalBridgeImport(options) {
    if (!this.isExternalBridgeEnabled()) {
      throw new Error('External bridge is disabled. Set extensions.zotero-rag-sync.externalBridgeEnabled=true');
    }

    const candidatePayloads = [
      options && options.data,
      options && options.body,
      options && options.postData,
      options && options.dataRaw,
    ];
    let payload = {};
    for (const candidate of candidatePayloads) {
      if (!candidate) {
        continue;
      }
      if (typeof candidate === 'string') {
        payload = this.parseConnectorJSON(candidate);
        break;
      }
      if (typeof TextDecoder !== 'undefined' && ArrayBuffer.isView(candidate)) {
        payload = this.parseConnectorJSON(new TextDecoder().decode(candidate));
        break;
      }
      if (typeof TextDecoder !== 'undefined' && candidate instanceof ArrayBuffer) {
        payload = this.parseConnectorJSON(new TextDecoder().decode(new Uint8Array(candidate)));
        break;
      }
      if (typeof candidate === 'object' && !Array.isArray(candidate)) {
        payload = candidate;
        break;
      }
    }
    const headers = (options && options.headers) || {};
    const headerToken = String(
      headers['X-RAG-Sync-Token'] ||
      headers['x-rag-sync-token'] ||
      headers.Authorization ||
      headers.authorization ||
      ''
    ).trim();
    const bearerMatch = headerToken.match(/^Bearer\s+(.+)$/i);
    const suppliedToken = String(
      payload.auth_token ||
      (bearerMatch ? bearerMatch[1] : headerToken) ||
      ''
    ).trim();
    const configuredToken = this.getExternalBridgeToken();
    if (!configuredToken) {
      throw new Error('External bridge token is not configured');
    }
    if (suppliedToken !== configuredToken) {
      throw new Error('Invalid external bridge token');
    }

    const result = await this.importExternalMineruNote(payload);
    return {
      ok: true,
      endpoint: this.externalBridgePaths.importMineruNote,
      ...result,
    };
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
      `External note bridge enabled: ${this.isExternalBridgeEnabled() ? 'yes' : 'no'}`,
      `External note bridge token set: ${this.getExternalBridgeToken() ? 'yes' : 'no'}`,
      `External note bridge ping URL: http://127.0.0.1:23119${this.externalBridgePaths.ping}`,
      `External note bridge import URL: http://127.0.0.1:23119${this.externalBridgePaths.importMineruNote}`,
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

  collectSelectedParentItems(items) {
    const parents = [];
    const seen = new Set();
    for (const item of items || []) {
      if (!item) {
        continue;
      }
      let candidate = null;
      if (item.isAttachment && item.isAttachment()) {
        if (item.parentItemID) {
          candidate = Zotero.Items.get(item.parentItemID);
        }
      } else if (!item.isRegularItem || item.isRegularItem()) {
        candidate = item;
      }
      if (candidate && candidate.id && !seen.has(candidate.id)) {
        seen.add(candidate.id);
        parents.push(candidate);
      }
    }
    return parents;
  },

  promptForPDFURL(defaultValue = '') {
    const input = { value: String(defaultValue || '') };
    const confirmed = Services.prompt.prompt(
      this.getMainWindow(),
      'RAG Sync',
      [
        'Enter a PDF URL to import as a Zotero-managed stored attachment.',
        '',
        'Stored attachments are eligible for Zotero file sync/WebDAV.',
      ].join('\n'),
      input,
      null,
      {}
    );
    if (!confirmed) {
      return null;
    }
    const value = String(input.value || '').trim();
    return value || null;
  },

  async importPDFURLToStoredAttachment() {
    const selectedItems = this.getSelectedItems();
    if (!selectedItems.length) {
      this.alert('RAG Sync', 'Select a Zotero item first. You can also select one of its child attachments.');
      return;
    }

    const parentItems = this.collectSelectedParentItems(selectedItems);
    if (parentItems.length !== 1) {
      this.alert(
        'RAG Sync',
        'Select exactly one parent item (or one child attachment under that item) before importing a PDF URL.'
      );
      return;
    }

    const parentItem = parentItems[0];
    const url = this.promptForPDFURL('https://');
    if (!url) {
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      this.alert('RAG Sync', 'PDF URL must start with http:// or https://');
      return;
    }

    this.openProgressWindow('Importing PDF URL as stored attachment...');
    this.updateProgressWindow(10, 'Creating Zotero-managed stored attachment');
    this.addProgressDetail(`Parent item: ${parentItem.getField ? parentItem.getField('title') : parentItem.key}\nURL: ${url}`);

    try {
      const attachment = await Zotero.Attachments.importFromURL({
        url,
        parentItemID: parentItem.id,
        title: 'Full Text PDF',
        contentType: 'application/pdf',
      });
      const attachmentKey = attachment && attachment.key ? attachment.key : 'unknown';
      const attachmentPath = attachment && attachment.attachmentPath ? attachment.attachmentPath : 'storage attachment';
      const message = [
        'Imported PDF as Zotero-managed stored attachment.',
        `Parent item: ${parentItem.getField ? parentItem.getField('title') : parentItem.key}`,
        `Attachment key: ${attachmentKey}`,
        `Attachment path: ${attachmentPath}`,
        'This attachment is eligible for Zotero file sync/WebDAV.',
      ].join('\n');
      this.updateProgressWindow(100, 'PDF import complete');
      this.addProgressDetail(message);
      this.setProgressWindowTerminalState(true);
      this.startProgressCloseTimer(10000);
      this.alert('RAG Sync', message);
    } catch (err) {
      const message = String(err && err.message ? err.message : err);
      this.updateProgressWindow(100, 'PDF import failed');
      this.markProgressError();
      this.addProgressDetail(message, true);
      this.setProgressWindowTerminalState(true);
      this.startProgressCloseTimer(12000);
      this.alert('RAG Sync Error', message);
      this.log(`PDF URL import failed: ${message}`);
    }
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
    this.registerExternalBridge();
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
        'rag-sync-menu-show-external-bridge',
        this.getExternalBridgeDiagnosticsLabel(),
        () => this.showExternalBridgeDiagnostics()
      )
    );
    popup.appendChild(
      makeItem(
        'rag-sync-menu-import-pdf-url',
        this.getImportPDFURLLabel(),
        () => void this.importPDFURLToStoredAttachment()
      )
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
    this.unregisterExternalBridge();

    this.initialized = false;
    this.id = null;
    this.version = null;
    this.rootURI = null;
    this.syncInProgress = false;
  },
};
