import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import send_brief  # noqa: E402


META = {
    "schema_version": 1, "date": "2026-09-11", "weekday": "금", "freshness": "FRESH",
    "title": "가락 과일 시세 09-11(금)",
    "description": "사과 홍로10kg 52,897 ▲5.1% 경계↑ · 배 신고7.5kg 41,029 ▼4.2% 안정",
    "page_url": "https://x.github.io/y/b/2026-09-11-abc/index.html",
    "poster_url": "https://x.github.io/y/b/2026-09-11-abc/poster.png",
    "card_url": "https://x.github.io/y/b/2026-09-11-abc/card.png",
    "item_count": 6,
}


class TemplateTests(unittest.TestCase):
    def test_feed_template_shape(self):
        t = send_brief.build_feed_template(META)
        self.assertEqual(t["object_type"], "feed")
        self.assertTrue(t["content"]["image_url"].startswith(META["card_url"] + "?v="))
        # 재게시(generated_at 변경) 시 이미지 URL 이 달라져야 카카오 캐시를 피한다
        t2 = send_brief.build_feed_template(dict(META, generated_at_kst="2026-09-14T09:00:00+09:00"))
        self.assertNotEqual(t["content"]["image_url"], t2["content"]["image_url"])
        self.assertEqual(t["content"]["image_width"], 800)
        self.assertTrue(t["content"]["link"]["mobile_web_url"].startswith(META["page_url"] + "?v="))
        self.assertEqual([b["title"] for b in t["buttons"]], ["포스터 보기", "상세 보기"])
        self.assertTrue(t["buttons"][0]["link"]["web_url"].startswith(META["poster_url"] + "?v="))

    def test_text_fallback_truncates_200(self):
        m = dict(META, description="가" * 500)
        t = send_brief.build_text_template(m)
        self.assertEqual(t["object_type"], "text")
        self.assertLessEqual(len(t["text"]), 200)
        self.assertTrue(t["text"].endswith("…"))
        self.assertEqual(t["button_title"], "상세 보기")

    def test_stale_template(self):
        t = send_brief.build_stale_template("2026-09-11", "data12 최신 2026-09-10", "")
        self.assertIn("미발행", t["text"])
        self.assertLessEqual(len(t["text"]), 200)


class ReceiptTests(unittest.TestCase):
    def test_already_delivered_only_on_success_same_date(self):
        self.assertTrue(send_brief.already_delivered({"date": "2026-09-11", "status": "success"}, "2026-09-11"))
        self.assertFalse(send_brief.already_delivered({"date": "2026-09-10", "status": "success"}, "2026-09-11"))
        self.assertFalse(send_brief.already_delivered({"date": "2026-09-11", "status": "failed"}, "2026-09-11"))
        self.assertFalse(send_brief.already_delivered(None, "2026-09-11"))

    def test_run_is_idempotent_and_writes_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            docs = Path(td) / "docs"
            d = docs / "b" / "2026-09-11-abc"
            d.mkdir(parents=True)
            (d / "brief.json").write_text(json.dumps(META, ensure_ascii=False), encoding="utf-8")
            sent = []
            with mock.patch.object(send_brief, "DOCS", docs), \
                 mock.patch.object(send_brief, "DELIVERY_DIR", docs / "delivery"), \
                 mock.patch.object(send_brief, "wait_for_url", return_value=True), \
                 mock.patch.object(send_brief.kakao_client, "send_template", side_effect=lambda t, s=None: sent.append(t) or {"result_code": 0}):
                args = send_brief.main.__globals__["argparse"].Namespace(date="2026-09-11", token="abc", freshness="FRESH", reason="", wait_sec=1, dry_run=False, force=False)
                self.assertEqual(send_brief.run(args), 0)
                self.assertEqual(len(sent), 1)
                self.assertEqual(sent[0]["object_type"], "feed")
                rec = json.loads((docs / "delivery" / "2026-09-11.json").read_text(encoding="utf-8"))
                self.assertEqual(rec["status"], "success")
                self.assertEqual(rec["message_format"], "feed")
                # 2회차 — 영수증으로 억제
                self.assertEqual(send_brief.run(args), 0)
                self.assertEqual(len(sent), 1)

    def test_text_fallback_when_pages_not_ready(self):
        with tempfile.TemporaryDirectory() as td:
            docs = Path(td) / "docs"
            d = docs / "b" / "2026-09-11-abc"
            d.mkdir(parents=True)
            (d / "brief.json").write_text(json.dumps(META, ensure_ascii=False), encoding="utf-8")
            sent = []
            with mock.patch.object(send_brief, "DOCS", docs), \
                 mock.patch.object(send_brief, "DELIVERY_DIR", docs / "delivery"), \
                 mock.patch.object(send_brief, "wait_for_url", return_value=False), \
                 mock.patch.object(send_brief.kakao_client, "send_template", side_effect=lambda t, s=None: sent.append(t) or {}):
                args = send_brief.main.__globals__["argparse"].Namespace(date="2026-09-11", token="abc", freshness="FRESH", reason="", wait_sec=1, dry_run=False, force=False)
                self.assertEqual(send_brief.run(args), 0)
                self.assertEqual(sent[0]["object_type"], "text")
                rec = json.loads((docs / "delivery" / "2026-09-11.json").read_text(encoding="utf-8"))
                self.assertEqual(rec["message_format"], "text_fallback")


if __name__ == "__main__":
    unittest.main()
