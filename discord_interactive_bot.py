"""🐯 hodori bot - 자연어 대화형 디스코드 비서 (discord.py)

💡 자연어 호출 방식:
• "도리야 [검색어/질문]" ➔ 봇이 알아서 리서치인지 일반 질문인지 판단해 즉시 답변!
  예) 도리야 백컨트리 360 특가 찾아줘
  예) 도리야 중국 AI 모델 최신 소식 정리해줘
  예) 도리야 파이썬으로 엑셀 다루는 코드 짜줘
  예) 도리야 오늘 저녁 메뉴 추천해줘
• @hodori bot 멘션 후 질문도 가능!
• 기존 명령어(!도리, !ai)도 100% 호환 지원
"""

import os
import sys
import time
import json
import asyncio
import urllib.request
import html
import re
from datetime import datetime, timezone

try:
    import discord
    from discord.ext import commands, tasks
except ImportError:
    print("[!] discord.py가 설치되지 않았습니다.")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import doribogo_bot

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
DISCORD_CHANNEL_ID = os.environ.get("DISCORD_CHANNEL_ID", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GEMINI_", "").strip() or "AIzaSyAXiI8a1MVwfegW5cz7MxfLbGKdv8amz-4"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

WATCH_KEYWORDS = ["백컨트리 360", "캠핑 텐트 특가"]


@bot.event
async def on_ready():
    print("=" * 60)
    print(f"🐯 hodori bot 자연어 대화 비서 가동: {bot.user.name} ({bot.user.id})")
    print("• 자연어 호출: '도리야 [질문]', '호도리야 [질문]', @봇 멘션")
    print("• 명령어 접두사: !도리, !ai, !도움말")
    print("=" * 60)
    if not auto_radar_loop.is_running():
        auto_radar_loop.start()


# --- 자연어 메시지 리스너 ("도리야 ~", "호도리야 ~", @멘션) ---
@bot.event
async def on_message(message):
    # 봇 자신의 메시지는 무시
    if message.author == bot.user:
        return

    content = message.content.strip()
    is_triggered = False
    cleaned_query = ""

    # 1. "도리야", "호도리야", "도리", "호도리" 로 시작하는지 검사
    pattern = r"^(도리야|호도리야|도리|호도리|dori)\s*[,~!\?]?\s*(.*)"
    match = re.match(pattern, content, re.IGNORECASE)

    if match:
        is_triggered = True
        cleaned_query = match.group(2).strip()
    elif bot.user in message.mentions:
        is_triggered = True
        cleaned_query = re.sub(r"<@!?[0-9]+>", "", content).strip()

    if is_triggered:
        if not cleaned_query or cleaned_query in ["안녕", "ㅎㅇ", "하이", "도움말", "help"]:
            await message.channel.send(
                f"🐯 안녕하세요, {message.author.mention}님! 무엇을 도와드릴까요?\n\n"
                "💡 **이렇게 말씀해 보세요:**\n"
                "• `도리야 백컨트리 360 특가 찾아줘` ➔ 5대 레이더 실시간 리서치\n"
                "• `도리야 중국 AI 모델 최신 이슈 알려줘` ➔ 4단계 팩트 브리핑\n"
                "• `도리야 파이썬 비동기 코드 예제 짜줘` ➔ 코딩 & AI 비서 답변\n"
                "• `도리야 오늘 저녁 메뉴 추천해줘` ➔ 자유 AI 대화"
            )
            return

        # 지능형 라우팅: 리서치/핫딜/뉴스 질문인지, 일반 대화/코딩인지 판단
        is_research_intent = any(w in cleaned_query for w in [
            "특가", "가격", "텐트", "할인", "대란", "구매", "장비", "이슈", "뉴스", "속보", "최신", "시세", "알아봐", "찾아봐", "정리해줘", "소식"
        ])

        if is_research_intent:
            await handle_doribogo_research(message.channel, cleaned_query)
        else:
            await handle_ai_chat(message.channel, cleaned_query)
        return

    # 기존 명령어(!도리, !ai 등) 처리
    await bot.process_commands(message)


async def handle_doribogo_research(channel, keyword):
    """도리보고 5대 레이더 4단계 팩트 리포트 처리."""
    loading_msg = await channel.send(f"🔍 **[{keyword}]** 5대 레이더 실시간 수집 및 팩트 분석 중... ⏳")
    try:
        loop = asyncio.get_event_loop()
        card_news = await loop.run_in_executor(None, doribogo_bot.run_full_doribogo, keyword)
        today_str = datetime.now().strftime("%m월 %d일")

        embed = discord.Embed(
            title=f"⚡ [{today_str} 실시간 이슈] {keyword}",
            description=card_news,
            color=0xFF6B00
        )
        embed.set_footer(text=f"hodori bot • {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        await loading_msg.delete()
        await channel.send(embed=embed)
    except Exception as e:
        await loading_msg.edit(content=f"❌ **[{keyword}]** 분석 중 오류 발생: {e}")


async def handle_ai_chat(channel, query):
    """Gemini 2.5 Flash 자유 대화 및 코딩/번역 비서 처리."""
    loading_msg = await channel.send(f"🧠 **[{query[:30]}...]** 답변 작성 중... ⏳")
    try:
        loop = asyncio.get_event_loop()
        answer = await loop.run_in_executor(None, call_gemini_general, query)
        await loading_msg.delete()

        if len(answer) <= 2000:
            embed = discord.Embed(
                title=f"💡 [AI 답변] {query[:40]}",
                description=answer,
                color=0x3B82F6
            )
            embed.set_footer(text="hodori bot • Powered by Gemini 2.5 Flash")
            await channel.send(embed=embed)
        else:
            chunks = [answer[i:i+1900] for i in range(0, len(answer), 1900)]
            for idx, ch in enumerate(chunks, 1):
                await channel.send(f"**[답변 {idx}/{len(chunks)}]**\n{ch}")
    except Exception as e:
        await loading_msg.edit(content=f"❌ 답변 생성 중 오류 발생: {e}")


def call_gemini_general(prompt: str) -> str:
    """Gemini 2.5 Flash 범용 질의응답."""
    system_instruction = (
        "당신은 친절하고 유능하며 명쾌한 AI 수석 비서 '호도리봇(hodori bot)'입니다. "
        "사용자의 질문에 대해 핵심을 찌르는 친절하고 전문적인 한국어로 답변하세요. "
        "코딩 질문에는 실행 가능한 깔끔한 코드 블록과 핵심 해설을 제공하세요."
    )
    
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"[시스템 지침: {system_instruction}]\n\n사용자 질문: {prompt}"}]}
        ],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 8192,
            "thinkingConfig": {"thinkingBudget": 0}
        }
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        res_data = json.loads(resp.read().decode("utf-8"))
        return res_data["candidates"][0]["content"]["parts"][0]["text"].strip()


# --- 기존 명령어 호환 (!도리, !ai, !도움말) ---
@bot.command(name="도리", aliases=["dori", "doribogo"])
async def dori_cmd(ctx, *, keyword: str = ""):
    if not keyword:
        await ctx.send("🐯 검색할 키워드를 입력해주세요! (예: `!도리 백컨트리 360` 또는 `도리야 백컨트리 360`)")
        return
    await handle_doribogo_research(ctx.channel, keyword)


@bot.command(name="ai", aliases=["질문", "q", "ask"])
async def ai_cmd(ctx, *, query: str = ""):
    if not query:
        await ctx.send("🐯 질문을 입력해주세요! (예: `!ai 파이썬 코드 짜줘` 또는 `도리야 파이썬 코드 짜줘`)")
        return
    await handle_ai_chat(ctx.channel, query)


@bot.command(name="도움말", aliases=["help", "명령어"])
async def help_cmd(ctx):
    embed = discord.Embed(
        title="🐯 hodori bot 사용 안내",
        description=(
            "**💡 자연어 대화 (느낌표 없이 편하게 부르기)**\n"
            "• `도리야 [검색어/질문]`\n"
            "• `호도리야 [검색어/질문]`\n"
            "• `@hodori bot [질문]`\n\n"
            "**📌 명령어 방식**\n"
            "• `!도리 [키워드]` : 5대 레이더 실시간 리서치 + 4단계 팩트 리포트\n"
            "• `!ai [질문]` : Gemini AI 자유 대화, 코딩, 번역 비서\n\n"
            "**⏰ 30분 정기 브리핑**\n"
            "• 컴퓨터를 꺼도 30분마다 주요 감시 핫딜/뉴스가 자동 발송됩니다."
        ),
        color=0x10B981
    )
    embed.set_footer(text="hodori bot • 만능 개인 비서")
    await ctx.send(embed=embed)


@tasks.loop(minutes=30)
async def auto_radar_loop():
    """30분 주기 정기 자동 브리핑."""
    if not DISCORD_CHANNEL_ID:
        return

    try:
        channel = bot.get_channel(int(DISCORD_CHANNEL_ID))
        if not channel:
            return

        today_str = datetime.now().strftime("%m월 %d일")
        loop = asyncio.get_event_loop()

        for kw in WATCH_KEYWORDS:
            card = await loop.run_in_executor(None, doribogo_bot.run_full_doribogo, kw)
            embed = discord.Embed(
                title=f"⚡ [{today_str} 실시간 이슈] {kw}",
                description=card,
                color=0xFF6B00
            )
            embed.set_footer(text=f"hodori bot • {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            await channel.send(embed=embed)
            await asyncio.sleep(2)

    except Exception as e:
        print(f"[!] 30분 정기 브리핑 에러: {e}")


@auto_radar_loop.before_loop
async def before_loop():
    await bot.wait_until_ready()


def main():
    if not DISCORD_BOT_TOKEN:
        print("❌ DISCORD_BOT_TOKEN이 설정되지 않았습니다.")
        sys.exit(1)

    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
