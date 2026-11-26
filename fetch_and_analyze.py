import os
import re
import html
import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import requests

API_KEY = os.environ.get("GEMINI_API_KEY")
TW_TZ = timezone(timedelta(hours=8))
DATA_FILE = "news_history.json"

# 主分析模型設定（每天僅跑 3 次；若未來想更進一步提升文筆可改為 gemini-2.5-pro）
# 可用 GitHub Secrets／環境變數 GEMINI_MODEL 一次切換模型（換模型前請先手動跑一次 workflow 確認輸出格式）
TOPIC_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ANALYSIS_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ANALYSIS_THINKING_BUDGET = 4096
GEMINI_MAX_ATTEMPTS = 3
GEMINI_BACKOFF_SECONDS = [10, 30]  # 限流（429）或暫時錯誤時的等待秒數
# 輸出上限（含思考 token）：防止 AI 暴衝輸出空白（曾單期輸出 200 萬個空白、報告被截斷）
TOPIC_MAX_OUTPUT_TOKENS = 512
ANALYSIS_MAX_OUTPUT_TOKENS = 16384  # 思考 4096＋報告；正常報告約 4～6 千 token
# 手動執行 workflow 時勾選 force 才會在同一時段重跑
FORCE_RUN = os.environ.get("FORCE_RUN", "").strip().lower() == "true"

# 內文抓取上限（跨 4 陣營各最多抓 2 篇，兼顧深度與執行速度）
MAX_FULLTEXT_PER_CAMP = 2
MAX_FULLTEXT_TOTAL = 8
MAX_EXCERPT_CHARS = 750

# 內文抓取：單頁最多讀取位元組數、並行執行緒數、每陣營最多嘗試幾家媒體
MAX_PAGE_BYTES = 400_000
FETCH_WORKERS = 8
MAX_CANDIDATES_PER_CAMP = 6

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
# 媒體光譜共用規則（官網 app.py、本程式、LINE 機器人 worker.js 共用 media_spectrum.json）
# 轉載入口黑名單、媒體光譜字典、陣營關鍵字都在該檔維護，修改分類只要改一處
# ==========================================
RULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media_spectrum.json")


def load_media_rules(path=RULES_FILE):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"找不到 {os.path.basename(path)}（媒體光譜共用規則檔），請放在 GitHub 專案根目錄、與本程式同一層。"
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


MEDIA_RULES = load_media_rules()
CAMP_LABELS = MEDIA_RULES["camp_labels"]
AGGREGATOR_BLACKLIST = MEDIA_RULES["aggregator_blacklist"]
# 名稱長的優先比對，確保「中天新聞網」優先於「中天新聞」、「TVBS新聞網」優先於「TVBS」
MEDIA_KEYS_LONGEST_FIRST = sorted(MEDIA_RULES["media"].keys(), key=len, reverse=True)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
}

# 共用連線（Session）：重複利用 TCP/TLS 連線，減少 Google／Bing／Gemini 的連線開銷
SESSION = requests.Session()
SESSION.headers.update(BROWSER_HEADERS)


def is_aggregator(source_name):
    s_lower = (source_name or "").lower()
    return any(b.lower() in s_lower for b in AGGREGATOR_BLACKLIST)


def match_media(source_name):
    """回傳 media_spectrum.json 中「名稱最長」且包含於媒體名稱的那一筆；找不到回傳 None。"""
    s = source_name or ""
    for key in MEDIA_KEYS_LONGEST_FIRST:
        if key in s:
            return MEDIA_RULES["media"][key]
    return None


def get_media_bias_tag(source_name):
    m = match_media(source_name)
    return m["desc"] if m else MEDIA_RULES["default_desc"]


def classify_camp_bucket(source_name, bias_tag=""):
    """與官網 app.py、LINE 機器人 worker.js 同一套規則（bias_tag 參數保留以相容舊呼叫）。"""
    m = match_media(source_name)
    if m:
        return CAMP_LABELS[m["camp"]]
    s = source_name or ""
    for camp in ("green", "blue", "white"):
        if any(k in s for k in MEDIA_RULES["keyword_fallback"][camp]):
            return CAMP_LABELS[camp]
    return CAMP_LABELS["neutral"]


def parse_pub_date(pub_raw):
    """RSS pubDate → (台灣時間字串, timestamp)；解析失敗回傳 ("未知時間", 0)。"""
    try:
        dt = parsedate_to_datetime(pub_raw).astimezone(TW_TZ)
        return dt.strftime("%Y-%m-%d %H:%M"), dt.timestamp()
    except Exception:
        return "未知時間", 0


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
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        print(f"Google RSS 抓取異常 ({query}): {e}")
        return []

    articles = []
    for item in root.findall(".//item"):
        source = (item.findtext("source") or "").strip() or "未知媒體"
        if is_aggregator(source):
            continue

        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        ts_str, ts_val = parse_pub_date(item.findtext("pubDate") or "")

        articles.append({
            "source": source,
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
        resp = SESSION.get(url, timeout=15)
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
        ts_str, ts_val = parse_pub_date((item.findtext("pubDate") or "").strip())

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
    # 用 <p(?:\s[^>]*)?> 而非 <p[^>]*>，避免誤配 <path>、<picture>、<param> 等標籤
    paragraphs = re.findall(r"<p(?:\s[^>]*)?>([\s\S]*?)</p>", cleaned, flags=re.IGNORECASE)
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


def decode_html_bytes(raw, declared_encoding):
    """依 HTTP 標頭 → <meta charset> → UTF-8 → Big5 的順序解碼，避免亂碼。"""
    enc = (declared_encoding or "").lower()
    if enc and enc != "iso-8859-1":
        try:
            return raw.decode(enc, errors="replace")
        except LookupError:
            pass
    m = re.search(rb'charset=["\']?\s*([A-Za-z0-9_\-]+)', raw[:4096], flags=re.IGNORECASE)
    if m:
        try:
            return raw.decode(m.group(1).decode("ascii"), errors="replace")
        except LookupError:
            pass
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("big5", errors="replace")


def fetch_page_excerpt(url):
    if not url or "news.google.com" in url:
        return ""
    try:
        # stream=True：只讀前 MAX_PAGE_BYTES，不必把整個大網頁下載完；timeout=(連線逾時, 讀取逾時)
        with requests.get(url, headers=BROWSER_HEADERS, timeout=(4, 6),
                          allow_redirects=True, stream=True) as resp:
            if resp.status_code != 200:
                return ""
            raw_bytes = resp.raw.read(MAX_PAGE_BYTES, decode_content=True) or b""
            declared = resp.encoding
        raw_html = decode_html_bytes(raw_bytes, declared)
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

    # 每陣營依「友善網域優先、原排序」挑出前幾家不重複媒體作為候選
    plan = {}
    for camp, candidates in buckets.items():
        candidates.sort(key=lambda x: (x[0], x[1]))
        seen, picked = set(), []
        for _, _, art in candidates:
            if art["source"] in seen:
                continue
            seen.add(art["source"])
            picked.append(art)
            if len(picked) >= MAX_CANDIDATES_PER_CAMP:
                break
        plan[camp] = picked

    # 並行抓取所有候選網址（原本逐篇排隊，每篇最多等 6 秒，失敗越多越慢）
    unique_urls = list(dict.fromkeys(art["direct_url"] for arts in plan.values() for art in arts))
    page_texts = {}
    if unique_urls:
        with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(unique_urls))) as executor:
            for url, text in zip(unique_urls, executor.map(fetch_page_excerpt, unique_urls)):
                page_texts[url] = text

    # 依原本的優先順序挑選：每陣營最多 MAX_FULLTEXT_PER_CAMP 篇、總計最多 MAX_FULLTEXT_TOTAL 篇
    excerpts = []
    used_sources = set()
    for camp, arts in plan.items():
        picked_in_camp = 0
        for art in arts:
            if len(excerpts) >= MAX_FULLTEXT_TOTAL or picked_in_camp >= MAX_FULLTEXT_PER_CAMP:
                break
            if art["source"] in used_sources:
                continue
            text = page_texts.get(art["direct_url"], "")
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


class GeminiError(RuntimeError):
    """可重試的 Gemini 錯誤（限流、暫時故障、空白回應）。"""


def call_gemini(prompt, model=ANALYSIS_MODEL, thinking_budget=0, max_output_tokens=None):
    """呼叫 Gemini：金鑰放在 x-goog-api-key 標頭（官方寫法）；限流或暫時錯誤時退避重試。"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": API_KEY, "Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "thinkingConfig": {"thinkingBudget": thinking_budget}
        }
    }
    if max_output_tokens:
        payload["generationConfig"]["maxOutputTokens"] = max_output_tokens

    last_err = None
    for attempt in range(GEMINI_MAX_ATTEMPTS):
        try:
            resp = SESSION.post(url, json=payload, headers=headers, timeout=300)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise GeminiError(f"Gemini 暫時無法服務（HTTP {resp.status_code}）：{resp.text[:200]}")
            if resp.status_code != 200:
                # 400／403 等設定錯誤，重試也不會好，直接中止
                raise ValueError(f"Gemini 請求失敗（HTTP {resp.status_code}）：{resp.text[:300]}")

            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                block = (data.get("promptFeedback") or {}).get("blockReason", "未知")
                raise GeminiError(f"Gemini 未回傳內容（blockReason={block}）")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            # 開啟思考模式時自動過濾 thought 內部草稿，僅回傳正式報告本文
            output_texts = [p.get("text", "") for p in parts if not p.get("thought") and p.get("text")]
            text = "\n".join(output_texts).strip()
            if not text:
                reason = candidates[0].get("finishReason", "未知")
                raise GeminiError(f"Gemini 回傳空白內容（finishReason={reason}）")
            return text
        except (requests.exceptions.RequestException, GeminiError) as e:
            last_err = e
            if attempt < GEMINI_MAX_ATTEMPTS - 1:
                wait = GEMINI_BACKOFF_SECONDS[min(attempt, len(GEMINI_BACKOFF_SECONDS) - 1)]
                print(f"Gemini 第 {attempt + 1} 次呼叫失敗，{wait} 秒後重試…（{e}）")
                time.sleep(wait)
    raise last_err


def load_history():
    if not os.path.exists(DATA_FILE):
        return []
    # 解析失敗時直接報錯中止：舊版會回傳空清單，接著用 1 期新資料覆蓋掉既有 30 期紀錄
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def clean_topic(raw_topic):
    """清掉引號、括號與 Markdown 符號，只保留前 2 個詞。"""
    text = re.sub(r"[\"'「」『』【】*#`]", "", raw_topic or "")
    return " ".join(text.split()[:2])


def sanitize_report(text):
    """清除 AI 暴衝輸出的連續空白（曾單期塞入 200 萬個空白，官網資料膨脹到 11MB），並去除行尾空白。"""
    text = re.sub(r"[ \t　]{8,}", " ", text or "")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


# 與官網 app.py 解析評分用同一個規則，確保存進去的報告官網一定讀得到分數
SCORE_PATTERN = r"可靠度評分(?:\s*[\(（][^\)）]*[\)）])?[\*\s]*[：:]\s*\*?(\d{1,3})\s*分"


def validate_report(report_md):
    """回傳問題描述；空字串代表通過。避免把空白或被截斷的報告寫進官網。"""
    text = (report_md or "").strip()
    if len(text) < 600:
        return f"長度僅 {len(text)} 字"
    for n in ("1", "2", "3"):
        if not re.search(rf"###\s*{n}\.", text):
            return f"缺少第 {n} 段（### {n}.）"
    if not re.search(SCORE_PATTERN, text):
        return "缺少消息可靠度評分"
    return ""


def period_of(dt):
    return "早報" if dt.hour < 11 else ("午報" if dt.hour < 17 else "晚報")


def main():
    if not API_KEY:
        raise ValueError("找不到 GEMINI_API_KEY，請確認已在 GitHub Secrets 設定！")

    history = load_history()

    # 同一時段只產一份：cron-job.org 與 GitHub 排程都會觸發（曾每個時段各跑兩次、Gemini 費用加倍）
    started_tw = datetime.now(TW_TZ)
    current_period = period_of(started_tw)
    if history and not FORCE_RUN:
        latest = history[0]
        if (str(latest.get("date_str", ""))[:10] == started_tw.strftime("%Y-%m-%d")
                and latest.get("period") == current_period):
            print(f"⏭️ {started_tw:%Y-%m-%d} {current_period}已有報告（{latest.get('date_str')}），本次略過以免重複。"
                  "如需重跑，請在 GitHub Actions 手動執行並勾選 force。")
            return

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
    hot_topic = ""
    for _ in range(2):
        raw_topic = call_gemini(topic_prompt, model=TOPIC_MODEL, thinking_budget=0,
                                max_output_tokens=TOPIC_MAX_OUTPUT_TOKENS)
        hot_topic = clean_topic(raw_topic)
        if hot_topic:
            break
        print(f"選題結果無法使用（{raw_topic[:40]!r}），重新選題一次…")
    if not hot_topic:
        raise RuntimeError("Gemini 連續兩次未回傳有效議題關鍵字，本次不更新 news_history.json")
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
- **表格格式鐵律**：請用最精簡的 Markdown 表格寫法，每個儲存格前後只留 1 個半形空白，**嚴禁用空白補齊欄寬或對齊**，分隔列只寫 `|---|---|---|---|`。
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

    report_md, problem = "", ""
    for _ in range(2):
        raw_report = call_gemini(
            analysis_prompt,
            model=ANALYSIS_MODEL,
            thinking_budget=ANALYSIS_THINKING_BUDGET,
            max_output_tokens=ANALYSIS_MAX_OUTPUT_TOKENS
        )
        report_md = sanitize_report(raw_report)
        if len(raw_report) - len(report_md) > 2000:
            print(f"⚠️ 偵測到 AI 輸出暴衝空白，已清除 {len(raw_report) - len(report_md):,} 個字元")
        problem = validate_report(report_md)
        if not problem:
            break
        print(f"報告格式檢查未通過（{problem}），重新產生一次…")
    else:
        raise RuntimeError(f"報告連續兩次格式不完整（{problem}），本次不更新 news_history.json，保留上一期內容")

    now_tw = datetime.now(TW_TZ)
    period = current_period  # 以開始執行的時段為準，與上方防重複檢查一致

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

    # 順便清理舊紀錄中 AI 暴衝的空白（官網資料曾因此膨脹到 11MB，拖慢官網與 LINE 機器人）
    for old_entry in history:
        if isinstance(old_entry.get("report"), str):
            old_entry["report"] = sanitize_report(old_entry["report"])

    history.insert(0, new_entry)
    history = history[:30]

    # 先寫暫存檔再替換，避免中途失敗留下壞掉的 JSON（官網與 LINE 機器人都讀這個檔）
    tmp_path = DATA_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, DATA_FILE)
    print(f"✅ 已寫入 {DATA_FILE}（共 {len(history)} 期）")


if __name__ == "__main__":
    main()
