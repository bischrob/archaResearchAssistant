/* eslint-disable no-undef */

var RAGSync = {
  initialized: false,
  injectedMenuID: 'rag-sync-tools-menu',
  syncInProgress: false,
  progressWindow: null,
  id: null,
  version: null,
  rootURI: null,
  prefBackendURL: 'extensions.zotero-rag-sync.backendURL',
  prefBearerToken: 'extensions.zotero-rag-sync.bearerToken',
  prefPaused: 'extensions.zotero-rag-sync.paused',

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

  isPaused() {
    return this.getBoolPref(this.prefPaused, false);
  },

  alert(title, msg) {
    Zotero.alert(this.getMainWindow(), title, msg);
  },

  getSyncNowLabel() {
    return this.syncInProgress ? 'Sync Now (Running...)' : 'Sync Now';
  },

  updateMenuState() {
    const win = this.getMainWindow();
    if (!win || !win.document) {
      return;
    }
    const syncItem = win.document.getElementById('rag-sync-menu-sync-now');
    if (syncItem) {
      syncItem.setAttribute('label', this.getSyncNowLabel());
      syncItem.setAttribute('disabled', this.syncInProgress ? 'true' : 'false');
    }
  },

  openProgressWindow(phaseText) {
    this.closeProgressWindow();
    const pw = new Zotero.ProgressWindow({ window: this.getMainWindow(), closeOnClick: true });
    pw.changeHeadline('RAG Sync', null, phaseText);
    pw.show();
    this.progressWindow = pw;
    return pw;
  },

  closeProgressWindow() {
    if (this.progressWindow) {
      try {
        this.progressWindow.close();
      } catch (_err) {
        // Ignore close errors during shutdown or window changes
      }
    }
    this.progressWindow = null;
  },

  async postJSON(path, payload) {
    const url = this.getBackendURL() + path;
    const headers = {
      'Content-Type': 'application/json',
    };
    const token = this.getBearerToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

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

    const pw = this.openProgressWindow('Sync request in progress...');
    const progress = new pw.ItemProgress('refresh', 'Sending /api/sync');
    progress.setProgress(40);

    try {
      const response = await this.postJSON('/api/sync', {});
      progress.setText(`Sync accepted (HTTP ${response.status})`);
      progress.setProgress(100);
      pw.addDescription(`Backend accepted sync request at ${this.getBackendURL()}/api/sync`);
      pw.startCloseTimer(2500);
      this.log(`Sync request succeeded with HTTP ${response.status}`);
    } catch (err) {
      const message = String(err && err.message ? err.message : err);
      progress.setText('Sync failed');
      progress.setError();
      pw.addDescription(message);
      pw.startCloseTimer(8000);
      this.alert('RAG Sync Error', message);
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
      `Bearer token set: ${this.getBearerToken() ? 'yes' : 'no'}`,
      `Paused: ${this.isPaused() ? 'yes' : 'no'}`,
      `Sync running: ${this.syncInProgress ? 'yes' : 'no'}`,
    ];
    this.alert('RAG Sync Diagnostics', lines.join('\n'));
  },

  init({ id, version, rootURI }) {
    if (this.initialized) {
      return;
    }

    this.id = id;
    this.version = version;
    this.rootURI = rootURI;
    this.injectToolsMenu();

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
      makeItem('rag-sync-menu-retry-failed', 'Retry Failed', () => this.retryFailed())
    );
    popup.appendChild(
      makeItem('rag-sync-menu-pause-resume', 'Pause/Resume', () => this.togglePause())
    );
    popup.appendChild(
      makeItem('rag-sync-menu-show-diagnostics', 'Show Diagnostics', () => this.showDiagnostics())
    );

    const addonsMenu = doc.getElementById('menu_addons');
    if (addonsMenu && addonsMenu.parentNode === toolsPopup) {
      toolsPopup.insertBefore(menu, addonsMenu.nextSibling);
    } else {
      toolsPopup.appendChild(menu);
    }
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
