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
TELEGRAM_BOT_TOKEN=os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
TELEGRAM_CHAT_ID=os.environ.get('TELEGRAM_CHAT_ID','').strip()
GEMINI_API_KEY=os.environ.get('GEMINI_API_KEY','').strip() or os.environ.get('GEMINI_','').strip()

ISSUE_RADARS={
 'TECH_SNS':('📱 공식 SNS & 릴리즈 속보','(공식 OR 출시 OR X OR 트위터 OR 스레드 OR release OR changelog)',10),
 'FINE_PRINT':('🔍 숨은 각주 & 쿼터/비용 정책','(사용량 OR 한도 OR quota OR 가격 OR 버그 OR 누수 OR 삭감)',9),
 'OPENSOURCE':('🛠️ 오픈소스/가중치/보안','(weights OR MoE OR LoRA OR 보안 OR 탈옥 OR 오픈소스)',8),
 'AGENT':('⚡ 에이전트 표준 & 인프라','(MCP OR WebMCP OR 에이전트 OR API OR 자동화)',8),
 'DEALS':('💰 실시간 특가 & 역대가','(역대가 OR 최저가 OR 핫딜 OR 대란 OR 특가 OR 세일 OR 쿠폰)',7),
}

def _rss(query:str)->list[dict]:
    url=f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    out=[]
    try:
        with urllib.request.urlopen(req,timeout=8) as r:
            root=ET.fromstring(r.read())
        for item in root.findall('.//item')[:8]:
            raw=item.findtext('title',''); link=item.findtext('link',''); source=item.findtext('source','') or '출처'
            title=html.unescape(raw.rsplit(' - ',1)[0].strip() if ' - ' in raw else raw)
            if link: out.append({'title':title,'link':link,'source':source})
    except Exception: pass
    return out

def harvest_5_way_radar(keyword:str)->list[dict]:
    clean=re.sub(r'^(지금|오늘|최신|실시간)\s*','',keyword).strip() or keyword
    jobs=[]
    with ThreadPoolExecutor(max_workers=5) as ex:
        for label,suffix,weight in ISSUE_RADARS.values():
            jobs.append(ex.submit(_rss,f'{clean} {suffix} when:7d'))
        rows=[]
        for i,f in enumerate(as_completed(jobs)):
            try: rows.extend(f.result())
            except Exception: pass
    seen=set(); filtered=[]
    for row in rows:
        if row['link'] in seen: continue
        seen.add(row['link']); filtered.append(row)
    return filtered[:12]

def generate_gemini_card_news(topic:str,items:list[dict])->str:
    today=datetime.now().strftime('%m월 %d일')
    context='\n'.join(f"- [{x['source']}] {x['title']} ({x['link']})" for x in items) or '(수집 결과 없음)'
    prompt=f"""당신은 '도리'다. 질문을 최신 팩트 중심으로 분석한다. 사실과 추정을 구분하고 근거 없는 수치는 만들지 않는다.\n질문: {topic}\n오늘: {today}\n자료:\n{context}\n\n출력:\n🔥 [{topic} • {today}]\n\n📌 [메인 본문]\n핵심 팩트와 반전 포인트를 3~5문장.\n\n💬 [댓글 1 | 기술/메커니즘]\n왜 이런 변화가 생겼는지 설명.\n\n💬 [댓글 2 | 실사용 영향]\n수치나 비용은 검증된 자료만 환산.\n\n💬 [댓글 3 | 공식 출처]\n대표 원문 URL 1개."""
    if not GEMINI_API_KEY: return _offline(topic,items)
    payload={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.3,'maxOutputTokens':4096}}
    for model in ('gemini-2.5-flash','gemini-flash-latest'):
        try:
            url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}'
            req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=20) as r: data=json.loads(r.read().decode())
            return html.unescape(data['candidates'][0]['content']['parts'][0]['text']).strip()
        except Exception: continue
    return _offline(topic,items)

def _offline(topic,items):
    top=items[0] if items else {'title':'관련 최신 데이터 없음','link':''}
    return f"🔥 [{topic} 실시간 브리핑]\n\n📌 [메인 본문]\n현재 수집 가능한 최신 자료 기준으로 다음 신호가 확인됩니다.\n\n💬 [댓글 1 | 기술/메커니즘]\n{top['title']}\n\n💬 [댓글 2 | 실사용 영향]\n원문과 추가 독립 출처를 함께 확인해야 합니다.\n\n💬 [댓글 3 | 공식 출처]\n🔗 {top['link']}"

def run_full_doribogo(topic:str)->str:
    items=harvest_5_way_radar(topic)
    return generate_gemini_card_news(topic,items)

def send_discord(title,text):
    if not DISCORD_WEBHOOK_URL: return False
    payload={'username':'dori bot','embeds':[{'title':title,'description':text[:4000],'color':0xFF6B00}]}
    try:
        req=urllib.request.Request(DISCORD_WEBHOOK_URL,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r: return r.status in (200,204)
    except Exception: return False

def send_telegram(text,chat_id=None):
    target=chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not target: return False
    url=f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload={'chat_id':target,'text':text,'disable_web_page_preview':True}
    try:
        req=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r: return r.status==200
    except Exception: return False

def send_broadcast(title,text,chat_id=None):
    return send_discord(title,text) or send_telegram(f'**{title}**\n\n{text}',chat_id)
