import os
import json
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import requests

API_KEY = os.environ.get("GEMINI_API_KEY")
TW_TZ = timezone(timedelta(hours=8))

def fetch_rss(query, max_items=40):
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

def main():
    if not API_KEY:
        raise ValueError("找不到 GEMINI_API_KEY，請確認已在 GitHub Secrets 設定！")

    # 階段一：抓取過去 12 小時台灣政治新聞，找出報導量最大的單一議題
    broad_query = "(政治 OR 立法院 OR 行政院 OR 總統府 OR 國民黨 OR 民進黨 OR 民眾黨) when:12h"
    pool = fetch_rss(broad_query, max_items=45)
    headlines_text = "\n".join([f"- [{a['source']}] {a['title']}" for a in pool])

    topic_prompt = f"""
以下是台灣過去 12 小時內的最新政治新聞標題清單：
{headlines_text}

請找出目前「各家媒體報導量最大、討論最集中」的第 1 名單一新聞事件。
請只回傳該事件的「核心搜尋關鍵字」（約 2 到 6 個字，以空白分隔，例如：「總預算 覆議案」或「財劃法 立法院」），不要加上任何標點符號或其他解釋文字。
"""
    hot_topic = call_gemini(topic_prompt).strip().replace('"', '').replace("'", "")
    print(f"鎖定本時段最大政治議題：{hot_topic}")

    # 階段二：針對該議題深入抓取各家報導，並依「時間戳記」由舊到新排序（追蹤源頭）
    topic_articles = fetch_rss(f"{hot_topic} when:24h", max_items=30)
    if len(topic_articles) < 5:
        topic_articles = pool[:25]

    # 依發布時間由最早排到最新
    topic_articles.sort(key=lambda x: x["timestamp"] if x["timestamp"] > 0 else 9999999999)

    timeline_text = "\n".join([
        f"時間：{a['time_str']} | 媒體：{a['source']} | 標題：{a['title']}"
        for a in topic_articles
    ])

    # 階段三：進行政黨風向、盲點與時間戳記溯源分析
    analysis_prompt = f"""
你是一位專精台灣政治生態與媒體識讀的首席分析師。
目前時段全台報導量最大的政治新聞議題為：【{hot_topic}】

以下是系統依「發布時間戳記（由最早到最新）」排序的各家媒體報導清單：
{timeline_text}

請根據上述時間序列與各家標題切角，產出以下結構化的深度分析報告（請使用繁體中文與 Markdown 格式）：

### 🎯 本時段最熱政治議題：{hot_topic}
**【中立客觀事實摘要】**：抽離所有政黨立場與情緒字眼，用 120 字以內還原此事件目前已確認的核心事實。

---

### 1. 🧭 政黨風向與媒體立場光譜分析
請將上述報導依台灣常見政治光譜（如：**泛綠傾向、泛藍傾向、泛白／第三勢力傾向、中立／純事實陳述**）進行歸類分析：
* 建立一個 Markdown 比較表格，欄位包含：【立場分類】、【代表媒體】、【主打敘事框架與情緒用詞】、【試圖引導受眾相信的結論】。
* 綜合評估：這波輿論戰目前是哪一個陣營在主導議題設定（Agenda Setting）？

### 2. 🕳️ 同溫層盲點分析（Blindspot Analysis）
交叉比對不同陣營的報導，揪出「選擇性揭露」的盲點：
* **泛藍／在野陣營讀者的盲點**：只看偏藍白媒體的受眾，會錯過哪些執政黨提出的數據、背景說明或反駁？
* **泛綠／執政陣營讀者的盲點**：只看偏綠媒體的受眾，會錯過哪些在野黨指出的程序瑕疵、爭議細節或民意反彈？

### 3. 🕵️‍♂️ 源頭追蹤與「一條龍」轉載鏈解析（可靠度評估）
請根據清單上的「時間戳記（最早發布時間）」與標題引述線索，逆向追蹤這起新聞的源頭：
* **🕒 傳播時間軸還原**：哪一家媒體在幾點幾分率先發難？隨後哪些媒體在幾點跟進轉載或改寫標題帶風向？
* **🔗 真正消息源頭判定**：這波新聞的最原始起點是什麼？（例如：立法院公開質詢／官方記者會、特定政治人物臉書／Threads 發文、獨家匿名「知情人士」放話、還是網路論壇 PTT/Dcard 爆卦？）
* **🛡️ 消息可靠度評分（0～100分）**：給予此議題目前的資訊可靠度分數，並說明哪些部分屬於「已證實事實」，哪些部分只是「政黨帶風向的臆測或放話」。
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

    data_file = "news_history.json"
    history = []
    if os.path.exists(data_file):
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    history.insert(0, new_entry)
    history = history[:30]  # 保留最近 30 期（約 10 天份的早中晚報）

    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
