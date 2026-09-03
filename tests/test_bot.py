"""hodori-bot unit tests — pure logic, no network, no Discord connection."""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import doribogo_bot


def _dt(hour: int, minute: int) -> datetime:
    return datetime(2026, 9, 3, hour, minute)


def test_briefing_slot_morning():
    assert doribogo_bot.is_briefing_slot(_dt(9, 0)) is True
    assert doribogo_bot.is_briefing_slot(_dt(9, 4)) is True


def test_briefing_slot_evening():
    assert doribogo_bot.is_briefing_slot(_dt(18, 0)) is True
    assert doribogo_bot.is_briefing_slot(_dt(18, 4)) is True


def test_briefing_slot_closed():
    assert doribogo_bot.is_briefing_slot(_dt(9, 5)) is False
    assert doribogo_bot.is_briefing_slot(_dt(12, 0)) is False
    assert doribogo_bot.is_briefing_slot(_dt(18, 5)) is False
    assert doribogo_bot.is_briefing_slot(_dt(8, 59)) is False


def test_offline_card_contains_title_and_link():
    items = [{"title": "테스트 이슈 본문", "link": "https://example.invalid/1", "source": "Threads @x"}]
    card = doribogo_bot._offline("오늘의 이슈", items)
    assert "테스트 이슈 본문" in card
    assert "https://example.invalid/1" in card


def test_offline_card_empty_items():
    card = doribogo_bot._offline("오늘의 이슈", [])
    assert "오늘의 이슈" in card


def test_gemini_fallback_without_key(monkeypatch):
    monkeypatch.setattr(doribogo_bot, "GEMINI_API_KEY", "")
    items = [{"title": "폴백 확인용", "link": "https://example.invalid/2", "source": "Threads @y"}]
    card = doribogo_bot.generate_gemini_card_news("테스트", items)
    assert "폴백 확인용" in card
    assert "https://example.invalid/2" in card


def _clean_search_term(cleaned_query: str) -> str:
    return re.sub(
        r"(최저가|가격비교|얼마야|얼마해|얼마정도|얼마|알아봐줘|찾아줘|사려는데|사고싶어|살까|가격|검색해줘|검색|시세|하는데|있어|있니|좀|해줘|보여줘|[?!\.,~])\s*",
        "",
        cleaned_query,
    ).strip() or cleaned_query


def test_search_term_cleaning():
    assert _clean_search_term("에어팟 얼마해?") == "에어팟"
    assert _clean_search_term("닌텐도 스위치 살까 하는데") == "닌텐도 스위치"
    assert _clean_search_term("버즈3 프로 가격") == "버즈3 프로"
    assert _clean_search_term("로봇청소기 알아봐줘") == "로봇청소기"
    assert _clean_search_term("아이폰 16") == "아이폰 16"


def test_threads_creators_configured():
    assert set(doribogo_bot.THREADS_CREATORS) == {"choi.openai", "unclejobs.ai", "h2smusic"}
