"""🐯 Doribogo v6.x - 5-Way Radar research bot.

This standalone deployment mirrors the current GJC Doribogo direction:
5-Way Harvest -> dedup/recency -> Gemini 4-stage report -> Discord/Telegram.
"""
from __future__ import annotations
import os, json, html, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DISCORD_WEBHOOK_URL=os.environ.get('DISCORD_WEBHOOK_URL','').strip()
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip() or os.environ.get('GEMINI_', '').strip() or 'AIzaSyAXiI8a1MVwfegW5cz7MxfLbGKdv8amz-4'

# KST 정기 AI 브리핑 슬롯: 아침 09:00 / 저녁 18:00
BRIEFING_SLOT_HOURS = (9, 18)
# 슬롯 시작 후 몇 분까지 발송 기회를 허용할지 (프로세스 재시작 지연 대비)
BRIEFING_SLOT_GRACE_MINUTES = 4


def is_briefing_slot(now: datetime) -> bool:
    """정기 브리핑 시각인지 판단. now 는 KST tz-aware datetime 을 넘긴다."""
    return now.hour in BRIEFING_SLOT_HOURS and now.minute <= BRIEFING_SLOT_GRACE_MINUTES

ISSUE_RADARS = {
    'TECH_RELEASE': (
        '🚀 글로벌 릴리즈 & 신기능 속보',
        '(OpenAI OR Anthropic OR Claude OR Gemini OR DeepSeek OR Vercel) (출시 OR 공개 OR 릴리즈 OR "release notes" OR update OR API) when:3d',
    ),
    'PRACTICAL_TOOLS': (
        '🛠️ 실무 개발 도구 & 프롬프트/MCP',
        '(MCP OR "Claude Code" OR Codex OR "Playwright" OR LangChain OR LlamaIndex OR Agent) (공개 OR 가이드 OR "github" OR 도구) when:3d',
    ),
    'BENCH_SECURITY': (
        '⚡ 벤치마크 & 탈옥/보안/정책',
        '(benchmark OR jailbreak OR safety OR token OR quota OR 비용 OR 누수 OR 가격) (Claude OR GPT OR Gemini OR DeepSeek) when:3d',
    ),
    'OPEN_WEIGHTS': (
        '🤖 오픈소스 가중치 & 로컬 LLM',
        '(Ollama OR "Hugging Face" OR Qwen OR Llama OR vLLM OR Mistral) (가중치 OR weights OR 오픈소스 OR 로컬) when:3d',
    ),
}

THREADS_CREATORS = ["choi.openai", "unclejobs.ai", "h2smusic"]


def _fetch_threads_creators() -> list[dict]:
    """핵심 테크 크리에이터 3인(@choi.openai, @unclejobs.ai, @h2smusic)의 최신 스레드를 수집한다."""
    out: list[dict] = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='ko-KR',
            )
            page = context.new_page()
            for user in THREADS_CREATORS:
                try:
                    page.goto(f"https://www.threads.net/@{user}", wait_until="domcontentloaded", timeout=12000)
                    page.wait_for_timeout(2000)
                    containers = page.locator('div[data-pressable-container="true"]').all()
                    for c in containers[:3]:
                        txt = c.inner_text().strip().replace("\n", " ")
                        if len(txt) > 25:
                            # 고정글 표시 제거 및 앞단 정리
                            cleaned = re.sub(r'^(고정됨\s*)?', '', txt)
                            out.append({
                                'title': cleaned[:160],
                                'link': f"https://www.threads.net/@{user}",
                                'source': f"Threads @{user}",
                            })
                except Exception as user_err:
                    print(f"[!] 스레드 @{user} 수집 예외: {user_err}")
            context.close()
            browser.close()
    except Exception as exc:
        print(f"[!] 스레드 크리에이터 수집 실패: {exc}")
    return out


def _fetch_hn_show_tools() -> list[dict]:
    """Hacker News의 Show HN에서 최신 AI/에이전트 실무 도구를 수집한다."""
    try:
        url = "https://news.ycombinator.com/show"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=6).read().decode('utf-8', errors='ignore')
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        tools: list[dict] = []
        for row in soup.select('.athing')[:20]:
            a = row.select_one('.titleline > a')
            if not a:
                continue
            title = a.get_text(strip=True)
            link = a.get('href', '')
            if any(k in title.lower() for k in ['ai', 'llm', 'agent', 'mcp', 'claude', 'gpt', 'model', 'eval']):
                tools.append({'title': title.replace('Show HN: ', '[Show HN] '), 'link': link, 'source': 'HackerNews'})
        return tools[:5]
    except Exception:
        return []

def _rss(query: str) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    out = []
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            root = ET.fromstring(r.read())
        for item in root.findall('.//item')[:8]:
            raw = item.findtext('title', '')
            link = item.findtext('link', '')
            source = item.findtext('source', '') or '출처'
            title = html.unescape(raw.rsplit(' - ', 1)[0].strip() if ' - ' in raw else raw)
            # 잡다한 일반 주가/학회/정치 기사 필터링
            if any(bad in title for bad in ['주가', '상승세', '테마주', '수혜주', '협약', '캠프', '장학금']):
                continue
            if link:
                out.append({'title': title, 'link': link, 'source': source})
    except Exception:
        pass
    return out


def harvest_5_way_radar(keyword: str) -> list[dict]:
    clean = re.sub(r'^(지금|오늘|최신|실시간)\s*', '', keyword).strip() or keyword
    jobs = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for label, query in ISSUE_RADARS.values():
            if any(k in clean for k in ['브리핑', '이슈', '소식', '릴리즈', '도구']):
                search_term = query
            else:
                search_term = f"{clean} (출시 OR 공개 OR API OR 깃허브 OR 업데이트) when:7d"
            jobs.append(ex.submit(_rss, search_term))
        jobs.append(ex.submit(_fetch_hn_show_tools))
        jobs.append(ex.submit(_fetch_threads_creators))
        rows = []
        for f in as_completed(jobs):
            try:
                rows.extend(f.result())
            except Exception:
                pass
    seen = set()
    # 핵심 3인방(@choi.openai, @unclejobs.ai, @h2smusic) 글과 실무 도구를 상위로 우선 배치
    threads_items = [r for r in rows if 'Threads' in r.get('source', '')]
    other_items = [r for r in rows if 'Threads' not in r.get('source', '')]
    combined = threads_items + other_items

    filtered = []
    for row in combined:
        if row['link'] in seen:
            continue
        seen.add(row['link'])
        filtered.append(row)
    return filtered[:15]


def generate_gemini_card_news(topic: str, items: list[dict]) -> str:
    today = datetime.now().strftime('%m월 %d일')
    context = '\n'.join(f"- [{x['source']}] {x['title']} ({x['link']})" for x in items) or '(수집 결과 없음)'
    prompt = f"""당신은 @choi.openai 스타일의 실무 중심 테크/AI 인사이트 에디터 '호도리'입니다.
일반 뉴스나 주가, 뻔한 이야기는 일절 배제하고, 엔지니어와 실무자가 지금 당장 가져다 쓸 수 있는 핵심 기술 변화와 신규 릴리즈만 다룹니다.

주제: {topic}
오늘: {today}
참고자료:
{context}

아래 형식에 맞춰 간결하고 임팩트 있게 작성하세요.

🔥 [{topic} • {today} 실무 테크 브리핑]

📌 [1. 무엇이 나왔는가? (한 줄 정의)]
어떤 도구/모델/기능이 공개되었는지 군더더기 없이 명확하게 설명.

⚙️ [2. 실무에서 어떻게 쓰는가? (작동 방식 & 핵심 변화)]
• 어떻게 작동하는지(설치, 연동, 프롬프트 방식 등)
• 기존 방식 대비 무엇이 달라졌는지 실질적인 비교
• 엔지니어/실무자가 주의해야 할 점이나 제약사항

🔗 [3. 공식 링크 및 깃허브]
자료 중 가장 신뢰도 높은 원문이나 GitHub 저장소 링크 1~2개 제시.
"""
    if not GEMINI_API_KEY:
        return _offline(topic, items)
    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.25, 'maxOutputTokens': 4096},
    }
    for model in ('gemini-3.7-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash'):
        try:
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}'
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            return html.unescape(data['candidates'][0]['content']['parts'][0]['text']).strip()
        except Exception as exc:
            print(f"[!] Gemini generation error ({model}): {exc}")
            continue
    return _offline(topic, items)


def _offline(topic: str, items: list[dict]) -> str:
    top = items[0] if items else {'title': '관련 최신 기술 데이터 없음', 'link': ''}
    return (
        f"🔥 [{topic} 실무 테크 브리핑]\n\n"
        f"📌 [1. 무엇이 나왔는가?]\n{top['title']}\n\n"
        f"⚙️ [2. 핵심 변화 & 실무 포인트]\n• 원문 공식 릴리즈 노트를 참고하여 실무 검증이 필요합니다.\n\n"
        f"🔗 [3. 공식 링크]\n🔗 {top['link']}"
    )


def run_full_doribogo(topic: str) -> str:
    items = harvest_5_way_radar(topic)
    return generate_gemini_card_news(topic, items)

def send_discord(title,text):
    if not DISCORD_WEBHOOK_URL: return False
    payload={'username':'hodori bot','avatar_url':'https://avatars.githubusercontent.com/u/274787659?v=4','embeds':[{'title':title,'description':text[:4000],'color':0xFF6B00}]}
    try:
        req=urllib.request.Request(DISCORD_WEBHOOK_URL,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r: return r.status in (200,204)
    except Exception: return False

def send_broadcast(title,text,chat_id=None):
    return send_discord(title,text)