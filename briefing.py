"""GitHub Actions cron 전용 정기 브리핑 발송기.

스케줄(cron) 자체가 시각을 보장하므로 슬롯 판정 없이 매 실행마다 1회 발송한다.
필요 env: DISCORD_WEBHOOK_URL, GEMINI_API_KEY
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    KST = ZoneInfo("Asia/Seoul")
except Exception:
    KST = timezone(timedelta(hours=9))

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import doribogo_bot


def main() -> int:
    now = datetime.now(KST)
    title = f"⚡ [{now.strftime('%m월 %d일')} 스레드 3인방 실시간 핫이슈]"
    print(f"[*] {now.strftime('%Y-%m-%d %H:%M')} 브리핑 수집 시작")
    card = doribogo_bot.run_full_doribogo("실시간 테크 이슈")
    ok = doribogo_bot.send_discord(title, card)
    print(f"[*] 웹훅 발송: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
