import os
import re
import html
import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import requests

API_KEY = os.environ.get("GEMINI_API_KEY")
TW_TZ = timezone(timedelta(hours=8))
DATA_FILE = "news_history.json"

# 主分析模型設定（每天僅跑 3 次；若未來想更進一步提升文筆可改為 gemini-2.5-pro）
TOPIC_MODEL = "gemini-2.5-flash"
ANALYSIS_MODEL = "gemini-2.5-flash"
ANALYSIS_THINKING_BUDGET = 4096

# 內文抓取上限（跨 4 陣營各最多抓 2 篇，兼顧深度與執行速度）
MAX_FULLTEXT_PER_CAMP = 2
MAX_FULLTEXT_TOTAL = 8
MAX_EXCERPT_CHARS = 750

# ==========================================
# 純新聞轉載入口黑名單（只保留原始發稿原生媒體）
# ==========================================
AGGREGATOR_BLACKLIST = [
    "LINE TODAY", "LINE新聞", "Yahoo", "MSN", "PChome",
    "蕃新聞", "Match生活網", "HiNet", "Hinet"
]

# 較友善、易成功抓取純文字內文的台灣主流媒體網域（優先抽取內文）
SCRAPER_FRIENDLY_DOMAINS = [
    "cna.com.tw", "news.pts.org.tw", "rti.org.tw",
    "news.ltn.com.tw", "udn.com", "ettoday.net",
    "nownews.com", "news.tvbs.com.tw", "setn.com",
    "ftvnews.com.tw", "newtalk.tw", "cnews.com.tw",
    "taisounds.com", "chinatimes.com", "storm.mg",
    "mirrormedia.mg", "upmedia.mg", "rwnews.tw"
]

# 過濾網頁雜訊與版權頁尾段落
BOILERPLATE_HINTS = [
    "版權所有", "copyright", "下載app", "下載 app", "加入會員", "訂閱",
    "延伸閱讀", "推薦閱讀", "看更多", "相關新聞", "點我", "追蹤我們",
    "cookie", "隱私權", "授權轉載", "未經授權", "更多新聞", "精彩內容",
    "按讚", "加入line", "官方line", "掃描qr"
]

# ==========================================
# 台灣主要原生媒體預設政治光譜字典（公開透明、持續滾動修正）
# ==========================================
MEDIA_SPECTRUM = {
    # 泛藍／偏在野監督／兩岸溫和派傾向
    "聯合報": "泛藍傾向（傳統四大報，偏重在野監督與體制穩定）",
    "聯合新聞網": "泛藍傾向（聯合報系）",
    "udn": "泛藍傾向（聯合報系）",
    "UDN": "泛藍傾向（聯合報系）",
    "經濟日報": "泛藍／財經務實傾向（聯合報系）",
    "中國時報": "泛藍／親中傾向（旺中集團，鮮明監督執政黨）",
    "中時新聞網": "泛藍／親中傾向（旺中集團）",
    "工商時報": "泛藍／財經產業界傾向（旺中集團）",
    "中天新聞": "深藍／強烈監督執政黨傾向（旺中集團）",
    "中天新聞網": "深藍／強烈監督執政黨傾向（旺中集團）",
    "中視": "泛藍傾向（旺中集團旗下老三台）",
    "TVBS": "泛藍／商業綜合傾向（關注藍營動態與民生監督）",
    "TVBS新聞網": "泛藍／商業綜合傾向",
    "風傳媒": "泛藍白／批判執政黨傾向（政論與幕後分析居多）",
    "梅花新聞網": "泛藍傾向",
    "中廣新聞網": "泛藍傾向",

    # 泛綠／偏執政本土／抗中保台傾向
    "自由時報": "泛綠／本土派傾向（傳統四大報，鮮明支持本土執政與抗中）",
    "三立新聞網": "泛綠傾向（親執政黨，常聚焦批判藍白陣營）",
    "三立新聞": "泛綠傾向",
    "民視新聞網": "泛綠／深綠本土傾向（鮮明支持台灣主體性與執政黨）",
    "民視新聞": "泛綠／深綠本土傾向",
    "新頭殼": "泛綠／本土派傾向（Newtalk，關注政黨攻防）",
    "Newtalk": "泛綠／本土派傾向",
    "太報": "泛綠／本土自由派傾向",
    "鏡週刊": "偏綠／揭弊調查傾向（常進行政商黑幕調查報導）",
    "鏡報": "偏綠／揭弊與政經網媒（鏡傳媒體系）",
    "放言": "泛綠傾向",
    "民報": "泛綠／本土派傾向",

    # 泛白／第三勢力或高度關注民眾黨動態
    "民眾之聲": "泛白傾向（民眾黨官方新媒體）",
    "匯流新聞網": "偏泛白／第三勢力傾向（CNEWS，高比例報導民眾黨與國會攻防）",
    "CNEWS": "偏泛白／第三勢力傾向",

    # 公媒／通訊社／獨立調查與商業綜合平台（不預設絕對中立，依當篇用詞實質檢驗）
    "中央社": "公媒／國家通訊社（CNA，以官方公開資訊與平實陳述為主，仍須檢視單篇框架）",
    "公視新聞網": "公媒／公共媒體（PTS，公共化電視台，仍須檢視單篇選題與引述平衡）",
    "中央廣播電臺": "公媒／國家廣播電台（央廣）",
    "央廣": "公媒／國家廣播電台",
    "報導者": "獨立深度調查媒體（非營利獨立媒體）",
    "華視": "公媒／公共化媒體",
    "台視": "商業綜合／傳統老三台",
    "鏡新聞": "商業綜合／新聞台（仍須依當篇用詞判讀）",
    "ETtoday": "商業綜合／流量導向（即時快訊與網路輿情為主，立場視議題而定）",
    "NOWnews": "商業綜合／立場視議題而定",
    "壹蘋新聞網": "商業綜合／揭弊與民生導向",
    "菱傳媒": "商業綜合／政壇調查與民調導向",
    "上報": "商業綜合／政經幕後與國安評論導向",
    "信傳媒": "商業綜合／財經與政壇觀察導向"
}

GREEN_KEYS = [
    "泛綠", "深綠", "偏綠", "自由", "三立", "民視",
    "新頭殼", "Newtalk", "太報", "鏡週刊", "鏡報", "放言", "民報"
]
BLUE_KEYS = [
    "泛藍", "深藍", "親中", "聯合", "UDN", "udn", "中時", "中國時報",
    "中天", "TVBS", "風傳媒", "中視", "中廣", "工商", "經濟日報", "梅花"
]
WHITE_KEYS = ["泛白", "民眾", "匯流", "CNEWS"]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
}


def is_aggregator(source_name):
    s_lower = (source_name or "").lower()
    return any(b.lower() in s_lower for b in AGGREGATOR_BLACKLIST)


def get_media_bias_tag(source_name):
    for key, bias_desc in MEDIA_SPECTRUM.items():
        if key in source_name:
            return bias_desc
    return "未預設光譜之原生媒體（請依標題與內文用詞直接判定）"


def classify_camp_bucket(source_name, bias_tag=""):
    text = f"{source_name} {bias_tag}"
    if any(k in text for k in GREEN_KEYS):
        return "泛綠傾向"
    if any(k in text for k in BLUE_KEYS):
        return "泛藍傾向"
    if any(k in text for k in WHITE_KEYS):
        return "泛白／第三勢力"
    return "公媒／通訊社與商業綜合"


def unwrap_bing_url(bing_link):
    """從 Bing News 跳轉連結中直接萃取出未加密的媒體原始網址。"""
    try:
        parsed = urllib.parse.urlparse(bing_link)
        qs = urllib.parse.parse_qs(parsed.query)
        if "url" in qs and qs["url"]:
            return qs["url"][0]
    except Exception:
        pass
    return bing_link


def clean_html_text(raw):
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_rss(query, max_items=45):
    encoded = urllib.parse.quote(query)
    url = (
        f"https://news.google.com/rss/search?"
        f"q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    )
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"Google RSS 抓取異常 ({query}): {e}")
        return []

    articles = []
    for item in root.findall(".//item"):
        source = item.find("source").text if item.find("source") is not None else "未知媒體"
        if is_aggregator(source):
            continue

        title = item.find("title").text if item.find("title") is not None else ""
        link = item.find("link").text if item.find("link") is not None else ""
        pub_raw = item.find("pubDate").text if item.find("pubDate") is not None else ""
        try:
            dt = parsedate_to_datetime(pub_raw).astimezone(TW_TZ)
            ts_str = dt.strftime("%Y-%m-%d %H:%M")
            ts_val = dt.timestamp()
        except Exception:
            ts_str = "未知時間"
            ts_val = 0

        articles.append({
            "source": source.strip(),
            "bias_tag": get_media_bias_tag(source),
            "title": title.strip(),
            "link": link.strip(),
            "direct_url": "",
            "snippet": "",
            "time_str": ts_str,
            "timestamp": ts_val
        })
        if len(articles) >= max_items:
            break
    return articles


def fetch_bing_rss(query, max_items=25):
    """補充抓取 Bing News 台灣繁中 RSS，取得未加密原始網址與導言摘要。"""
    encoded = urllib.parse.quote(query)
    url = f"https://www.bing.com/news/search?q={encoded}&format=rss&mkt=zh-TW&setlang=zh-Hant"
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"Bing RSS 抓取異常 ({query}): {e}")
        return []

    now_ts = time.time()
    max_age_sec = 7 * 24 * 3600
    articles = []

    for item in root.findall(".//item"):
        source = ""
        for child in item:
            if child.tag.lower().endswith("source") and child.text:
                source = child.text.strip()
                break
        if not source:
            source = "未知媒體"
        if is_aggregator(source):
            continue

        title = (item.findtext("title") or "").strip()
        raw_link = (item.findtext("link") or "").strip()
        direct_url = unwrap_bing_url(raw_link)
        snippet = clean_html_text(item.findtext("description") or "")[:220]
        pub_raw = (item.findtext("pubDate") or "").strip()

        try:
            dt = parsedate_to_datetime(pub_raw).astimezone(TW_TZ)
            ts_str = dt.strftime("%Y-%m-%d %H:%M")
            ts_val = dt.timestamp()
        except Exception:
            ts_str = "未知時間"
            ts_val = 0

        if ts_val > 0 and (now_ts - ts_val) > max_age_sec:
            continue

        articles.append({
            "source": source,
            "bias_tag": get_media_bias_tag(source),
            "title": f"{title} - {source}" if source not in title else title,
            "link": direct_url,
            "direct_url": direct_url,
            "snippet": snippet,
            "time_str": ts_str,
            "timestamp": ts_val
        })
        if len(articles) >= max_items:
            break
    return articles


def fetch_topic_articles(hot_topic, pool):
    """
    結合 Google News RSS 與 Bing News RSS 抓取原生媒體報導，
    合併時優先保留未加密原始網址與導言摘要，以供後續跨陣營內文抽取。
    """
    words = [w for w in hot_topic.split() if w]
    short_topic = " ".join(words[:2]) if len(words) >= 2 else hot_topic

    queries_to_try = [f"{hot_topic} when:24h"]
    if short_topic != hot_topic:
        queries_to_try.append(f"{short_topic} when:24h")
    queries_to_try.append(f"{short_topic} when:48h")
    queries_to_try.append(f"{short_topic} when:72h")

    merged_map = {}

    def merge_batch(batch):
        for a in batch:
            clean_title = a["title"].split(" - ")[0].strip()
            dedup_key = (a["source"], clean_title[:16])
            if dedup_key not in merged_map:
                merged_map[dedup_key] = a
            else:
                existing = merged_map[dedup_key]
                # 若新來源具備直連網址或導言摘要，補齊進既有紀錄
                if not existing.get("direct_url") and a.get("direct_url"):
                    existing["direct_url"] = a["direct_url"]
                if not existing.get("snippet") and a.get("snippet"):
                    existing["snippet"] = a["snippet"]
                if existing.get("timestamp", 0) == 0 and a.get("timestamp", 0) > 0:
                    existing["timestamp"] = a["timestamp"]
                    existing["time_str"] = a["time_str"]

    for q in queries_to_try:
        merge_batch(fetch_rss(q, max_items=35))
        print(f"Google 查詢「{q}」後，累計不重複原生報導：{len(merged_map)} 篇")
        if len(merged_map) >= 15:
            break

    # 同步補撈 Bing News RSS（為跨陣營內文抓取提供直連網址與導言摘要）
    bing_batch = fetch_bing_rss(short_topic, max_items=25)
    merge_batch(bing_batch)
    print(f"合併 Bing News 備援與直連網址後，累計不重複原生報導：{len(merged_map)} 篇")

    merged = list(merged_map.values())
    if len(merged) < 6:
        print("樣本數仍過少，回退採用綜合政治新聞池前 25 篇")
        return pool[:25]

    # 優先保留最新 30 篇，但盡量不丟失帶直連網址的代表性報導
    merged.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return merged[:30]


def extract_article_excerpt(raw_html, max_chars=MAX_EXCERPT_CHARS):
    """純標準庫 HTML 內文段落萃取器（零額外相依套件）。"""
    cleaned = re.sub(
        r"<(script|style|noscript|nav|header|footer|aside|form)[^>]*>[\s\S]*?</\1>",
        " ",
        raw_html,
        flags=re.IGNORECASE
    )
    paragraphs = re.findall(r"<p[^>]*>([\s\S]*?)</p>", cleaned, flags=re.IGNORECASE)
    good_lines = []
    total_len = 0

    for p in paragraphs:
        text = clean_html_text(p)
        if len(text) < 22:
            continue
        low = text.lower()
        if any(h in low for h in BOILERPLATE_HINTS):
            continue
        good_lines.append(text)
        total_len += len(text)
        if total_len >= max_chars:
            break

    return " ".join(good_lines)[:max_chars].strip()


def fetch_page_excerpt(url):
    if not url or "news.google.com" in url:
        return ""
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=6, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        # 避免亂碼：若宣告為 ISO-8859-1 則採用 apparent_encoding
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding or "utf-8"
        raw_html = resp.text[:180000]
        excerpt = extract_article_excerpt(raw_html, MAX_EXCERPT_CHARS)
        if len(excerpt) >= 80:
            return excerpt
        # 若 <p> 抓不到（部分 CSR 網頁），退回抓 og:description
        og_m = re.search(
            r'<meta[^>]+(?:property|name)=["\'](?:og:description|description)["\'][^>]+content=["\']([^"\']+)["\']',
            raw_html,
            flags=re.IGNORECASE
        )
        if og_m:
            return clean_html_text(og_m.group(1))[:300]
        return ""
    except Exception:
        return ""


def enrich_cross_camp_excerpts(articles):
    """
    依四大立場群組均衡挑選具直連網址的報導抓取內文摘錄（每群組最多 2 篇、總計最多 8 篇），
    確保 AI 看得到真實數字、法條與完整引述，而非只憑標題推測。
    """
    buckets = {
        "公媒／通訊社與商業綜合": [],
        "泛藍傾向": [],
        "泛綠傾向": [],
        "泛白／第三勢力": [],
    }
    for idx, a in enumerate(articles):
        direct = a.get("direct_url", "")
        if not direct or "news.google.com" in direct:
            continue
        camp = classify_camp_bucket(a["source"], a.get("bias_tag", ""))
        friendly_rank = 0 if any(d in direct.lower() for d in SCRAPER_FRIENDLY_DOMAINS) else 1
        buckets[camp].append((friendly_rank, idx, a))

    excerpts = []
    used_sources = set()

    for camp, candidates in buckets.items():
        candidates.sort(key=lambda x: x[0])
        picked_in_camp = 0
        for _, _, art in candidates:
            if len(excerpts) >= MAX_FULLTEXT_TOTAL or picked_in_camp >= MAX_FULLTEXT_PER_CAMP:
                break
            if art["source"] in used_sources:
                continue
            text = fetch_page_excerpt(art["direct_url"])
            if not text and art.get("snippet"):
                text = art["snippet"]
            if len(text) >= 60:
                excerpts.append({
                    "camp": camp,
                    "source": art["source"],
                    "time_str": art["time_str"],
                    "title": art["title"].split(" - ")[0].strip(),
                    "excerpt": text
                })
                used_sources.add(art["source"])
                picked_in_camp += 1

    print(f"成功取得跨陣營代表性內文摘錄：{len(excerpts)} 篇")
    return excerpts


def call_gemini(prompt, model=ANALYSIS_MODEL, thinking_budget=0):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={API_KEY}"
    )
    gen_config = {
        "temperature": 0.2,
        "thinkingConfig": {"thinkingBudget": thinking_budget}
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_config
    }

    for attempt in range(2):
        try:
            resp = requests.post(url, json=payload, timeout=300)
            resp.raise_for_status()
            parts = resp.json()["candidates"][0]["content"]["parts"]
            # 開啟思考模式時自動過濾 thought 內部草稿，僅回傳正式報告本文
            output_texts = [p.get("text", "") for p in parts if not p.get("thought") and p.get("text")]
            return "\n".join(output_texts).strip()
        except requests.exceptions.RequestException as e:
            if attempt == 0:
                print(f"連線異常，5秒後進行第2次重試... ({e})")
                time.sleep(5)
            else:
                raise


def load_history():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def main():
    if not API_KEY:
        raise ValueError("找不到 GEMINI_API_KEY，請確認已在 GitHub Secrets 設定！")

    history = load_history()
    recent_topics = [item["topic"] for item in history[:3]]
    recent_topics_str = "、".join(recent_topics) if recent_topics else "無"
    print(f"近期已分析過的議題：{recent_topics_str}")

    broad_query = (
        "(政治 OR 立法院 OR 行政院 OR 總統府 OR 國民黨 OR 民進黨 OR 民眾黨) when:18h"
    )
    pool = fetch_rss(broad_query, max_items=60)
    headlines_text = "\n".join([f"- [{a['source']}] {a['title']}" for a in pool])

    topic_prompt = f"""
以下是台灣過去 18 小時內的最新政治新聞標題清單（已排除入口轉載平台，均為原生媒體）：
{headlines_text}

我們在前幾期已經分析過以下議題：【{recent_topics_str}】

請依照以下規則選出本期要分析的單一新聞事件：
1. 優先挑選在清單中「有多家不同陣營媒體共同報導」、最具討論熱度的前 3 名政治事件。
2. 優先選擇第 1 名；但如果第 1 名與【{recent_topics_str}】是同一個新聞事件（即使字面用詞略有不同），請直接排除它，改選第 2 名或第 3 名的全新事件。
3. 唯一例外：如果舊議題發生了「重大結果翻轉」（例如：三讀通過、官員請辭、宣判出爐），才允許再次選擇。
4. 【關鍵字長度嚴格限制】：請只回傳 **1 到 2 個核心專有名詞**（以 1 個空白分隔，總字數 2～6 字），**絕對不要加上第 3 個細節動詞**（例如寫「軍公教 加薪」即可，不要寫「軍公教 加薪 入帳」；寫「財劃法 協商」即可，不要寫「財劃法 朝野協商 破局」），以免搜尋條件太嚴苛導致漏抓新聞。

請只回傳最終選定的關鍵字，不要加上任何標點符號或解釋文字。
"""
    raw_topic = call_gemini(topic_prompt, model=TOPIC_MODEL, thinking_budget=0).strip().replace('"', '').replace("'", "")
    hot_topic = " ".join(raw_topic.split()[:2])
    print(f"鎖定本時段分析議題：{hot_topic}")

    topic_articles = fetch_topic_articles(hot_topic, pool)
    topic_articles.sort(
        key=lambda x: x["timestamp"] if x["timestamp"] > 0 else 9999999999
    )

    # 跨陣營抓內文摘錄（讓 AI 看得到真實數據、法條與完整引述）
    fulltext_excerpts = enrich_cross_camp_excerpts(topic_articles)

    # 統計各陣營真實篇數，避免單邊聲量時 AI 硬湊偽均衡
    camp_counts = Counter(
        classify_camp_bucket(a["source"], a.get("bias_tag", ""))
        for a in topic_articles
    )
    camp_stats_str = (
        f"泛藍傾向 {camp_counts['泛藍傾向']} 篇｜"
        f"泛綠傾向 {camp_counts['泛綠傾向']} 篇｜"
        f"泛白／第三勢力 {camp_counts['泛白／第三勢力']} 篇｜"
        f"公媒／通訊社與商業綜合 {camp_counts['公媒／通訊社與商業綜合']} 篇"
    )
    dominance_guardrail = ""
    if camp_counts["泛藍傾向"] < 2 or camp_counts["泛綠傾向"] < 2:
        dominance_guardrail = (
            "\n⚠️【單邊聲量特別警告】：目前有一方主要陣營媒體報導不到 2 篇，"
            "切勿為了表面平衡而憑空捏造對方立場或硬湊不存在的盲點；請在對應盲點中誠實註明「本時段屬單邊陣營推動熱度，另一方尚未大規模跟進」。"
        )

    timeline_lines = []
    for a in topic_articles:
        snip = f"｜導言：{a['snippet'][:110]}" if a.get("snippet") else ""
        timeline_lines.append(
            f"時間：{a['time_str']} | 媒體：{a['source']} 【{a['bias_tag']}】 | 標題：{a['title']}{snip}"
        )
    timeline_text = "\n".join(timeline_lines)

    if fulltext_excerpts:
        excerpts_text = "\n\n".join([
            f"[{e['camp']}] {e['source']}（{e['time_str']}）\n標題：{e['title']}\n內文摘錄：{e['excerpt']}"
            for e in fulltext_excerpts
        ])
    else:
        excerpts_text = "（本時段未能取得額外內文，請嚴格依據上方清單標題與導言進行分析，切勿腦補未出現的數字或細節。）"

    analysis_prompt = f"""
你是一位專精台灣政治生態、公共政策與媒體識讀的資深查核分析師。
本時段鎖定分析的重大政治新聞議題為：【{hot_topic}】
本時段原生媒體陣營分布：{camp_stats_str}{dominance_guardrail}

【資料一：依發布時間由早到晚排序之原生媒體清單（已排除轉載入口）】
{timeline_text}

【資料二：跨陣營代表性報導內文摘錄（共 {len(fulltext_excerpts)} 篇）】
{excerpts_text}

【核心寫作鐵律（務必嚴格遵守，否則報告不合格）】
1. **零空話原則**：禁止寫出「藍媒強調在野監督、綠媒強調執政說明」這類套話。每一項盲點、框架對照都必須盡可能引用上述資料中的**具體數字、法條／預算名稱、人名原話或時間點**。
2. **禁止腦補原則**：所有數據與引述必須來自上方資料一或資料二；資料中未提及的細節不得自行編造。
3. **強制出處括號**：所有資訊落差與盲點句尾，一律附上實際有報導該資訊的媒體出處，例如 `（見中央社、自由時報報導）`，把主觀評論轉化為客觀可查證的「資訊覆蓋差」。
4. **拒絕貼標籤與偽均衡**：不預設任何媒體絕對中立，亦不各打五十大板。誰的標題煽動、誰平實引述數據、誰刻意省略關鍵前提，皆依實際文本客觀點出。

請嚴格依照以下標題與格式輸出繁體中文 Markdown 報告（不要在開頭加任何問候語）：

### 🎯 本時段焦點政治議題：{hot_topic}
**【多方對照事實摘要】**：抽離政黨情緒字眼，用 100～125 字精準還原已確認的核心事實、關鍵數字與真正爭點（請寫成單一段落，不要換行）。
**【議題主導陣營】**：請用「陣營名稱｜一句話原因（15字內）」格式填寫（例：🟦 藍營主導戰場｜以稅收超徵為由力拚法案三讀，或 ⚔️ 朝野攻防拉鋸｜雙方針對預算違憲與民生補貼交鋒）。
**【當事人表態對照】**（嚴格規則：只允許列出實際參與事件的政治人物、政黨、政府機關或民間團體；**嚴禁將任何新聞媒體名稱列入當事人**；實際明確表態者若只有 2 位就只列 2 行）：
- 🟦/🟩/⬜/🏛️ 實際當事人A姓名或機關名稱：用 35 字以內濃縮其最新具體主張或數據。
- 🟦/🟩/⬜/🏛️ 實際當事人B姓名或機關名稱：用 35 字以內濃縮其核心反駁或法理依據。
- 🟦/🟩/⬜/🏛️ 實際當事人C姓名或機關名稱（選填，無明確第3位請省略）：用 35 字以內濃縮其立場或關鍵表態。

---

### 1. 🧭 政黨風向與媒體立場光譜分析
請結合「預設背景光譜」與「本篇實際標題／內文用詞」，將報導歸類為 **泛綠傾向、泛藍傾向、泛白／第三勢力傾向、公媒／通訊社與商業綜合** 四大類：
- 請建立一個 Markdown 比較表格，欄位包含：【立場分類】、【本次上榜媒體】、【主打敘事框架與具體引述】、【試圖引導受眾相信的結論】。
- **🔍 同一事實，兩邊怎麼切？（敘事框架對照）**：從資料中挑出 1～2 個「同一個數字、法條或當事人原話」，並列呈現藍白媒體與綠營媒體分別怎麼剪輯與詮釋（附上媒體名稱）。
- **📰 標題 vs. 內文落差抓包**：比對資料二內文與資料一標題，點出是否有「標題情緒激化或斷章取義，但內文原話其實相對平緩／附帶前提條件」的案例（若各家標題皆大致符合內文，請直接誠實註記「本期跨陣營標題大致符合內文原意，未見明顯標題黨扭曲」）。
- **🧭 風向總評**：2～3 句總結目前是哪一方掌握議題設定權（Agenda Setting）與實質攻防焦點。

### 2. 🕳️ 同溫層盲點分析（Blindspot Analysis）
交叉比對不同陣營報導的「資訊覆蓋差」，揪出選擇性揭露的具體事實（**格式鐵律**：請務必嚴格保留以下兩個粗體子標題，且每個盲點請寫成 **同一行內 2～3 句具體事實，以句號「。」分隔**，每句皆須帶具體內容與 `(見OO媒體報導)` 出處括號，不要再另開次層換行清單）：
- **只看泛藍／泛白媒體的受眾盲點**：第一句具體指出藍白報導漏掉的執政方數據、法理依據或完整原話（見OO、XX報導）。第二句補充另一項被淡化的脈絡或公媒查證細節（見OO報導）。
- **只看泛綠媒體的受眾盲點**：第一句具體指出綠營報導漏掉的在野黨核心質疑、預算／程序細節或民間反彈依據（見OO、XX報導）。第二句補充第三勢力或中立機構的不同觀點（見OO報導）。

### 3. 🕵️‍♂️ 源頭追蹤、缺失拼圖與可查證度檢核
- **🕒 傳播時間軸還原**：哪一家原生媒體在幾點幾分率先發布第一篇報導？隨後各陣營媒體如何接力擴散、改寫標題或發動反擊？
- **🔗 真正消息源頭判定**：這波新聞的最原始起點為何？（如官方記者會／立院公開質詢／特定政治人物公開貼文／匿名「知情人士」放話等）
- **🧩 各陣營都沒講的「缺失拼圖」（事實基準線）**：指出藍綠雙方忙著口水攻防時，都刻意省略或沒講清楚的 1～2 個關鍵前提（例如現行法規原本怎麼規定、該筆金額佔總預算比例、後續仍須經過哪些法定程序，或單一消息來源尚未獲第三方證實）。
- **🛡️ 消息可靠度評分**：80分（請直接將此處的「80分」替換為下方四項加總後的 0～100 實際總分，例如「84分」，切勿在冒號前加上任何數字）
  - **具名來源（X/25分）**：說明核心說法是否來自具名機關、公開會議紀錄或本人表態，而非匿名放話。
  - **跨陣營共識（X/25分）**：說明核心事件本身是否獲至少兩大不同立場群組（或公媒）共同證實。
  - **具體數據與文本（X/25分）**：說明報導是否附有可核對的金額、法條、公文或完整原話脈絡。
  - **單一來源風險控管（X/25分）**：評估是否過度依賴單一媒體獨家爆料或未經證實的政黨推論。
  - **查證結論**：簡潔區分哪些屬於「已確認事實」，哪些屬於「政黨推論或待查證放話」。
"""

    report_md = call_gemini(
        analysis_prompt,
        model=ANALYSIS_MODEL,
        thinking_budget=ANALYSIS_THINKING_BUDGET
    )

    now_tw = datetime.now(TW_TZ)
    hour = now_tw.hour
    period = "早報" if hour < 11 else ("午報" if hour < 17 else "晚報")

    # 存入 JSON 前清除暫存欄位，維持 news_history.json 輕量高速
    compact_sources = [
        {
            "source": a["source"],
            "bias_tag": a["bias_tag"],
            "title": a["title"],
            "link": a.get("direct_url") or a["link"],
            "time_str": a["time_str"],
            "timestamp": a["timestamp"]
        }
        for a in topic_articles
    ]

    new_entry = {
        "id": now_tw.strftime("%Y%m%d_%H%M"),
        "date_str": now_tw.strftime("%Y-%m-%d %H:%M"),
        "period": period,
        "topic": hot_topic,
        "article_count": len(compact_sources),
        "fulltext_count": len(fulltext_excerpts),
        "report": report_md,
        "sources": compact_sources
    }

    history.insert(0, new_entry)
    history = history[:30]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
