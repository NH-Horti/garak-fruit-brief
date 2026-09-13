"""가락 과일 시세 브리프 — 카카오 발송 (§12 docs/design/12 §7.3, Market Analysis 레포 문서).

입력: docs/b/<date>-<token>/brief.json (Market Analysis 의 brief-garak-fruit.ts 가 Contents API 로 올림)
동작: 영수증 멱등 확인 → Pages URL 200 대기 → 피드 카드 전송(실패 시 텍스트 폴백) → docs/delivery/<date>.json 영수증
STALE 알림(dispatch payload freshness=STALE, 파일 없음): 텍스트 경고 1건.

사용: python send_brief.py --date 2026-09-11 --token abcd1234ef [--freshness FRESH] [--dry-run] [--reason ...]
종료코드: 0 success/already_delivered/skipped · 1 실패
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

import kakao_client

log = logging.getLogger("send_brief")
KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
DELIVERY_DIR = DOCS / "delivery"

TITLE_MAX = 200
DESC_MAX = 200
TEXT_MAX = 200


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def brief_dir(date: str, token: str) -> Path:
    return DOCS / "b" / f"{date}-{token}"


def load_meta(date: str, token: str) -> dict[str, Any]:
    p = brief_dir(date, token) / "brief.json"
    with open(p, encoding="utf-8") as fh:
        meta = json.load(fh)
    if not isinstance(meta, dict):
        raise RuntimeError(f"brief.json 형식 오류: {p}")
    return meta


def receipt_path(date: str) -> Path:
    return DELIVERY_DIR / f"{date}.json"


def load_receipt(date: str) -> dict[str, Any] | None:
    p = receipt_path(date)
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            j = json.load(fh)
        return j if isinstance(j, dict) else None
    except Exception:
        return None


def already_delivered(receipt: dict[str, Any] | None, date: str) -> bool:
    return bool(receipt) and receipt.get("date") == date and receipt.get("status") == "success"


def wait_for_url(url: str, timeout_sec: int = 300, interval: int = 10, session: requests.Session | None = None) -> bool:
    """GitHub Pages 반영 대기 — 200 이면 True. cache-bust 쿼리로 CDN 캐시 회피."""
    if not url:
        return False
    s = session or requests.Session()
    deadline = time.time() + timeout_sec
    while True:
        try:
            r = s.get(url, params={"_": int(time.time())}, timeout=20, headers={"Cache-Control": "no-cache"})
            if r.status_code == 200 and len(r.content) > 0:
                return True
            log.info("waiting for %s (HTTP %s)", url, r.status_code)
        except Exception as exc:
            log.info("waiting for %s (%s)", url, exc)
        if time.time() >= deadline:
            return False
        time.sleep(interval)


def _link(url: str) -> dict[str, str]:
    return {"web_url": url, "mobile_web_url": url}


def build_feed_template(meta: dict[str, Any]) -> dict[str, Any]:
    title = str(meta.get("title") or "가락 과일 시세")[:TITLE_MAX]
    desc = str(meta.get("description") or "")[:DESC_MAX]
    page = str(meta.get("page_url") or "")
    poster = str(meta.get("poster_url") or page)
    card = str(meta.get("card_url") or "")
    return {
        "object_type": "feed",
        "content": {
            "title": title,
            "description": desc,
            "image_url": card,
            "image_width": 800,
            "image_height": 800,
            "link": _link(page),
        },
        "buttons": [
            {"title": "포스터 보기", "link": _link(poster)},
            {"title": "상세 보기", "link": _link(page)},
        ],
    }


def build_text_template(meta: dict[str, Any]) -> dict[str, Any]:
    title = str(meta.get("title") or "가락 과일 시세")
    desc = str(meta.get("description") or "")
    text = f"{title}\n{desc}".strip()
    if len(text) > TEXT_MAX:
        text = text[: TEXT_MAX - 1].rstrip() + "…"
    page = str(meta.get("page_url") or "")
    return {"object_type": "text", "text": text, "link": _link(page), "button_title": "상세 보기"}


def build_stale_template(date: str, reason: str, prev_page: str) -> dict[str, Any]:
    text = f"가락 과일 시세 미발행 — {date} 05:00 갱신 실패 의심. {reason}".strip()
    if len(text) > TEXT_MAX:
        text = text[: TEXT_MAX - 1].rstrip() + "…"
    link = prev_page or "https://github.com/"
    return {"object_type": "text", "text": text, "link": _link(link), "button_title": "확인"}


def write_receipt(date: str, payload: dict[str, Any]) -> Path:
    DELIVERY_DIR.mkdir(parents=True, exist_ok=True)
    p = receipt_path(date)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return p


def sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def run(args: argparse.Namespace) -> int:
    date = args.date
    freshness = (args.freshness or "").upper()
    session = requests.Session()
    receipt = load_receipt(date)
    if already_delivered(receipt, date) and not args.force:
        log.info("already delivered for %s — skip", date)
        _status("already_delivered")
        return 0

    # STALE — 파일 없이 경고 텍스트만
    if freshness == "STALE":
        tpl = build_stale_template(date, args.reason or "", "")
        if args.dry_run:
            print(json.dumps(tpl, ensure_ascii=False, indent=2))
            return 0
        kakao_client.send_template(tpl, session)
        write_receipt(date, {"schema_version": 1, "date": date, "status": "success", "channel": "kakao", "message_format": "text_stale", "freshness": "STALE", "sent_at_kst": now_kst(), "reason": args.reason or ""})
        _status("success")
        return 0

    meta = load_meta(date, args.token)
    fmt = "feed"
    pages_ok = wait_for_url(meta.get("card_url", ""), timeout_sec=args.wait_sec, session=session) and wait_for_url(meta.get("page_url", ""), timeout_sec=60, session=session)
    tpl = build_feed_template(meta) if pages_ok else build_text_template(meta)
    if not pages_ok:
        fmt = "text_fallback"
        log.warning("Pages 반영 대기 초과 — 텍스트 폴백")
    if args.dry_run:
        print(json.dumps(tpl, ensure_ascii=False, indent=2))
        return 0
    try:
        kakao_client.send_template(tpl, session)
    except Exception as exc:
        if fmt == "feed":
            log.warning("feed 전송 실패(%s) — 텍스트 폴백 재시도", exc)
            tpl = build_text_template(meta)
            fmt = "text_fallback"
            kakao_client.send_template(tpl, session)
        else:
            raise
    write_receipt(date, {
        "schema_version": 1, "date": date, "status": "success", "channel": "kakao", "message_format": fmt,
        "freshness": meta.get("freshness"), "sent_at_kst": now_kst(),
        "urls": {"page": meta.get("page_url"), "poster": meta.get("poster_url"), "card": meta.get("card_url")},
        "item_count": meta.get("item_count"), "template_sha256": sha256(tpl),
    })
    _status("success")
    return 0


def _status(s: str) -> None:
    p = (os.getenv("KAKAO_STATUS_FILE") or "").strip()
    if p:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(s + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--token", default="")
    ap.add_argument("--freshness", default="")
    ap.add_argument("--reason", default="")
    ap.add_argument("--wait-sec", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return run(args)
    except kakao_client.KakaoNonRetryableError as exc:
        log.error("non-retryable: %s", exc)
        _status("failed_non_retryable")
        return 1
    except Exception as exc:
        log.exception("failed: %s", exc)
        _status("failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
