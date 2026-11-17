import os
import json
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import requests

API_KEY = os.environ.get("GEMINI_API_KEY")
TW_TZ = timezone(timedelta(hours=8))
DATA_FILE = "news_history.json"

# ==========================================
# 台灣主要媒體預設政治光譜字典（可隨時自行增刪修改）
# ==========================================
MEDIA_SPECTRUM = {
    # 泛藍／偏在野監督／兩岸溫和派傾向
    "聯合報": "泛藍傾向（傳統四大報，偏重在野監督與體制穩定）",
    "聯合新聞網": "泛藍傾向（聯合報系）",
    "經濟日報": "泛藍／財經務實傾向（聯合報系）",
    "中國時報": "泛藍／親中傾向（旺中集團，鮮明監督執政黨）",
    "中時新聞網": "泛藍／親中傾向（旺中集團）",
    "工商時報": "泛藍／財經產業界傾向（旺中集團）",
    "中天新聞": "深藍／強烈監督執政黨傾向（旺中集團）",
    "中天新聞網": "深藍／強烈監督執政黨傾向（旺中集團）",
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
    "Newtalk新聞": "泛綠／本土派傾向",
    "太報": "泛綠／本土自由派傾向",
    "鏡週刊": "偏綠／揭弊調查傾向（常進行政商黑幕調查報導）",
    "鏡新聞": "偏綠／綜合新聞傾向",
    "放言": "泛綠傾向",

    # 泛白／第三勢力或高度關注民眾黨動態
    "民眾之聲": "泛白傾向（民眾黨官方新媒體）",
    "匯流新聞網": "偏泛白／第三勢力傾向（CNEWS，高比例報導民眾黨與國會攻防）",
    "CNEWS匯流新聞網": "偏泛白／第三勢力傾向",

    # 官方通訊社／公共媒體／相對中立或商業流量導向
    "中央社": "中立／國家通訊社（CNA，以官方公開資訊與平實陳述為主，略帶官方視角）",
    "公視新聞網": "中立／公共媒體（PTS，強調平衡報導與公共議題）",
    "報導者": "中立／深度調查獨立媒體",
    "ETtoday新聞雲": "商業流量導向／立場視議題而定（常做即時快訊與網路輿情）",
    "NOWnews今日新聞": "商業綜合／立場相對溫和",
    "壹蘋新聞網": "商業綜合／揭弊與民生導向",
    "華視新聞": "公共化媒體／相對中立",
    "台視新聞": "傳統老三台／相對中立平實",
    "中視新聞": "泛藍傾向（旺中集團旗下老三台）",
    "Yahoo奇摩新聞": "入口網站／綜合轉載",
    "LINE TODAY": "入口網站／綜合轉載"
}

def get_media_bias_tag(source_name):
    """比對媒體名稱，回傳預設光譜標籤"""
    for key, bias_desc in MEDIA_SPECTRUM.items():
        if key in source_name:
            return bias_desc
    return "未預設光譜（請依標題用詞直接判定）"

def fetch_rss(query, max_items=45):
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=15)
    root = ET.fromstring(resp.content)
    articles = []
    for item in root.findall(".//item")[:max_items]:
        title = item.find("title").text if item.find("title") is not None else ""
        source = item.find("source").text if item.find("source") is not None else "未知媒體"
        link = item.find("link").text if item.find("link") is not None else ""
        pub_date_raw = item.find("pubDate").text if item.find("pubDate") is not None else ""
        try:
            dt = parsedate_to_datetime(pub_date_raw).astimezone(TW_TZ)
            ts_str = dt.strftime("%Y-%m-%d %H:%M")
            ts_val = dt.timestamp()
        except Exception:
            ts_str = "未知時間"
            ts_val = 0
        articles.append({
            "source": source,
            "bias_tag": get_media_bias_tag(source),
            "title": title,
            "link": link,
            "time_str": ts_str,
            "timestamp": ts_val
        })
    return articles

def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }
    resp = requests.post(url, json=payload, timeout=90)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

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

    # 讀取歷史紀錄，抓出最近 3 期已經分析過的議題（防撞題）
    history = load_history()
    recent_topics = [item["topic"] for item in history[:3]]
    recent_topics_str = "、".join(recent_topics) if recent_topics else "無"
    print(f"近期已分析過的議題：{recent_topics_str}")

    # 階段一：抓取過去 12 小時台灣政治新聞，找出最大議題（若重複則自動遞補第二大）
    broad_query = "(政治 OR 立法院 OR 行政院 OR 總統府 OR 國民黨 OR 民進黨 OR 民眾黨) when:12h"
    pool = fetch_rss(broad_query, max_items=50)
    headlines_text = "\n".join([f"- [{a['source']}] {a['title']}" for a in pool])

    topic_prompt = f"""
以下是台灣過去 12 小時內的最新政治新聞標題清單：
{headlines_text}

我們在前幾期已經分析過以下議題：【{recent_topics_str}】

請依照以下規則選出本期要分析的單一新聞事件：
1. 先在心中統計出目前報導量最大的前 3 名政治新聞事件。
2. 優先選擇第 1 名；但如果第 1 名與【{recent_topics_str}】是同一個新聞事件（即使字面用詞略有不同，例如「總預算覆議」與「立院總預算」視為同一事件），請直接排除它，**改選擇報導量第 2 名（或第 3 名）的全新新聞事件**！
3. 唯一例外：如果舊議題在過去幾小時內發生了「重大結果翻轉」（例如：法案正式三讀通過、官員宣布請辭、法院宣判結果出爐），才允許再次選擇，並請在關鍵字中加上最新進度。

請只回傳最終選定之事件的「核心搜尋關鍵字」（約 2 到 6 個字，以空白分隔，例如：「財劃法 朝野協商」或「憲法訴訟法 釋憲」），不要加上任何標點符號或解釋文字。
"""
    hot_topic = call_gemini(topic_prompt).strip().replace('"', '').replace("'", "")
    print(f"鎖定本時段分析議題：{hot_topic}")

    # 階段二：針對該議題深入抓取各家報導，並依「時間戳記」由舊到新排序
    topic_articles = fetch_rss(f"{hot_topic} when:24h", max_items=35)
    if len(topic_articles) < 5:
        topic_articles = pool[:25]

    topic_articles.sort(key=lambda x: x["timestamp"] if x["timestamp"] > 0 else 9999999999)

    timeline_text = "\n".join([
        f"時間：{a['time_str']} | 媒體：{a['source']} 【預設背景：{a['bias_tag']}】 | 標題：{a['title']}"
        for a in topic_articles
    ])

    # 階段三：結合媒體光譜字典、盲點與時間戳記進行深度分析
    analysis_prompt = f"""
你是一位專精台灣政治生態與媒體識讀的首席分析師。
本時段鎖定分析的重大政治新聞議題為：【{hot_topic}】
（備註：若前幾期已分析過頭號話題，系統已自動為讀者遞補次高討論度之焦點議題）

以下是系統依「發布時間戳記（由最早到最新）」排序的各家媒體報導清單，每家媒體後方皆附有系統預設的「媒體政治光譜背景」供你參考：
{timeline_text}

請根據上述時間序列、媒體預設光譜與實際標題切角，產出以下結構化的深度分析報告（請使用繁體中文與 Markdown 格式）：

### 🎯 本時段焦點政治議題：{hot_topic}
**【中立客觀事實摘要】**：抽離所有政黨立場與情緒字眼，用 120 字以內還原此事件目前已確認的核心事實。

### 1. 🧭 政黨風向與媒體立場光譜分析
請結合清單中的「預設背景光譜」與「該篇報導的實際標題用詞」，將報導歸類為 **泛綠傾向、泛藍傾向、泛白／第三勢力傾向、中立／純事實陳述** 四大類：
* **判讀原則**：預設光譜代表該媒體長期社論立場，但若某偏藍或偏綠媒體在此事件中僅平實陳述數據而無情緒字眼，請務必肯定其實際表現。
* 請建立一個 Markdown 比較表格，欄位包含：【立場分類】、【本次上榜媒體】、【主打敘事框架與情緒用詞】、【試圖引導受眾相信的結論】。
* **風向總評**：這波輿論戰目前是哪一個陣營在主導議題設定（Agenda Setting）？各陣營的攻防重點為何？

### 2. 🕳️ 同溫層盲點分析（Blindspot Analysis）
交叉比對不同陣營的報導比例與內容，揪出「選擇性揭露」的盲點：
* **只看泛藍／泛白媒體的受眾盲點**：這群讀者在這波報導中，會看不見哪些執政黨提出的數據背景、法理依據或澄清說明？
* **只看泛綠媒體的受眾盲點**：這群讀者在這波報導中，會看不見哪些在野黨質疑的程序瑕疵、預算爭議或民間反彈聲浪？

### 3. 🕵️‍♂️ 源頭追蹤與「一條龍」轉載鏈解析（可靠度評估）
請根據清單上的「時間戳記（最早發布時間）」與標題引述線索，逆向追蹤這起新聞的源頭：
* **🕒 傳播時間軸還原**：哪一家媒體在幾點幾分率先發布第一篇報導？隨後哪些同陣營或敵對陣營媒體在幾點跟進轉載、或是改寫標題進行反擊？
* **🔗 真正消息源頭判定**：這波新聞的最原始起點是什麼？（例如：立法院公開質詢／官方記者會、特定政治人物臉書／Threads 發文、獨家匿名「知情人士」放話、還是網路論壇 PTT/Dcard 爆卦？）
* **🛡️ 消息可靠度評分（0～100分）**：給予此議題目前的資訊可靠度分數，並說明哪些屬於「有憑有據的查證事實」，哪些只是「政黨帶風向的放話或過度推論」。
"""
    report_md = call_gemini(analysis_prompt)

    now_tw = datetime.now(TW_TZ)
    hour = now_tw.hour
    period = "早報" if hour < 11 else ("午報" if hour < 17 else "晚報")

    new_entry = {
        "id": now_tw.strftime("%Y%m%d_%H%M"),
        "date_str": now_tw.strftime("%Y-%m-%d %H:%M"),
        "period": period,
        "topic": hot_topic,
        "article_count": len(topic_articles),
        "report": report_md,
        "sources": topic_articles
    }

    history.insert(0, new_entry)
    history = history[:30]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
