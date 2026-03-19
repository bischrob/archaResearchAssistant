from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import zipfile

import requests

from .config import Settings
from .path_utils import resolve_input_path


WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/].*")
URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


@dataclass
class AttachmentResolution:
    path: Path | None
    issue_code: str
    detail: str = ""
    resolver: str = ""


class ZoteroAttachmentResolver:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.webdav_url = (settings.zotero_webdav_url or "").strip().rstrip("/")
        self.webdav_cache_dir = resolve_input_path(settings.zotero_webdav_cache_dir)
        self.linked_path_map = self._load_linked_path_map(settings.zotero_linked_path_map_json)
        self.attachment_overrides = self._load_attachment_overrides(settings.zotero_attachment_override_json)
        self._session: requests.Session | None = None
        if self.webdav_url:
            self.webdav_cache_dir.mkdir(parents=True, exist_ok=True)
            self._session = requests.Session()
            username = (settings.zotero_webdav_username or "").strip()
            password = settings.zotero_webdav_password or ""
            if username:
                self._session.auth = (username, password)

    def close(self) -> None:
        if self._session is not None:
            self._session.close()

    def resolve(self, row: dict) -> AttachmentResolution:
        raw_path = str(row.get("attachment_path_raw") or "").strip()
        resolved = str(row.get("attachment_path") or "").strip()
        attachment_key = str(row.get("zotero_attachment_key") or "").strip()
        persistent_id = str(row.get("zotero_persistent_id") or "").strip()

        if not raw_path and not resolved:
            return AttachmentResolution(None, "missing_attachment_path")

        override = self._resolve_override(attachment_key, persistent_id)
        if override is not None:
            return AttachmentResolution(override, "ok", resolver="attachment_override")

        lowered_raw = raw_path.lower()
        if lowered_raw.startswith("storage:"):
            candidate = Path(resolved) if resolved else None
            if candidate and candidate.exists():
                return AttachmentResolution(candidate, "ok", resolver="local_storage")
            if attachment_key and self._session is not None:
                return self._resolve_via_webdav(attachment_key)
            return AttachmentResolution(None, "zotero_storage_missing_local", raw_path)

        if URL_SCHEME_RE.match(raw_path):
            return AttachmentResolution(None, "linked_url_or_webdav", raw_path)

        mapped = self._resolve_linked_file(raw_path, resolved)
        if mapped is not None:
            return AttachmentResolution(mapped, "ok", resolver="linked_path_map")

        if WIN_DRIVE_RE.match(raw_path):
            return AttachmentResolution(None, "linked_windows_path", raw_path)

        if raw_path.startswith("\\\\"):
            return AttachmentResolution(None, "linked_unc_path", raw_path)

        candidate = Path(resolved) if resolved else Path(raw_path)
        try:
            if candidate.exists():
                return AttachmentResolution(candidate, "ok", resolver="local_linked_path")
        except OSError:
            return AttachmentResolution(None, "local_path_io_error", raw_path or resolved)
        return AttachmentResolution(None, "local_path_missing", raw_path or resolved)

    def _resolve_via_webdav(self, attachment_key: str) -> AttachmentResolution:
        cache_dir = self.webdav_cache_dir / attachment_key.lower()
        cache_dir.mkdir(parents=True, exist_ok=True)

        cached = sorted(cache_dir.rglob("*.pdf"))
        if cached:
            return AttachmentResolution(cached[0], "ok", resolver="webdav_cache")

        url = f"{self.webdav_url}/{attachment_key}.zip"
        tmp_zip = cache_dir / f"{attachment_key}.zip"
        try:
            assert self._session is not None
            probe = self._session.head(url, timeout=(3, 8), allow_redirects=True)
            if probe.status_code == 404:
                probe.close()
                return AttachmentResolution(None, "webdav_missing_remote", url)
            if probe.status_code >= 400 and probe.status_code not in {405, 501}:
                status = probe.status_code
                reason = probe.reason
                probe.close()
                return AttachmentResolution(None, "webdav_probe_error", f"{url} :: {status} {reason}")
            probe.close()
        except requests.RequestException as exc:
            return AttachmentResolution(None, "webdav_probe_error", f"{url} :: {exc}")
        try:
            assert self._session is not None
            response = self._session.get(url, stream=True, timeout=(5, 20))
        except requests.RequestException as exc:
            return AttachmentResolution(None, "webdav_download_error", f"{url} :: {exc}")

        if response.status_code == 404:
            response.close()
            return AttachmentResolution(None, "webdav_missing_remote", url)
        try:
            response.raise_for_status()
            with tmp_zip.open("wb") as fh:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
        except requests.RequestException as exc:
            response.close()
            return AttachmentResolution(None, "webdav_download_error", f"{url} :: {exc}")
        finally:
            response.close()

        try:
            with zipfile.ZipFile(tmp_zip) as zf:
                members = [m for m in zf.infolist() if not m.is_dir()]
                if not members:
                    return AttachmentResolution(None, "webdav_bad_zip", url)
                pdf_members = [m for m in members if m.filename.lower().endswith(".pdf")]
                chosen = pdf_members[0] if pdf_members else members[0]
                target = cache_dir / Path(chosen.filename).name
                with zf.open(chosen) as src, target.open("wb") as dst:
                    dst.write(src.read())
        except (OSError, zipfile.BadZipFile) as exc:
            return AttachmentResolution(None, "webdav_bad_zip", f"{url} :: {exc}")
        finally:
            try:
                tmp_zip.unlink(missing_ok=True)
            except OSError:
                pass

        if target.exists():
            return AttachmentResolution(target, "ok", resolver="webdav_fetch")
        return AttachmentResolution(None, "webdav_cache_error", url)

    def _load_linked_path_map(self, raw_json: str) -> list[tuple[str, Path]]:
        text = (raw_json or "").strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        pairs: list[tuple[str, Path]] = []
        for src, dst in data.items():
            src_text = str(src or "").strip()
            dst_text = str(dst or "").strip()
            if not src_text or not dst_text:
                continue
            pairs.append((src_text.lower().replace("/", "\\"), resolve_input_path(dst_text)))
        pairs.sort(key=lambda x: len(x[0]), reverse=True)
        return pairs

    def _load_attachment_overrides(self, raw_path: str) -> dict[str, Path]:
        text = (raw_path or "").strip()
        if not text:
            return {}
        path = resolve_input_path(text)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[str, Path] = {}
        for k, v in data.items():
            key = str(k or "").strip()
            val = str(v or "").strip()
            if not key or not val:
                continue
            out[key] = resolve_input_path(val)
        return out

    def _resolve_override(self, attachment_key: str, persistent_id: str) -> Path | None:
        for key in (attachment_key, persistent_id):
            if not key:
                continue
            candidate = self.attachment_overrides.get(key)
            if candidate is None:
                continue
            try:
                if candidate.exists():
                    return candidate
            except OSError:
                continue
        return None

    def _resolve_linked_file(self, raw_path: str, resolved: str) -> Path | None:
        candidates: list[Path] = []
        if resolved:
            candidates.append(Path(resolved))
        for candidate in candidates:
            try:
                if candidate.exists():
                    return candidate
            except OSError:
                continue

        if raw_path:
            normalized_raw = raw_path.strip().replace("/", "\\")
            lowered = normalized_raw.lower()
            for src_prefix, dst_prefix in self.linked_path_map:
                if lowered.startswith(src_prefix):
                    remainder = normalized_raw[len(src_prefix):].lstrip("\\/")
                    mapped = dst_prefix / Path(remainder.replace("\\", "/")) if remainder else dst_prefix
                    candidates.append(mapped)

            if not (WIN_DRIVE_RE.match(raw_path) or raw_path.startswith("\\\\")):
                try:
                    candidates.append(resolve_input_path(raw_path))
                except Exception:
                    pass

        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if not key or key in seen:
                continue
            seen.add(key)
            try:
                if candidate.exists():
                    return candidate
            except OSError:
                continue
        return None
