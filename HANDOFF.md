# HANDOFF — 정기 브리핑 Actions 이관 잔여 작업 (2026-09-04)

## 현재 상태
- 정기 브리핑 발송 주체를 Render 워커 → GitHub Actions cron으로 이관 완료.
  - 워크플로: `.github/workflows/briefing.yml` (`00:00` / `09:00` UTC = `09:00` / `18:00` KST) + `workflow_dispatch`
  - 발송기: `briefing.py` (웹훅 발송, 슬롯 판정 없음 — cron이 시각 보장)
  - 워커(`discord_interactive_bot.py`)의 자동발송 루프는 삭제됨 → 이중발송 없음.
- 필요 시크릿(둘 다 등록済, 2026-08-31): `DISCORD_WEBHOOK_URL`, `GEMINI_API_KEY`
- 그 과정에서 잡은 버그: 만료 Gemini 모델명 하드코딩 → `ListModels` 런타임 선택 +
  후보 순회(`_pick_gemini_models`), 전실패시 `_offline` 폴백 보장, 웹훅 실패 로그 추가.

## 미완 — 테스트런 #3 결과 확인
- 실행: `gh run view 33859196597 --repo hodoi-ing/hodori-bot --log | grep -E "모델 후보|웹훅"`
- 판정표:
  - `웹훅 발송: True` → 끝. 다음날 09:00 KST 자동발송 대기.
  - `Discord 웹훅 HTTP 4xx` 또는 `웹훅 발송: False` → `DISCORD_WEBHOOK_URL` 시크릿 만료.
    디스코드 채널 설정 → 연동 → 웹훅 URL 재발급 →
    `gh secret set DISCORD_WEBHOOK_URL --repo hodoi-ing/hodori-bot` 후
    `gh workflow run briefing.yml --repo hodoi-ing/hodori-bot` 재실행.
  - `Gemini ... 404/503` 전후보 실패 + 오프라인 카드 발송됨 → 해당 키/리전에
    사용 가능 flash 모델 없음. `GEMINI_API_KEY` 키 권한·결제 상태 확인할 것.
- 참고: 테스트런 #1(`33858620666`) 모델 503/404 + `None` 크래시,
  #2(`33858920595`) `gemini-2.5-flash` 404 + 웹훅 `False`.
