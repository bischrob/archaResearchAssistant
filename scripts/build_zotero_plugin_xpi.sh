#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_DIR="${ROOT_DIR}/plugins/zotero-rag-sync"
OUTPUT_XPI="${OUTPUT_XPI:-/tmp/rag-sync@rjbischo.local.xpi}"
EXPECTED_ID="rag-sync@rjbischo.local"
INSTALL_AFTER_BUILD="${INSTALL_AFTER_BUILD:-1}"
INSTALL_SCRIPT="${ROOT_DIR}/scripts/install_zotero_plugin_windows.sh"

ALLOWLIST=(
  "manifest.json"
  "bootstrap.js"
  "prefs.js"
  "content/scripts/ragsync.js"
)

die() {
  echo "Error: $*" >&2
  exit 1
}

stage_root=""

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

check_manifest() {
  node - "${PLUGIN_DIR}/manifest.json" "${EXPECTED_ID}" <<'NODE'
const fs = require('fs');
const [manifestPath, expectedId] = process.argv.slice(2);
const raw = fs.readFileSync(manifestPath, 'utf8');
let manifest;
try {
  manifest = JSON.parse(raw);
} catch (err) {
  throw new Error(`manifest.json is not valid JSON: ${err.message}`);
}

const problems = [];
if (manifest.manifest_version !== 2) problems.push(`manifest_version=${manifest.manifest_version}`);
if (!manifest.applications || !manifest.applications.zotero) problems.push('missing applications.zotero');
if (!manifest.applications?.zotero?.id) problems.push('missing applications.zotero.id');
if (!manifest.applications?.zotero?.update_url) problems.push('missing applications.zotero.update_url');
if (manifest.applications?.zotero?.id !== expectedId) {
  problems.push(`unexpected addon id ${manifest.applications?.zotero?.id}`);
}
if (manifest.applications?.zotero?.update_url &&
    !/^https?:\/\/\S+/i.test(String(manifest.applications.zotero.update_url))) {
  problems.push(`invalid applications.zotero.update_url ${manifest.applications.zotero.update_url}`);
}
for (const field of ['name', 'version', 'description']) {
  if (!String(manifest[field] || '').trim()) problems.push(`missing ${field}`);
}
if (problems.length) {
  throw new Error(`manifest sanity checks failed: ${problems.join(', ')}`);
}
NODE
}

check_js_syntax() {
  node --check "${PLUGIN_DIR}/bootstrap.js"
  node --check "${PLUGIN_DIR}/prefs.js"
  node --check "${PLUGIN_DIR}/content/scripts/ragsync.js"
}

stage_tree() {
  local stage_root="$1"
  mkdir -p "${stage_root}"

  for rel in "${ALLOWLIST[@]}"; do
    local src="${PLUGIN_DIR}/${rel}"
    local dst="${stage_root}/${rel}"
    [[ -f "${src}" ]] || die "Missing required plugin file: ${src}"
    mkdir -p "$(dirname "${dst}")"
    cp -p "${src}" "${dst}"
  done

  find "${stage_root}" -type f -exec chmod 0644 {} +
  find "${stage_root}" -type d -exec chmod 0755 {} +
  find "${stage_root}" -exec touch -t 198001010000.00 {} +
}

build_xpi() {
  local stage_root="$1"
  rm -f "${OUTPUT_XPI}"
  (
    cd "${stage_root}"
    zip -X -q -D "${OUTPUT_XPI}" "${ALLOWLIST[@]}"
  )
}

verify_xpi() {
  local actual
  mapfile -t actual < <(unzip -Z1 "${OUTPUT_XPI}")
  if [[ "${#actual[@]}" -ne "${#ALLOWLIST[@]}" ]]; then
    printf 'Archive file count mismatch:\nexpected (%d):\n' "${#ALLOWLIST[@]}" >&2
    printf '  %s\n' "${ALLOWLIST[@]}" >&2
    printf 'actual (%d):\n' "${#actual[@]}" >&2
    printf '  %s\n' "${actual[@]}" >&2
    exit 1
  fi
  for i in "${!ALLOWLIST[@]}"; do
    if [[ "${actual[$i]}" != "${ALLOWLIST[$i]}" ]]; then
      printf 'Archive entry mismatch at index %d:\nexpected: %s\nactual:   %s\n' \
        "$i" "${ALLOWLIST[$i]}" "${actual[$i]}" >&2
      exit 1
    fi
  done
}

main() {
  require_cmd node
  require_cmd zip
  require_cmd unzip
  require_cmd cp
  require_cmd touch

  [[ -d "${PLUGIN_DIR}" ]] || die "Plugin directory not found: ${PLUGIN_DIR}"
  [[ -f "${PLUGIN_DIR}/manifest.json" ]] || die "Missing manifest: ${PLUGIN_DIR}/manifest.json"

  check_manifest
  check_js_syntax

  stage_root="$(mktemp -d)"
  trap cleanup EXIT

  stage_tree "${stage_root}"
  build_xpi "${stage_root}"
  verify_xpi

  printf 'Built %s\n' "${OUTPUT_XPI}"

  if [[ "${INSTALL_AFTER_BUILD}" == "1" ]]; then
    if [[ ! -x "${INSTALL_SCRIPT}" ]]; then
      die "Install script not executable: ${INSTALL_SCRIPT}"
    fi
    SOURCE_XPI="${OUTPUT_XPI}" "${INSTALL_SCRIPT}"
    printf 'Installed %s via %s\n' "${OUTPUT_XPI}" "${INSTALL_SCRIPT}"
  fi
}

cleanup() {
  if [[ -n "${stage_root:-}" && -d "${stage_root}" ]]; then
    rm -rf "${stage_root}"
  fi
}

main "$@"
