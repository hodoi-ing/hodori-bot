# 🐯 hodori-bot

디스코드 대화형 비서 & 실시간 큐레이션 봇. 24시간 상시 가동되며 매일 아침 09:00 / 저녁 18:00(KST) 정기 브리핑을 자동 발송합니다.

## ✨ 주요 기능

### 1. 🛒 실시간 오픈마켓 최저가 검색 (다나와 브릿지 기반)
다나와 가격비교 AJAX를 활용해 쿠팡, G마켓, 11번가, 옥션, 롯데ON 등 판매처별 실시간 가격과 **카드/쿠폰 추가할인가**까지 파싱합니다.
결과는 **실질 최저가 1위 판매처의 최종 할인가 + 직통 구매링크**만 깔끔하게 출력합니다.

```
도리야 에어팟 얼마해?
도리야 닌텐도 스위치 살까 하는데
!핫딜 아이폰 16
```

### 2. 🔥 스레드 3인방 실시간 핫이슈 브리핑 (GeekNews 스타일)
`@choi.openai`, `@unclejobs.ai`, `@h2smusic` 3인의 스레드에서 가장 반응(좋아요)이 좋은 베스트 글을 선정하고,
글쓴이가 타래(1/8 ~ n/8)로 덧붙인 전체 내용을 끝까지 수집해 GeekNews식 심층 요약으로 정리합니다.

### 3. 💬 자연어 대화 & 명령어
- `도리야 [질문]`, `호도리야 [질문]`, `@hodori bot [질문]` — 자연어 호출
- `!도리 [키워드]` — 스레드 3인방 + 글로벌 테크 레이더 실시간 리서치
- `!핫딜 [상품명]` — 오픈마켓 실시간 최저가 검색 (카드/쿠폰 할인가 포함)
- `!ai [질문]` — Gemini 자유 대화 / 코딩 비서

## 🛠️ 로컬 실행

```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium

# .env 파일 생성 (절대 커밋 금지 — .gitignore 처리됨)
cat > .env << 'EOF'
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=your_channel_id
GEMINI_API_KEY=your_gemini_api_key
EOF

python discord_interactive_bot.py
```

> ⚠️ API 키를 코드에 하드코딩하지 마세요. 전부 환경변수(`.env` / Render Environment)에서 읽습니다.

## ✅ 테스트

```bash
python -m pytest tests/ -q
```

브리핑 슬롯 판정, 폴백 카드 포맷, 검색어 정제, 크리에이터 설정을 검증합니다 (외부 네트워크 불필요).

## ☁️ 클라우드 배포 (Render)

`render.yaml`이 포함되어 있어 Render.com에서 원클릭 배포가 가능합니다.
`requirements.txt` + Chromium 자동 설치가 빌드 단계에 포함되어 있습니다.
배포 후 Environment에 `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`, `GEMINI_API_KEY` 3개를 등록하세요.

---

## 📌 추후 도입 검토 기술 (Backlog / Ideas)

### 1. Claude Code / Codex CLI 연동 봇 환경 (ThisCode & ThisCodex)
- **GitHub 저장소:**
  - [treylom/ThisCode](https://github.com/treylom/ThisCode)
  - [treylom/tofukyung-plugins](https://github.com/treylom/tofukyung-plugins)
- **설명 & 특징:**
  - Claude Code와 Codex CLI 세션을 슬랙/디스코드 인터페이스와 직접 연결하는 운영 번들.
  - 별도 유료 API 호출 없이 터미널 세션과 직접 소통하여 디스코드 채팅창에서 명령 수행 가능.
  - AI 에이전트 간 회의(Multi-Agent Collaboration) 및 팀 워크플로우 지원.
  - 추후 호도리 봇 채널에서 터미널 작업 지시나 상태 브리핑 기능으로 확장 검토.

### 2. 자연어 기반 스마트 웹 스크래퍼 (ScrapeGraphAI)
- **GitHub 저장소:**
  - [ScrapeGraphAI/Scrapegraph-ai](https://github.com/ScrapeGraphAI/Scrapegraph-ai)
- **설명 & 특징:**
  - 파이썬 기반으로, URL과 추출하고 싶은 정보(프롬프트)를 입력하면 1분 내에 구조화된 표/JSON으로 반환.
  - 로컬 Ollama 모델 연동 시 무료로 동작 가능.
  - 추후 봇에서 실시간 링크 요약이나 특정 사이트 즉석 스크래핑 기능 추가 시 검토.
