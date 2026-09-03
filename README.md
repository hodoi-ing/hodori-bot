# 🐯 hodori-bot

호도리 디스코드 대화형 비서 & 실시간 팩트 큐레이션 봇 저장소입니다.

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
