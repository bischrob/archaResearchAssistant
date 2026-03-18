#!/usr/bin/env bash
set -euo pipefail

SOURCE_XPI="${SOURCE_XPI:-/tmp/rag-sync@rjbischo.local.xpi}"
EXPECTED_ID="rag-sync@rjbischo.local"
OBSOLETE_ID="rag-sync@local.xpi"

die() {
  echo "Error: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

normalize_path() {
  local path="$1"
  if [[ "${path}" =~ ^[A-Za-z]:\\ || "${path}" == *\\* ]] && command -v wslpath >/dev/null 2>&1; then
    wslpath -u "${path}"
  else
    printf '%s\n' "${path}"
  fi
}

timestamp_utc() {
  date -u +%Y%m%dT%H%M%SZ
}

resolve_profile_base() {
  if [[ -n "${ZOTERO_PROFILE_DIR:-}" ]]; then
    normalize_path "${ZOTERO_PROFILE_DIR}"
    return
  fi

  local candidates=()
  if [[ -n "${ZOTERO_PROFILE_BASE:-}" ]]; then
    candidates+=("${ZOTERO_PROFILE_BASE}")
  fi
  if [[ -n "${APPDATA:-}" ]]; then
    candidates+=("${APPDATA}/Zotero/Zotero")
  fi
  if [[ -n "${LOCALAPPDATA:-}" ]]; then
    candidates+=("${LOCALAPPDATA}/Zotero/Zotero")
  fi
  if [[ -n "${HOME:-}" ]]; then
    candidates+=("${HOME}/AppData/Roaming/Zotero/Zotero")
  fi
  # WSL fallback: scan typical Windows user profile roots.
  local drive_root user_dir
  for drive_root in /mnt/[c-z]/Users; do
    [[ -d "${drive_root}" ]] || continue
    for user_dir in "${drive_root}"/*; do
      [[ -d "${user_dir}" ]] || continue
      candidates+=("${user_dir}/AppData/Roaming/Zotero/Zotero")
    done
  done

  local candidate
  for candidate in "${candidates[@]}"; do
    candidate="$(normalize_path "${candidate}")"
    if [[ -f "${candidate}/profiles.ini" ]]; then
      printf '%s\n' "${candidate}"
      return
    fi
  done

  die "Could not locate Zotero profiles.ini. Set ZOTERO_PROFILE_DIR or ZOTERO_PROFILE_BASE."
}

resolve_active_profile_dir() {
  local profile_base
  profile_base="$(resolve_profile_base)" || return 1
  [[ -n "${profile_base}" ]] || die "Resolved empty Zotero profile base path"
  local profile_ini="${profile_base}/profiles.ini"
  [[ -f "${profile_ini}" ]] || die "profiles.ini not found at ${profile_ini}"

  python - "${profile_base}" "${profile_ini}" <<'PY'
from __future__ import annotations

import configparser
import sys
from pathlib import Path

profile_base = Path(sys.argv[1])
profile_ini = Path(sys.argv[2])

parser = configparser.RawConfigParser()
parser.read(profile_ini, encoding="utf-8")

sections = [s for s in parser.sections() if s.lower().startswith("profile")]
if not sections:
    raise SystemExit(f"No profile sections found in {profile_ini}")

chosen = None
for section in sections:
    if parser.get(section, "Default", fallback="0").strip() == "1":
        chosen = section
        break

if chosen is None and parser.has_section("Install"):
    # Zotero sometimes marks the active profile via Install/Default.
    default_name = parser.get("Install", "Default", fallback="").strip()
    if default_name:
        for section in sections:
            if parser.get(section, "Name", fallback="").strip() == default_name:
                chosen = section
                break

if chosen is None:
    chosen = sections[0]

path = parser.get(chosen, "Path", fallback="").strip()
if not path:
    raise SystemExit(f"Profile {chosen} missing Path in {profile_ini}")

is_relative = parser.get(chosen, "IsRelative", fallback="1").strip() != "0"
profile_dir = (profile_base / path) if is_relative else Path(path)
print(str(profile_dir.resolve()))
PY
}

backup_existing() {
  local file="$1"
  if [[ -f "${file}" ]]; then
    local backup="${file}.bak.$(timestamp_utc)"
    cp -p "${file}" "${backup}"
    echo "Backed up ${file} -> ${backup}"
  fi
}

main() {
  require_cmd cp
  require_cmd python

  local source_xpi
  source_xpi="$(normalize_path "${SOURCE_XPI}")"
  [[ -f "${source_xpi}" ]] || die "XPI not found: ${source_xpi}"

  local profile_dir extensions_dir target obsolete
  profile_dir="$(resolve_active_profile_dir)"
  extensions_dir="${profile_dir}/extensions"
  target="${extensions_dir}/${EXPECTED_ID}.xpi"
  obsolete="${extensions_dir}/${OBSOLETE_ID}"

  mkdir -p "${extensions_dir}"
  backup_existing "${target}"
  cp -f "${source_xpi}" "${target}"
  rm -f "${obsolete}"

  printf 'Installed %s -> %s\n' "${source_xpi}" "${target}"
  printf 'Removed obsolete file if present: %s\n' "${obsolete}"
}

main "$@"
