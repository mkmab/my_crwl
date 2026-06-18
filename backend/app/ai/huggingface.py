import asyncio
import json
import socket
from typing import Any

import requests

from app.models import AnalysisResponse, CrawlResult, EmailResponse
from app.utils.config import settings
from .gemini import ANALYSIS_SCHEMA_KEYS, DICT_FIELDS, GeminiAnalyzer

HF_ROUTER_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"
HF_SERVERLESS_URL = "https://api-inference.huggingface.co/models"
HF_MODEL_FALLBACKS = [
    "google/gemma-2-2b-it",
    "Qwen/Qwen2.5-7B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
]

_NETWORK_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    socket.gaierror,
    OSError,
)


class HuggingFaceAnalyzer:
    """
    Analyse a crawled website using Hugging Face free-tier endpoints.

    Strategy:
      1. Try the current Hugging Face router chat-completions endpoint.
      2. Fall back to the legacy serverless inference endpoint.
      3. If both fail, return local_analysis/local_email.
    """

    async def analyze(self, crawl: CrawlResult, dom_snapshot: str | None = None) -> AnalysisResponse:
        fallback = GeminiAnalyzer().local_analysis(crawl)

        if not settings.huggingface_api_key:
            result = fallback.model_dump()
            result["ai_source"] = "local_fallback"
            result["ai_failure_reason"] = "Hugging Face API key is missing."
            result["short_summary"] = (
                "[Hugging Face API key missing. Showing local analysis.] "
                + (fallback.short_summary or "")
            )
            return AnalysisResponse(**result)

        if not self._can_reach_hf():
            result = fallback.model_dump()
            result["ai_source"] = "local_fallback"
            result["ai_failure_reason"] = "Hugging Face API unreachable (network/DNS error)."
            result["short_summary"] = (
                "[Hugging Face API unreachable (network/DNS error). Showing local analysis.] "
                + (fallback.short_summary or "")
            )
            return AnalysisResponse(**result)

        prompt = GeminiAnalyzer()._prompt(crawl, dom_snapshot)
        try:
            text = await self._generate_text(prompt, max_new_tokens=1500)
            parsed = self._safe_parse_json(text)
            if not GeminiAnalyzer()._looks_like_analysis_payload(parsed):
                raise RuntimeError("Hugging Face returned unusable analysis JSON.")

            for f in DICT_FIELDS:
                if f in parsed and parsed[f] is not None and not isinstance(parsed[f], dict):
                    parsed[f] = {"details": parsed[f]}

            merged = fallback.model_dump()
            merged.update({key: parsed.get(key, merged.get(key)) for key in ANALYSIS_SCHEMA_KEYS})

            for f in DICT_FIELDS:
                if f in merged and merged[f] is not None and not isinstance(merged[f], dict):
                    merged[f] = {"details": merged[f]}

            merged["ai_source"] = "huggingface"
            return AnalysisResponse(**merged)

        except _NETWORK_ERRORS as exc:
            result = fallback.model_dump()
            result["ai_source"] = "local_fallback"
            result["ai_failure_reason"] = f"Hugging Face network error: {exc}"
            result["short_summary"] = (
                f"[Hugging Face network error: {exc}. Showing local analysis.] "
                + (fallback.short_summary or "")
            )
            return AnalysisResponse(**result)
        except Exception as exc:
            result = fallback.model_dump()
            result["ai_source"] = "local_fallback"
            result["ai_failure_reason"] = f"Hugging Face analysis failed: {exc}"
            result["short_summary"] = (
                f"[Hugging Face analysis failed: {exc}. Showing local analysis.] "
                + (fallback.short_summary or "")
            )
            return AnalysisResponse(**result)

    async def generate_email(self, analysis: dict[str, Any], template: str) -> EmailResponse:
        fallback = GeminiAnalyzer().local_email(analysis, template)
        if not settings.huggingface_api_key:
            return fallback

        if not self._can_reach_hf():
            fb = fallback.model_dump()
            fb["ai_source"] = "local_fallback"
            return EmailResponse(**fb)

        try:
            prompt = GeminiAnalyzer()._email_prompt(analysis, template)
            text = await self._generate_text(prompt, max_new_tokens=420)
            parsed = self._safe_parse_json(text)
            if not GeminiAnalyzer()._looks_like_email_payload(parsed):
                raise RuntimeError("Hugging Face returned unusable email JSON.")

            subject = str(parsed.get("subject") or fallback.subject).strip()
            body = str(parsed.get("body") or fallback.body).strip()
            return EmailResponse(subject=subject[:120], body=body, ai_source="huggingface")
        except Exception:
            return fallback

    @staticmethod
    def _can_reach_hf() -> bool:
        try:
            resp = requests.head(HF_ROUTER_CHAT_URL, timeout=3)
            return resp.status_code < 500
        except requests.RequestException:
            return False

    @staticmethod
    def _local_result(fallback: AnalysisResponse, reason: str) -> AnalysisResponse:
        data = fallback.model_dump()
        data["ai_source"] = "local_fallback"
        data["ai_failure_reason"] = reason
        data["short_summary"] = f"[{reason}. Showing local analysis.] " + (fallback.short_summary or "")
        return AnalysisResponse(**data)

    async def _generate_text(self, prompt: str, max_new_tokens: int) -> str:
        errors: list[str] = []
        model_names = list(dict.fromkeys([settings.huggingface_model, *HF_MODEL_FALLBACKS]))

        for model_name in model_names:
            try:
                return await self._router_chat_completion(model_name, prompt, max_new_tokens)
            except Exception as exc:
                errors.append(f"router:{model_name}: {exc}")
                try:
                    return await self._legacy_serverless_generation(model_name, prompt, max_new_tokens)
                except Exception as legacy_exc:
                    errors.append(f"serverless:{model_name}: {legacy_exc}")
                    continue

        raise RuntimeError("; ".join(errors) or "No Hugging Face model could generate content.")

    async def _router_chat_completion(self, model_name: str, prompt: str, max_new_tokens: int) -> str:
        headers = {
            "Authorization": f"Bearer {settings.huggingface_api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "Return only valid JSON with no markdown fences."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_new_tokens,
            "stream": False,
        }

        def sync_call() -> str:
            resp = requests.post(
                HF_ROUTER_CHAT_URL,
                headers=headers,
                json=payload,
                timeout=settings.huggingface_timeout_seconds,
            )
            if resp.status_code >= 400:
                raise RuntimeError(self._http_error("router", model_name, resp))
            data = resp.json()
            text = (
                (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
                or ""
            )
            if isinstance(text, list):
                text = "".join(str(item.get("text") or "") for item in text if isinstance(item, dict))
            if not str(text).strip():
                raise RuntimeError(f"router:{model_name}: empty response")
            return str(text)

        return await asyncio.wait_for(
            asyncio.to_thread(sync_call),
            timeout=settings.huggingface_timeout_seconds + 10,
        )

    async def _legacy_serverless_generation(self, model_name: str, prompt: str, max_new_tokens: int) -> str:
        headers = {
            "Authorization": f"Bearer {settings.huggingface_api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": max_new_tokens,
                "temperature": 0.2,
                "top_p": 0.9,
                "return_full_text": False,
                "do_sample": True,
            },
            "options": {
                "wait_for_model": True,
                "use_cache": False,
            },
        }

        def sync_call() -> str:
            resp = requests.post(
                f"{HF_SERVERLESS_URL}/{model_name}",
                headers=headers,
                json=payload,
                timeout=settings.huggingface_timeout_seconds,
            )
            if resp.status_code >= 400:
                raise RuntimeError(self._http_error("serverless", model_name, resp))
            data = resp.json()
            text = self._extract_text(data)
            if not text.strip():
                raise RuntimeError(f"serverless:{model_name}: empty response")
            return text

        return await asyncio.wait_for(
            asyncio.to_thread(sync_call),
            timeout=settings.huggingface_timeout_seconds + 10,
        )

    def _http_error(self, source: str, model_name: str, response: requests.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            payload = {"error": response.text}
        if isinstance(payload, dict):
            error_message = payload.get("error") or payload.get("message") or response.text
        else:
            error_message = response.text
        return f"{source}:{model_name}: {error_message or f'HTTP {response.status_code}'}"

    def _extract_text(self, response: Any) -> str:
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            return str(response.get("generated_text") or response.get("text") or "")
        if isinstance(response, list) and response:
            first = response[0]
            if isinstance(first, dict):
                return str(first.get("generated_text") or first.get("text") or "")
            if isinstance(first, str):
                return first
        return json.dumps(response)

    def _safe_parse_json(self, text: str) -> dict[str, Any]:
        if not text:
            return {}
        cleaned = (
            text.strip()
            .removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        import re

        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            candidate = re.sub(r",\s*([}\]])", r"\1", match.group(0))
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        return {}
