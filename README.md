# garak-fruit-brief

가락시장 과일 경매 시세 모닝브리프 — **게시(GitHub Pages) + 카카오톡 발송** 전용 레포.

- 시세 계산·렌더는 **NH Market Analysis** 레포(`scripts/brief-garak-fruit.ts`)가 하며, 산출물(`poster.png`·`card.png`·`index.html`·`data.json`·`brief.json`)을
  Contents API 로 `docs/b/<date>-<token>/` 에 올린 뒤 `repository_dispatch(brief-published)` 를 보낸다.
- 이 레포는 그 이벤트를 받아 **카카오 "나에게 보내기" 피드 카드**를 전송하고 `docs/delivery/<date>.json` 영수증을 남긴다.
- 설계 원문: Market Analysis `docs/design/12_garak_fruit_morning_brief.md`. 뉴스브리핑(`agri-news-brief`)과는 **완전 별개** 운영.

## 경로 규칙

- `docs/b/<YYYY-MM-DD>-<token>/` — token = HMAC-SHA256(`BRIEF_PATH_SECRET`, date) base32 앞 10자. Market Analysis `.env` 의 secret 으로만 재계산 가능.
- 목록 페이지 없음, `docs/robots.txt` Disallow, `docs/index.html` 은 안내문만. 링크를 받은 사람만 열람.

## Secrets (Settings → Secrets and variables → Actions)

| 이름 | 용도 |
|---|---|
| `KAKAO_REST_API_KEY` | 카카오 앱 REST 키 (agri-news-brief 와 같은 앱) |
| `KAKAO_CLIENT_SECRET` | 카카오 앱 client secret |
| `KAKAO_REFRESH_TOKEN` | "나에게 보내기" 동의한 계정의 refresh token (agri-news-brief 와 **같은 값**) |

GitHub Pages: Settings → Pages → Source `Deploy from a branch`, Branch `main` / `/docs`. (`docs/.nojekyll` 필수)

## Refresh token 갱신 절차 (두 레포 공유)

카카오는 만료 임박 시 토큰 갱신 응답에 새 `refresh_token` 을 준다. 이 레포와 agri-news-brief 가 같은 토큰을 쓰므로
**어느 쪽이든 갱신을 감지하면 Actions 가 실패로 알린다**(`Refresh token renewed: true`). 그때:

1. agri-news-brief 의 `scripts/rotate-kakao-refresh-token.ps1` 로 재발급
2. **두 레포 모두** `KAKAO_REFRESH_TOKEN` secret 갱신
3. 이 레포 `send.yml` 을 `workflow_dispatch` (date=어제, force=true) 로 재전송 확인

## 수동 실행

- Actions → `garak-fruit-brief (send)` → Run workflow: `date`·`token`(Market Analysis `out/brief/garak-fruit/<date>/published.json` 의 token)·`dry_run` 으로 템플릿만 확인 가능.
- 로컬: `pip install -r requirements.txt` → `python send_brief.py --date 2026-09-11 --token <token> --dry-run` (env 에 KAKAO_* 필요, dry-run 은 불필요).

## 발송 시각

Market Analysis 의 05:00 갱신이 끝나면(≈05:07) 게시·dispatch 되지만, 카톡은 **`SEND_AT_KST` 시각(기본 07:00)** 까지 워크플로가 기다렸다 보낸다.
바꾸려면 Settings → Secrets and variables → Actions → **Variables** 에 `SEND_AT_KST` = `HH:MM` 추가/수정 (코드 수정 불필요).
이미 지난 시각에 dispatch 되면(08:30 캐치업·수동 재발행) 즉시 발송. 수동 Run workflow 는 `wait` 체크 시에만 대기.

## 신선도별 동작

| freshness | 발송 |
|---|---|
| FRESH | 피드 카드 (card.png + 제목 + 요약 + 버튼 2) |
| PARTIAL | 피드 카드, 요약 앞 "⚠상품기준가 미수신(평균가)" |
| STALE | 텍스트 경고 1건 (파일 없음) |
| 피드 실패·Pages 미반영(5분) | 텍스트 폴백 (`message_format: text_fallback`) |

## 테스트

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
