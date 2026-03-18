/* eslint-disable no-undef */

var RAGSync;

function install(_data, _reason) {}

async function startup({ id, version, rootURI, resourceURI }) {
  await Zotero.initializationPromise;

  if (!rootURI && resourceURI) {
    rootURI = resourceURI.spec;
  }

  Services.scriptloader.loadSubScript(rootURI + 'content/scripts/ragsync.js');
  RAGSync.init({ id, version, rootURI });
}

function shutdown(_data, reason) {
  if (reason === APP_SHUTDOWN) {
    return;
  }

  if (RAGSync && typeof RAGSync.shutdown === 'function') {
    RAGSync.shutdown();
  }
  RAGSync = undefined;
}

function uninstall(_data, _reason) {}
