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
    """핵심 테크 크리에이터 3인(@choi.openai, @unclejobs.ai, @h2smusic)의 스레드에서 가장 반응(좋아요/댓글) 좋은 대표 이슈를 그대로 추출한다."""
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
                    user_posts: list[dict] = []
                    for c in containers[:6]:
                        lines = [l.strip() for l in c.inner_text().splitlines() if l.strip()]
                        if not lines:
                            continue
                        # 좋아요 수 추출 (마지막 줄 부근 숫자 파싱)
                        likes = 0
                        for l in reversed(lines[-5:]):
                            if l.isdigit():
                                likes = int(l)
                                break
                            elif re.match(r'^\d+(\.\d+)?[Kk천만]?$', l):
                                val = l.replace('K', '').replace('k', '').replace('천', '')
                                try:
                                    likes = int(float(val) * 1000)
                                except Exception:
                                    pass
                                break

                        # 게시물 링크
                        links = c.locator('a').all()
                        hrefs = [l.get_attribute('href') for l in links if l.get_attribute('href') and '/post/' in l.get_attribute('href')]
                        post_url = f"https://www.threads.net{hrefs[0]}" if hrefs else f"https://www.threads.net/@{user}"

                        # 본문 정리 (유저명, 시간단위, 고정표시 제외)
                        body_lines = [
                            l for l in lines
                            if l != user
                            and not l.isdigit()
                            and not re.match(r'^\d+(분|시간|일|d|h|m)$', l)
                            and l not in ['고정됨', 'Translate', '번역']
                        ]
                        content = ' '.join(body_lines)
                        if len(content) > 30:
                            user_posts.append({
                                'title': content[:300],
                                'link': post_url,
                                'likes': likes,
                                'source': f"Threads @{user}",
                            })

                    # 반응(좋아요)이 가장 높은 베스트 글 1~2건 선정
                    if user_posts:
                        user_posts.sort(key=lambda x: x['likes'], reverse=True)
                        out.extend(user_posts[:2])
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
    context = '\n\n'.join(
        f"[{x['source']} | 반응: {x.get('likes', 0)}]\n내용: {x['title']}\n원문링크: {x['link']}"
        for x in items
    ) or '(수집 결과 없음)'
    prompt = f"""당신은 테크 크리에이터 원문 전달 큐레이터 '호도리'입니다.
3대 테크 크리에이터(@choi.openai, @unclejobs.ai, @h2smusic)가 작성한 원문 내용을 임의로 생략하거나 줄이지 말고, 크리에이터가 쓴 실제 글 본문 전체를 인용구(>) 형식으로 그대로 담아서 전달하세요.

오늘 날짜: {today}
수집된 최신 포스트 원문:
{context}

출력 형식 (원문 본문 문장을 생략하지 말고 전부 출력하세요):

1️⃣ **[@choi.openai] [게시글 핵심 주제]**
> [작성자가 쓴 실제 본문 전체를 그대로 줄바꿈 유지하여 인용구로 출력]
🔗 **스레드 원문 보기:** [원문 URL]

---

2️⃣ **[@unclejobs.ai] [게시글 핵심 주제]**
> [작성자가 쓴 실제 본문 전체를 그대로 줄바꿈 유지하여 인용구로 출력]
🔗 **스레드 원문 보기:** [원문 URL]

---

3️⃣ **[@h2smusic] [게시글 핵심 주제]**
> [작성자가 쓴 실제 본문 전체를 그대로 줄바꿈 유지하여 인용구로 출력]
🔗 **스레드 원문 보기:** [원문 URL]
"""
    if not GEMINI_API_KEY:
        return _offline(topic, items)
    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.2, 'maxOutputTokens': 4096},
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