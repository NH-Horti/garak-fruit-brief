"""Kakao "나에게 보내기" 최소 클라이언트 (agri-news-brief main.py 50819-50900 의 동작을 독립 구현).

- refresh_token → access_token 갱신. 응답에 새 refresh_token 이 오면 KAKAO_REFRESH_TOKEN_OUT_FILE 에 기록하고
  경고 (두 레포가 같은 토큰을 쓰므로 rotate 후 양쪽 secret 동시 갱신 — README 참조).
- 인증 오류(invalid_client/invalid_grant/insufficient_scope/access_denied)는 재시도 없이 KakaoNonRetryableError.
- 429/5xx 는 지수 백오프 재시도, 401/403 은 토큰 재발급 후 재시도.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from typing import Any

import requests

log = logging.getLogger("kakao")

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
NON_RETRYABLE = {"invalid_client", "invalid_grant", "insufficient_scope", "access_denied"}


class KakaoNonRetryableError(RuntimeError):
    pass


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _error_details(r: requests.Response) -> tuple[str, str, str]:
    try:
        data = r.json()
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    err = str(data.get("error") or "").strip()
    desc = str(data.get("error_description") or data.get("msg") or data.get("message") or "").strip()
    code = str(data.get("error_code") or data.get("code") or "").strip()
    return err, desc, code


def _raise_non_retryable(r: requests.Response, context: str) -> None:
    err, desc, code = _error_details(r)
    if err in NON_RETRYABLE:
        detail = desc or f"HTTP {r.status_code}"
        if code:
            detail = f"{detail} (code={code})"
        raise KakaoNonRetryableError(f"{context}: {err}: {detail}")


def _backoff(attempt: int, base: float = 0.8, cap: float = 15.0, jitter: float = 0.4) -> float:
    return min(cap, base * (2**attempt)) + random.uniform(0, jitter)


def _handle_refresh_renewal(payload: Any, current: str) -> None:
    if not isinstance(payload, dict):
        return
    new = str(payload.get("refresh_token") or "").strip()
    if not new or new == current:
        return
    path = _env("KAKAO_REFRESH_TOKEN_OUT_FILE")
    if path:
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new + "\n")
            try:
                os.chmod(path, 0o600)
            except Exception:
                pass
        except Exception as exc:  # pragma: no cover
            log.warning("renewed refresh token received but writing OUT_FILE failed: %s", exc)
    log.warning("[KAKAO] renewed refresh token received — rotate KAKAO_REFRESH_TOKEN in BOTH repos (garak-fruit-brief, agri-news-brief)")


def refresh_access_token(session: requests.Session | None = None) -> str:
    key = _env("KAKAO_REST_API_KEY")
    refresh = _env("KAKAO_REFRESH_TOKEN")
    secret = _env("KAKAO_CLIENT_SECRET")
    if not key or not refresh:
        raise RuntimeError("KAKAO_REST_API_KEY / KAKAO_REFRESH_TOKEN not set")
    data = {"grant_type": "refresh_token", "client_id": key, "refresh_token": refresh}
    if secret:
        data["client_secret"] = secret
    s = session or requests.Session()
    r = s.post(TOKEN_URL, data=data, timeout=30)
    if not r.ok:
        _raise_non_retryable(r, "Kakao token refresh failed")
        log.error("[KAKAO TOKEN ERROR] %s %s", r.status_code, r.text[:300])
        r.raise_for_status()
    j = r.json()
    _handle_refresh_renewal(j, refresh)
    return str(j["access_token"])


def send_template(template: dict[str, Any], session: requests.Session | None = None, max_try: int = 3) -> dict[str, Any]:
    """default 템플릿(feed/text …) 1건 전송. 성공 시 응답 JSON 반환."""
    s = session or requests.Session()
    access = refresh_access_token(s)
    last: requests.Response | None = None
    last_exc: Exception | None = None
    for attempt in range(max(1, min(max_try, 6))):
        try:
            r = s.post(
                SEND_URL,
                headers={"Authorization": f"Bearer {access}"},
                data={"template_object": json.dumps(template, ensure_ascii=False)},
                timeout=35,
            )
        except Exception as exc:
            last_exc = exc
            b = _backoff(attempt)
            log.warning("[KAKAO SEND] network error (attempt %d): %s -> sleep %.1fs", attempt + 1, exc, b)
            time.sleep(b)
            continue
        last = r
        if r.ok:
            try:
                return r.json()
            except Exception:
                return {"result_code": 0}
        if r.status_code in (401, 403):
            _raise_non_retryable(r, "Kakao send auth failed")
            try:
                access = refresh_access_token(s)
            except Exception as exc:
                log.warning("[KAKAO SEND] token refresh failed (attempt %d): %s", attempt + 1, exc)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            b = _backoff(attempt)
            log.warning("[KAKAO SEND] transient HTTP %s (attempt %d) -> sleep %.1fs", r.status_code, attempt + 1, b)
            time.sleep(b)
            continue
        _raise_non_retryable(r, "Kakao send failed")
        log.error("[KAKAO SEND ERROR] %s %s", r.status_code, r.text[:300])
        r.raise_for_status()
    if last is not None:
        _raise_non_retryable(last, "Kakao send failed")
        last.raise_for_status()
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Kakao send failed without response")
