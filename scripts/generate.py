#!/usr/bin/env python3
"""
港股市场脉搏自动生成器
流程: Longbridge SDK 获取行情 → Babbage Agent 生成资讯 → 保存到 articles/
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta

# ========== 配置 ==========
BABBAGE_AGENT_URL = os.environ.get(
    "BABBAGE_AGENT_URL",
    "https://api.lbkrs.com/v1/babbage/api/agents/iyuu6dl5sbcp/runs"
)
BABBAGE_API_KEY = os.environ.get("BABBAGE_API_KEY", "")

# 港股核心标的 (按成交活跃度选取)
HK_SYMBOLS = [
    "700.HK",   # 腾讯
    "9988.HK",  # 阿里巴巴
    "9999.HK",  # 网易
    "3690.HK",  # 美团
    "1810.HK",  # 小米
    "2318.HK",  # 平安
    "941.HK",   # 中移动
    "1024.HK",  # 快手
    "9618.HK",  # 京东
    "2015.HK",  # 理想汽车
    "9888.HK",  # 百度
    "1211.HK",  # 比亚迪
    "388.HK",   # 港交所
    "2382.HK",  # 舜宇光学
    "5.HK",     # 汇丰
    "1.HK",     # 长和
    "2331.HK",  # 李宁
    "268.HK",   # 金蝶
    "6060.HK",  # 众安在线
    "981.HK",   # 中芯国际
]

HK_TIME = timezone(timedelta(hours=8))


def get_hk_now():
    """获取当前香港时间"""
    return datetime.now(HK_TIME)


def get_session_type(hk_now):
    """根据香港时间判断时段"""
    h, m = hk_now.hour, hk_now.minute
    t = h * 60 + m
    if 570 <= t < 720:      # 9:30 - 12:00
        return "盘中"
    elif 720 <= t < 780:    # 12:00 - 13:00
        return "午评"
    else:                   # 16:00 后 或 其他时间
        return "收盘"


def fetch_quotes_via_sdk():
    """通过 Longbridge Python SDK 获取实时行情"""
    try:
        from longbridge.openapi import QuoteContext, Config

        config = Config.from_env()
        ctx = QuoteContext(config)
        quotes = ctx.quote(HK_SYMBOLS)

        results = []
        for q in quotes:
            results.append({
                "symbol": q.symbol,
                "last_done": str(q.last_done),
                "change_rate": f"{float(q.change_rate) * 100:.2f}%",
                "turnover": float(q.turnover),
                "turnover_display": f"{float(q.turnover) / 1e8:.1f}亿",
            })

        results.sort(key=lambda x: x["turnover"], reverse=True)
        return results
    except Exception as e:
        print(f"[WARN] SDK quote failed: {e}", file=sys.stderr)
        return None


def fetch_quotes_via_api():
    """
    备用方案: 通过东方财富公开接口获取港股行情
    无需认证，作为 Longbridge SDK 的 fallback
    """
    try:
        url = (
            "https://push2.eastmoney.com/api/qt/clist/get"
            "?fid=f6&po=1&pz=30&pn=1&np=1"
            "&fltt=2&invt=2&fs=m:128+t:3,m:128+t:4,m:128+t:1,m:128+t:2"
            "&fields=f2,f3,f6,f12,f14"
        )
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com"
        })
        data = resp.json()

        if not data.get("data", {}).get("diff"):
            return None

        results = []
        for item in data["data"]["diff"]:
            results.append({
                "code": str(item.get("f12", "")),
                "name": str(item.get("f14", "")),
                "price": item.get("f2"),
                "change_pct": item.get("f3"),
                "turnover": item.get("f6", 0),
                "turnover_display": f"{item.get('f6', 0) / 1e8:.1f}亿",
            })

        results.sort(key=lambda x: x.get("turnover", 0), reverse=True)
        return results[:20]
    except Exception as e:
        print(f"[WARN] EastMoney fallback also failed: {e}", file=sys.stderr)
        return None


def fetch_market_data():
    """获取行情数据，优先 Longbridge SDK，失败则用东财接口"""
    print("  Trying Longbridge SDK...")
    data = fetch_quotes_via_sdk()
    if data:
        print(f"  Got {len(data)} quotes from Longbridge")
        return json.dumps(data, ensure_ascii=False, indent=2), "longbridge"

    print("  Trying EastMoney fallback...")
    data = fetch_quotes_via_api()
    if data:
        print(f"  Got {len(data)} quotes from EastMoney")
        return json.dumps(data, ensure_ascii=False, indent=2), "eastmoney"

    print("  All data sources failed")
    return None, None


def build_prompt(quote_text, news_text, session_type):
    """构建发送给 Babbage Agent 的提示词"""

    word_limit = {
        "盘中": "150-200字，硬上限200字",
        "午评": "250-300字，硬上限300字",
        "收盘": "400-500字，硬上限500字",
    }[session_type]

    top10_instruction = ""
    if session_type == "收盘":
        top10_instruction = """
收盘稿最后加TOP10：
<p><b>成交额TOP10</b></p>
<p style="font-size:14px;color:#555;line-height:2">
股票名(代码) 价格港元，涨跌X%，成交XX亿<br/>
</p>
"""

    news_section = ""
    if news_text:
        news_section = f"\n## 相关新闻\n{news_text}\n"

    prompt = f"""你是港美股券商编辑，写纯事实快讯。当前时段：{session_type}。

## 行情数据（按成交额降序）
{quote_text}
{news_section}
## 输出要求
1. 时段：{session_type}，正文{word_limit}
2. 只输出JSON，不输出其他任何文字：
{{"article":[{{"title":"港股{session_type}｜<15-25字>","abstract":"<40字内>","body":"<HTML正文>"}}]}}
3. 从数据里找今天最大的2-3件事，每件写一段，其余最后一段1-2句带过
4. 消息面融入段落，不要单独的"消息面""要闻"模块
5. 写完就结束，不要"展望""研判""关注"结尾段
6. 数字用约数："涨近2%""成交逾22亿"，不要太精确
7. 用<p>包段落，<b>加粗小标题，不用表格、bullet、markdown
{top10_instruction}
## 禁用词
情绪、承压、青睐、追捧、动能、格局、警惕、谨慎、虹吸、避风港、阴云、拖累、防御属性、风险偏好、承压消化、宜、需关注"""

    return prompt


def call_babbage_agent(prompt):
    """调用 Longbridge Babbage Agent API"""

    # 根据官方文档，使用 x-agent-key 认证
    headers = {
        "Content-Type": "application/json",
        "x-agent-key": BABBAGE_API_KEY,
    }

    payload = {
        "query": prompt,
    }

    print(f"  POST {BABBAGE_AGENT_URL}")
    resp = requests.post(
        BABBAGE_AGENT_URL,
        headers=headers,
        json=payload,
        timeout=180,
    )

    print(f"  Response status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"  Response body: {resp.text[:500]}", file=sys.stderr)

    resp.raise_for_status()

    data = resp.json()
    # Babbage API 返回格式: {outputs: {output: {text: "..."}}}
    answer = ""
    if "outputs" in data:
        output = data["outputs"]
        if isinstance(output, dict) and "output" in output:
            inner = output["output"]
            if isinstance(inner, dict) and "text" in inner:
                answer = inner["text"]
            else:
                answer = json.dumps(inner, ensure_ascii=False)
        else:
            answer = json.dumps(output, ensure_ascii=False)
    elif "answer" in data:
        answer = data["answer"]
    elif "result" in data:
        answer = data["result"]
    else:
        answer = json.dumps(data, ensure_ascii=False)

    return answer


def extract_article_json(raw_answer):
    """从 Agent 回答中提取 JSON"""
    text = raw_answer.strip()

    # 去掉 markdown code fence
    if "```json" in text:
        text = text.split("```json", 1)[1]
        text = text.split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1]
        text = text.split("```", 1)[0]

    text = text.strip()

    try:
        parsed = json.loads(text)
        return parsed
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
    return None


def save_article(article_data, raw_answer, hk_now, session_type, source):
    """保存文章到 articles/ 目录"""
    os.makedirs("articles", exist_ok=True)

    date_str = hk_now.strftime("%Y-%m-%d")
    session_map = {"盘中": "intraday", "午评": "midday", "收盘": "close"}
    session_en = session_map.get(session_type, "unknown")

    filename = f"articles/{date_str}_{session_en}.json"

    output = {
        "generated_at": hk_now.strftime("%Y-%m-%d %H:%M:%S HKT"),
        "session": session_type,
        "data_source": source,
    }

    if article_data:
        output["article"] = article_data.get("article", [article_data])
        output["status"] = "success"
    else:
        output["raw_answer"] = raw_answer
        output["status"] = "parse_failed"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  Saved: {filename}")
    return filename


def main():
    hk_now = get_hk_now()
    session_type = get_session_type(hk_now)
    print(f"{'='*50}")
    print(f"港股市场脉搏 - {hk_now.strftime('%Y-%m-%d %H:%M')} HKT")
    print(f"时段: {session_type}")
    print(f"{'='*50}")

    # Step 1: 获取行情
    print("\n[1/2] 获取行情数据...")
    quote_text, source = fetch_market_data()
    if not quote_text:
        print("ERROR: 无法获取行情数据，退出")
        sys.exit(1)

    # Step 2: 调用 Agent 生成文章
    print("\n[2/2] 调用 Babbage Agent 生成文章...")
    prompt = build_prompt(quote_text, None, session_type)

    try:
        raw_answer = call_babbage_agent(prompt)
        print(f"  Got response ({len(raw_answer)} chars)")
    except Exception as e:
        print(f"  Agent call failed: {e}", file=sys.stderr)
        save_article(None, str(e), hk_now, session_type, source)
        sys.exit(1)

    # Step 3: 解析并保存
    print("\n[保存] 解析并保存文章...")
    article_data = extract_article_json(raw_answer)
    if article_data:
        print("  JSON parsed successfully")
    else:
        print("  JSON parse failed, saving raw answer")

    filename = save_article(article_data, raw_answer, hk_now, session_type, source)

    print(f"\n{'='*50}")
    print(f"完成! 文件: {filename}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
