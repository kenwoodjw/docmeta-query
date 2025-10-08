from collections.abc import Generator
from typing import Any, Iterable, Union, cast
import json
import urllib.parse
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class DocmetaQueryTool(Tool):
    """
    Query document metadata across datasets by document name.

    Inputs (via tool_parameters):
      - dataset_list: list[str] | str (JSON array or comma-separated)
      - kb_api_key: str
      - document_name: list[str] | str (JSON array, comma-separated, or single keyword)
      - metadata_filter: Optional[str] (JSON list of names, or JSON object {name: expected_value},
        or comma-separated names)

    Output (JSON message):
      { "documents": [ { "document_name": str, "metadata": list }, ... ] }
      When metadata_filter provided, metadata list is filtered accordingly.
    """

    DEFAULT_BASE_URL = "http://127.0.0.1:5001"

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            dataset_list = self._normalize_dataset_list(tool_parameters.get("dataset_list"))
            api_key = self._require_str(tool_parameters.get("kb_api_key"), name="kb_api_key")
            document_name_list = self._normalize_document_name_list(tool_parameters.get("document_name"))
            metadata_filter_raw = tool_parameters.get("metadata_filter")
            base_url = self._normalize_base_url(tool_parameters.get("kb_base_url"))
            name_filter_set, name_value_map = self._parse_metadata_filter(metadata_filter_raw)
        except ValueError as e:
            yield self.create_error_message(str(e))
            return

        aggregated: list[dict[str, Any]] = []
        errors: list[str] = []
        for ds_id in dataset_list:
            for doc_name_keyword in document_name_list:
                try:
                    docs = self._fetch_documents(
                        base_url=base_url,
                        dataset_id=ds_id,
                        api_key=api_key,
                        keyword=doc_name_keyword,
                    )
                except Exception as e:  # network or parse errors per dataset shouldn't stop others
                    errors.append(f"dataset {ds_id}, keyword '{doc_name_keyword}': {e}")
                    continue

                for doc in docs:
                    # Prefer top-level name; fallback to metadata 'document_name'
                    doc_name = cast(str | None, doc.get("name"))
                    if not doc_name:
                        doc_name = self._extract_document_name_from_metadata(doc.get("doc_metadata", []))
                    # Ensure metadata list
                    metadata_list = cast(list[dict[str, Any]], doc.get("doc_metadata", []) or [])
                    filtered_metadata = self._filter_metadata(metadata_list, name_filter_set, name_value_map)

                    aggregated.append({
                        "document_name": doc_name or "",
                        "metadata": filtered_metadata,
                    })

        if not aggregated:
            if errors:
                yield self.create_error_message("no documents found; errors: " + "; ".join(errors))
            else:
                yield self.create_error_message("no documents found")
            return

        yield self.create_json_message({"documents": aggregated})

    # ------------------------------- helpers ---------------------------------

    def _require_str(self, val: Any, *, name: str) -> str:
        if val is None:
            raise ValueError(f"missing required parameter: {name}")
        if isinstance(val, str):
            s = val.strip()
            if not s:
                raise ValueError(f"parameter '{name}' cannot be empty")
            return s
        # allow numbers or other simple types converted to str
        return str(val)

    def _normalize_dataset_list(self, val: Any) -> list[str]:
        if val is None:
            raise ValueError("missing required parameter: dataset_list")
        if isinstance(val, list):
            items = [str(x).strip() for x in val if str(x).strip()]
            if not items:
                raise ValueError("parameter 'dataset_list' is empty")
            return items
        if isinstance(val, str):
            s = val.strip()
            if not s:
                raise ValueError("parameter 'dataset_list' is empty")
            # Try JSON array first
            if (s.startswith("[") and s.endswith("]")) or (s.startswith("\"") and s.endswith("\"")):
                try:
                    parsed = json.loads(s)
                    return self._normalize_dataset_list(parsed)
                except Exception:
                    pass
            # Fallback: comma/space separated
            parts = [p.strip() for p in s.replace("\n", ",").split(",")]
            parts = [p for p in parts if p]
            if not parts:
                raise ValueError("parameter 'dataset_list' is empty")
            return parts
        # other types: attempt to coerce into a list
        return [str(val)]

    def _normalize_document_name_list(self, val: Any) -> list[str]:
        """
        Normalize document_name parameter to a list of keywords.
        Accepts:
          - list[str]: direct list of keywords
          - str: JSON array, comma-separated, or single keyword
        """
        if val is None:
            raise ValueError("missing required parameter: document_name")
        if isinstance(val, list):
            items = [str(x).strip() for x in val if str(x).strip()]
            if not items:
                raise ValueError("parameter 'document_name' is empty")
            return items
        if isinstance(val, str):
            s = val.strip()
            if not s:
                raise ValueError("parameter 'document_name' is empty")
            # Try JSON array first
            if (s.startswith("[") and s.endswith("]")) or (s.startswith("\"") and s.endswith("\"")):
                try:
                    parsed = json.loads(s)
                    return self._normalize_document_name_list(parsed)
                except Exception:
                    pass
            # Fallback: comma/Chinese comma/newline separated
            parts = [p.strip() for p in s.replace("\n", ",").replace("，", ",").split(",")]
            parts = [p for p in parts if p]
            if not parts:
                raise ValueError("parameter 'document_name' is empty")
            return parts
        # other types: attempt to coerce into a list
        return [str(val)]

    def _parse_metadata_filter(
        self, val: Any
    ) -> tuple[set[str] | None, dict[str, str] | None]:
        """
        Accepts:
          - None/empty: no filter
          - JSON list[str]: names set
          - JSON object{name: value}: name→expected value map
          - string with comma-separated names

        Returns (names_set, name_value_map). Only one will be non-None.
        """
        if val is None:
            return None, None
        # Already-typed list or dict
        if isinstance(val, list):
            names = {str(x).strip() for x in val if str(x).strip()}
            return (names or None), None
        if isinstance(val, dict):
            mapping = {str(k).strip(): str(v).strip() for k, v in val.items() if str(k).strip()}
            return None, (mapping or None)
        # String input
        if isinstance(val, str):
            s = val.strip()
            if not s:
                return None, None
            # Try JSON first
            if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
                try:
                    parsed = json.loads(s)
                    return self._parse_metadata_filter(parsed)
                except Exception:
                    pass
            # key=value pairs (supports commas, semicolons, Chinese commas/semicolons, or newlines)
            if "=" in s:
                mapping: dict[str, str] = {}
                normalized = (
                    s.replace("\n", ",")
                    .replace("；", ";")
                    .replace("，", ",")
                    .replace(";", ",")
                )
                for token in normalized.split(","):
                    token = token.strip()
                    if not token or "=" not in token:
                        continue
                    k, v = token.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if k:
                        mapping[k] = v
                return (None, mapping or None)
            # Otherwise treat as names list (comma/Chinese comma/newline separated)
            names = {
                p.strip()
                for p in s.replace("\n", ",").replace("，", ",").split(",")
                if p.strip()
            }
            return (names or None), None
        # Fallback
        return None, None

    def _filter_metadata(
        self,
        metadata_list: Iterable[dict[str, Any]],
        names_set: set[str] | None,
        name_value_map: dict[str, str] | None,
    ) -> list[dict[str, Any]]:
        if not metadata_list:
            return []
        if not names_set and not name_value_map:
            # Exclude built-in metadata by default
            return [m for m in metadata_list if not self._is_built_in_metadata(m)]

        filtered: list[dict[str, Any]] = []
        for m in metadata_list:
            # Skip built-in metadata
            if self._is_built_in_metadata(m):
                continue
            name = str(m.get("name", "")).strip()
            if not name:
                continue
            if names_set is not None:
                if name in names_set:
                    filtered.append(m)
                continue
            if name_value_map is not None:
                if name in name_value_map:
                    expected = name_value_map[name]
                    value = m.get("value")
                    value_str = "" if value is None else str(value).strip()
                    if value_str == expected:
                        filtered.append(m)
                continue
        return filtered

    def _is_built_in_metadata(self, m: dict[str, Any]) -> bool:
        mid = str(m.get("id", "")).strip().lower()
        if mid in {"built-in", "built_in"}:
            return True
        builtin_names = {"document_name", "uploader", "upload_date", "last_update_date", "source"}
        name = str(m.get("name", "")).strip()
        return name in builtin_names

    def _extract_document_name_from_metadata(self, metadata_list: Iterable[dict[str, Any]]) -> str | None:
        for m in metadata_list or []:
            if m.get("name") == "document_name":
                v = m.get("value")
                return None if v is None else str(v)
        return None

    def _fetch_documents(self, *, base_url: str, dataset_id: str, api_key: str, keyword: str) -> list[dict[str, Any]]:
        url = f"{base_url.rstrip('/')}/v1/datasets/{urllib.parse.quote(dataset_id)}/documents"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers, params={"keyword": keyword}, timeout=30)
        except requests.RequestException as e:
            raise RuntimeError(f"request error: {e}") from e
        if resp.status_code != 200:
            text = resp.text or ""
            raise RuntimeError(f"HTTP {resp.status_code}: {text[:200]}")
        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError("unexpected response format: not JSON")
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise RuntimeError("unexpected response format: missing 'data' list")
        return items

    def _normalize_base_url(self, val: Any) -> str:
        if val is None:
            return self.DEFAULT_BASE_URL
        s = str(val).strip()
        if not s:
            return self.DEFAULT_BASE_URL
        # Minimal validation: must look like http(s) URL
        if not (s.startswith("http://") or s.startswith("https://")):
            # if only host:port provided, assume http
            s = "http://" + s
        return s
