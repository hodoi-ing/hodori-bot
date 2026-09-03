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
    """핵심 테크 크리에이터 3인(@choi.openai, @unclejobs.ai, @h2smusic)의 스레드에서
    가장 반응(좋아요/조회수) 좋은 베스트 글을 선정하고, 글쓴이가 타래(1/8, 댓글)로 덧붙인 전체 내용을 끝까지 수집한다.
    """
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
                    # 1. 프로필 페이지에서 최근 글 목록 및 반응도(좋아요/조회수) 확인
                    page.goto(f"https://www.threads.net/@{user}", wait_until="domcontentloaded", timeout=12000)
                    page.wait_for_timeout(2000)
                    containers = page.locator('div[data-pressable-container="true"]').all()
                    candidates: list[dict] = []
                    for c in containers[:8]:
                        lines = [l.strip() for l in c.inner_text().splitlines() if l.strip()]
                        if not lines:
                            continue
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

                        links = c.locator('a').all()
                        hrefs = [l.get_attribute('href') for l in links if l.get_attribute('href') and '/post/' in l.get_attribute('href')]
                        if not hrefs:
                            continue
                        post_url = f"https://www.threads.net{hrefs[0]}"
                        candidates.append({'url': post_url, 'likes': likes})

                    if not candidates:
                        continue

                    # 2. 반응(좋아요)이 가장 높은 베스트 게시물 1개 선택
                    candidates.sort(key=lambda x: x['likes'], reverse=True)
                    best = candidates[0]
                    best_url = best['url']

                    # 3. 해당 게시물 상세 페이지로 진입하여 글쓴이가 작성한 타래(댓글 1/8 ~ n/8) 전체 수집
                    page.goto(best_url, wait_until="domcontentloaded", timeout=12000)
                    page.wait_for_timeout(2500)
                    for _ in range(3):
                        page.mouse.wheel(0, 2500)
                        page.wait_for_timeout(1000)

                    thread_containers = page.locator('div[data-pressable-container="true"]').all()
                    thread_parts: list[str] = []
                    for tc in thread_containers:
                        raw = tc.inner_text().strip()
                        if user in raw:
                            lines = [l.strip() for l in raw.splitlines() if l.strip()]
                            body = [
                                l for l in lines
                                if l != user
                                and l != '작성자'
                                and l != '·'
                                and not re.match(r'^\d+(분|시간|일|d|h|m)$', l)
                                and not l.isdigit()
                                and l not in ['고정됨', 'Translate', '번역']
                            ]
                            part_text = ' '.join(body)
                            if len(part_text) > 20 and part_text not in thread_parts:
                                thread_parts.append(part_text)

                    full_thread_content = '\n\n'.join(thread_parts) if thread_parts else '내용 추출 실패'
                    out.append({
                        'title': full_thread_content,
                        'link': best_url,
                        'likes': best['likes'],
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
    context = '\n\n'.join(
        f"[{x['source']} | 반응: {x.get('likes', 0)}]\n내용: {x['title']}\n원문링크: {x['link']}"
        for x in items
    ) or '(수집 결과 없음)'
    prompt = f"""당신은 개발자/테크 큐레이션 서비스 'GeekNews' 스타일의 전문 테크 에디터 '호도리'입니다.
스레드 3대 테크 크리에이터(@choi.openai, @unclejobs.ai, @h2smusic)의 오늘 가장 반응(좋아요/조회수) 좋은 베스트 게시물과, 글쓴이가 타래 댓글(1/8, 2/8... 등)로 덧붙여 쓴 핵심 내용을 단 하나도 누락하지 말고 완벽하게 정리하세요.

오늘 날짜: {today}
수집된 최신 포스트 및 타래 전체 내용:
{context}

출력 형식 (GeekNews 스타일):

🔥 **[Geek/Tech Hot Topics • {today}] 실시간 3대 스레드 심층 브리핑**

### 1. [핵심 주제 타이틀] (@choi.openai)
🔗 **원문 타래:** [원문 URL]
- **핵심 요약:** [전체 주장의 핵심 결론을 2문장으로 명확히 요약]
- **글쓴이 타래 본문 전체 정리:**
  1. [1번 타래 내용 요약 및 팩트]
  2. [2번 타래 내용 요약 및 팩트]
  (타래에 담긴 모든 번호/단계 내용을 빠짐없이 불릿으로 정리)

---

### 2. [핵심 주제 타이틀] (@unclejobs.ai)
🔗 **원문 타래:** [원문 URL]
- **핵심 요약:** [전체 주장의 핵심 결론을 2문장으로 명확히 요약]
- **글쓴이 타래 본문 전체 정리:**
  1. [1번 타래 내용 요약 및 팩트]
  2. [2번 타래 내용 요약 및 팩트]
  (타래에 담긴 모든 번호/단계 내용을 빠짐없이 불릿으로 정리)

---

### 3. [핵심 주제 타이틀] (@h2smusic)
🔗 **원문 타래:** [원문 URL]
- **핵심 요약:** [전체 주장의 핵심 결론을 2문장으로 명확히 요약]
- **글쓴이 타래 본문 전체 정리:**
  1. [핵심 기술/도구 스펙 및 동작 방식]
  2. [실무 적용 포인트 및 오픈소스 링크]
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
def search_shopping_deals(query: str, max_items: int = 3) -> list[dict]:
    """다나와 브릿지 AJAX를 활용해 특정 상품의 마켓별(쿠팡, G마켓, 11번가, 옥션 등) 실시간 최저가를 검색한다."""
    encoded = urllib.parse.quote_plus(query)
    search_url = f"https://search.danawa.com/dsearch.php?query={encoded}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
    try:
        req = urllib.request.Request(search_url, headers=headers)
        html = urllib.request.urlopen(req, timeout=8).read().decode("utf-8", errors="ignore")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        products: list[dict] = []
        for item in soup.select(".prod_main_info")[:max_items]:
            name_el = item.select_one(".prod_name a")
            if not name_el:
                continue
            title = name_el.get_text(strip=True)
            href = name_el.get("href", "")
            pcode_match = re.search(r"pcode=(\d+)", href)
            if not pcode_match:
                continue
            pcode = pcode_match.group(1)

            ajax_url = "https://prod.danawa.com/info/ajax/getAllPriceCompareMallList.ajax.php"
            data = urllib.parse.urlencode({"pcode": pcode}).encode("utf-8")
            ajax_headers = {
                "User-Agent": headers["User-Agent"],
                "Referer": f"https://prod.danawa.com/info/?pcode={pcode}",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
            }
            r = urllib.request.Request(ajax_url, data=data, headers=ajax_headers)
            try:
                resp = urllib.request.urlopen(r, timeout=6).read().decode("utf-8", errors="ignore")
                s_ajax = BeautifulSoup(resp, "html.parser")
                malls = []
                seen = set()
                for diff in s_ajax.select(".diff_item"):
                    mall_img = diff.select_one(".d_mall img")
                    raw_mall = mall_img.get("alt", "").strip() if mall_img else (diff.select_one(".d_mall").get_text(strip=True) if diff.select_one(".d_mall") else "")
                    mall_name = raw_mall.split("\n")[0].replace("네이버페이", "").replace("신고", "").strip()
                    if not mall_name or mall_name in seen:
                        continue
                    prc_el = diff.select_one(".prc_c, .price")
                    if not prc_el:
                        continue
                    digits = re.sub(r"[^\d]", "", prc_el.get_text())
                    if not digits:
                        continue
                    price = int(digits)
                    link_el = diff.select_one("a.link, .btn_buy a")
                    link = link_el["href"] if link_el and "href" in link_el.attrs else href
                    seen.add(mall_name)
                    malls.append({"mall": mall_name, "price": price, "link": link})
                malls.sort(key=lambda x: x["price"])
                if malls:
                    products.append({"title": title, "pcode": pcode, "url": href, "malls": malls})
            except Exception:
                pass
        return products
    except Exception as exc:
        print(f"[!] 쇼핑 검색 실패: {exc}")
        return []


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