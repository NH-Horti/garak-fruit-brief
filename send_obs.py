"""KREI 과일관측회의 발언 노트 — 카카오 발송 (Market Analysis docs/design/28 §10.1, Q11).

모닝브리프와 같은 카카오 키·토큰(kakao_client)을 쓰되 메시지·영수증은 별개.
입력: repository_dispatch `obs-published` payload {ym, page_url, title, description, send_at}
영수증: docs/delivery/obs-<ym>.json (멱등 — 같은 월호는 한 번만, --force 로 재발송)

사용: python send_obs.py --ym 2026-10 --page-url https://... --title ... --description ... [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import kakao_client

log = logging.getLogger("send_obs")
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
DELIVERY_DIR = ROOT / "docs" / "delivery"
TEXT_MAX = 200


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def receipt_path(ym: str) -> Path:
    return DELIVERY_DIR / f"obs-{ym}.json"


def _status(s: str) -> None:
    p = (os.getenv("KAKAO_STATUS_FILE") or "").strip()
    if p:
        Path(p).write_text(s, encoding="utf-8")


def wait_for_url(url: str, timeout_sec: int = 300, interval: int = 10) -> bool:
    deadline = time.time() + timeout_sec
    while True:
        try:
            r = requests.get(url, params={"_": int(time.time())}, timeout=20, headers={"Cache-Control": "no-cache"})
            if r.status_code == 200 and r.content:
                return True
            log.info("waiting for %s (HTTP %s)", url, r.status_code)
        except Exception as exc:  # noqa: BLE001
            log.info("waiting for %s (%s)", url, exc)
        if time.time() >= deadline:
            return False
        time.sleep(interval)


def build_template(title: str, description: str, page_url: str) -> dict:
    text = f"{title}\n{description}".strip()
    if len(text) > TEXT_MAX:
        text = text[: TEXT_MAX - 1].rstrip() + "…"
    sep = "&" if "?" in page_url else "?"
    url = f"{page_url}{sep}v={int(time.time())}"
    return {"object_type": "text", "text": text, "link": {"web_url": url, "mobile_web_url": url}, "button_title": "발언 노트 보기"}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ym", required=True)
    ap.add_argument("--page-url", required=True)
    ap.add_argument("--title", default="과일관측회의 발언 노트")
    ap.add_argument("--description", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    rp = receipt_path(a.ym)
    if rp.exists() and not a.force:
        try:
            if json.loads(rp.read_text(encoding="utf-8")).get("status") == "success":
                log.info("already delivered: %s", rp)
                _status("already_delivered")
                return 0
        except Exception:  # noqa: BLE001
            pass

    tpl = build_template(a.title, a.description, a.page_url)
    if a.dry_run:
        print(json.dumps(tpl, ensure_ascii=False, indent=1))
        _status("dry_run")
        return 0
    if not wait_for_url(a.page_url):
        log.error("page not reachable: %s", a.page_url)
        _status("page_unreachable")
        return 1
    try:
        kakao_client.send_template(tpl, requests.Session())
    except kakao_client.KakaoNonRetryableError as exc:
        log.error("kakao non-retryable: %s", exc)
        _status("failed")
        return 1
    DELIVERY_DIR.mkdir(parents=True, exist_ok=True)
    receipt = {"schema_version": 1, "kind": "observation", "ym": a.ym, "status": "success", "channel": "kakao", "page_url": a.page_url, "sent_at_kst": now_kst()}
    rp.write_text(json.dumps(receipt, ensure_ascii=False, indent=1), encoding="utf-8")
    _status("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
