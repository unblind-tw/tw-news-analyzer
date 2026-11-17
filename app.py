import streamlit as st
import requests
import urllib.parse
import xml.etree.ElementTree as ET

# 網頁標題與排版設定
st.set_page_config(page_title="台灣新聞風向分析儀", page_icon="🧭", layout="wide")

st.title("🧭 台灣新聞風向與中立性分析儀")
st.write("透過交叉比對各家媒體（傳統媒體與新媒體），自動拆解**客觀事實交集**、**情緒引導用字**與**潛在立場風向**。")

# 側邊欄設定
with st.sidebar:
    st.header("🔑 啟動設定")
    api_key = st.text_input("請輸入 Gemini API Key", type="password", help="於 Google AI Studio 免費申請")
    st.markdown("[👉 點此免費取得 API Key](https://aistudio.google.com/app/apikey)")
    st.divider()
    st.markdown("### 💡 這個工具如何運作？\n1. **排除同溫層**：同時抓取不同立場媒體對同一事件的報導。\n2. **抽離情緒字眼**：過濾形容詞，只保留各方皆認可的事實。\n3. **揭露帶風向手法**：標示標題殺人、刻意遺漏與匿名來源。")

# 抓取 Google News 台灣版 RSS
def fetch_google_news(keyword, max_results=12):
    encoded_kw = urllib.parse.quote(keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_kw}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(rss_url, headers=headers, timeout=10)
    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall(".//item")[:max_results]:
        title = item.find("title").text if item.find("title") is not None else ""
        source = item.find("source").text if item.find("source") is not None else "未知媒體"
        pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
        link = item.find("link").text if item.find("link") is not None else ""
        items.append({"source": source, "title": title, "date": pub_date, "link": link})
    return items

# 將新聞網址轉為純文字
def extract_url_text(url):
    try:
        jina_url = f"https://r.jina.ai/{url.strip()}"
        resp = requests.get(jina_url, timeout=15)
        if resp.status_code == 200:
            return resp.text[:4000]
    except Exception:
        pass
    return ""

# 呼叫 Gemini AI 進行分析
def analyze_with_gemini(key, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }
    resp = requests.post(url, json=payload, timeout=60)
    if resp.status_code != 200:
        raise Exception(f"API 呼叫失敗，請確認 API Key 是否正確。狀態碼：{resp.status_code}")
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

# 建立兩種分析模式的分頁
tab1, tab2 = st.tabs(["🔍 模式一：輸入關鍵字（自動抓取各家媒體）", "📋 模式二：貼上多篇新聞內文／網址（深度比對）"])

with tab1:
    st.subheader("輸入新聞事件關鍵字，一鍵比對台灣各家媒體切角")
    keyword = st.text_input("請輸入近期新聞關鍵字（例如：總預算、電價、大巨蛋、台積電）", placeholder="輸入關鍵字後按下方按鈕")
    
    if st.button("🚀 自動抓取新聞並分析風向", key="btn_kw"):
        if not api_key:
            st.warning("⚠️ 請先在左側欄位輸入你的 Gemini API Key！")
        elif not keyword.strip():
            st.warning("⚠️ 請輸入新聞關鍵字！")
        else:
            with st.spinner("正在從各大媒體抓取最新報導並進行 AI 交叉比對..."):
                try:
                    news_list = fetch_google_news(keyword)
                    if not news_list:
                        st.error("找不到相關新聞，請換個關鍵字試試。")
                    else:
                        with st.expander(f"✅ 已抓取 {len(news_list)} 則不同媒體報導（點此展開原始清單）", expanded=False):
                            for idx, n in enumerate(news_list, 1):
                                st.markdown(f"{idx}. **[{n['source']}]** [{n['title']}]({n['link']})")
                        
                        news_text = "\n".join([f"- 媒體：{n['source']} | 標題：{n['title']}" for n in news_list])
                        prompt = f"""
你是一位專業、客觀的媒體素養與新聞風向分析師。以下是台灣各家媒體針對「{keyword}」的最新報導標題清單：

{news_text}

請根據上述各家媒體的報導切角與用詞，產出結構化的「新聞風向分析報告」（請用繁體中文與 Markdown 表格呈現）：

### 1. 📌 客觀事實交集（還原事件真相）
排除各家媒體的情緒字眼後，這個事件最核心、無爭議的客觀事實是什麼？

### 2. 🎭 各家媒體風向與用詞比較表
請建立一個表格，欄位包含：【媒體名稱】、【報導切角與立場傾向】、【關鍵情緒用字或框架】、【試圖引導受眾產生的觀點】。

### 3. 🔍 媒體盲點與帶風向手法解析
分析這些報導中，有哪些常見的輿論引導手法（例如：貼標籤、因果簡化、放大單一發言）？受眾在閱讀時應注意哪些可能被省略的資訊？
"""
                        result = analyze_with_gemini(api_key, prompt)
                        st.markdown("---")
                        st.markdown(result)
                except Exception as e:
                    st.error(f"發生錯誤：{e}")

with tab2:
    st.subheader("貼上 2～3 篇不同媒體的新聞內文或網址，揪出「刻意遺漏」與「真正來源」")
    col1, col2, col3 = st.columns(3)
    with col1:
        media_a = st.text_area("📰 媒體 A（貼上新聞內文或網址）", height=220, placeholder="例如：貼上某報的新聞全文，或直接貼上新聞網址 https://...")
    with col2:
        media_b = st.text_area("📰 媒體 B（貼上新聞內文或網址）", height=220, placeholder="例如：貼上另一家立場不同媒體的新聞全文或網址")
    with col3:
        media_c = st.text_area("📰 媒體 C（選填，第 3 家媒體）", height=220, placeholder="選填：可再加入第 3 家媒體或新媒體報導")

    if st.button("🔬 進行深度內文交叉比對", key="btn_deep"):
        if not api_key:
            st.warning("⚠️ 請先在左側欄位輸入你的 Gemini API Key！")
        elif not media_a.strip() or not media_b.strip():
            st.warning("⚠️ 請至少在「媒體 A」與「媒體 B」填入兩篇新聞內容或網址！")
        else:
            with st.spinner("正在讀取新聞內容並進行深度語意與來源比對..."):
                try:
                    inputs = [("媒體 A", media_a), ("媒體 B", media_b)]
                    if media_c.strip():
                        inputs.append(("媒體 C", media_c))
                    
                    compiled_articles = ""
                    for label, content in inputs:
                        text = content.strip()
                        if text.startswith("http://") or text.startswith("https://"):
                            extracted = extract_url_text(text)
                            text = extracted if extracted else f"（無法自動讀取網址，僅提供網址：{text}，請改貼上內文以獲得最佳效果）"
                        compiled_articles += f"\n\n--- 【{label}】 ---\n{text}"

                    prompt = f"""
你是一位嚴謹的新聞事實查核員與媒體框架分析專家。請交叉比對以下不同媒體針對同一事件的報導內容：

{compiled_articles}

請產出以下 5 個維度的深度分析報告（請使用繁體中文）：

### 1. ⚖️ 中立還原版新聞（去除所有偏見與形容詞）
請只根據各家報導共同承認的「客觀事實」，用最中立、無情緒的語氣，重新寫出一段 150 字以內的「純淨版新聞摘要」。

### 2. 🔗 真正消息來源與可靠度評分（滿分 100 分）
* 拆解各篇報導的消息來源究竟是什麼？（例如：官方公開文件、具名受訪者、匿名「知情人士」、網友貼文、或是記者自行推論？）
* 為各篇報導的「證據可靠度」打分數（0-100分）並說明扣分原因。

### 3. 📊 用詞框架與情緒引導對照表
請用 Markdown 表格對照各篇報導在描述同一個人物、行為或爭議時，分別使用了什麼不同的動詞與形容詞？各自帶有什麼褒貶暗示？

### 4. 🕳️ 選擇性揭露與「刻意遺漏」（Omission Bias）
哪一篇報導「刻意沒寫到」另一篇報導提到的重要背景、反方說法或當事人澄清？這會對只看單一媒體的讀者造成什麼誤導？

### 5. 💡 給讀者的總結判讀建議
看完這幾篇報導後，讀者應該抱持什麼樣的保留態度？有哪些疑點目前尚未被證實？
"""
                    result = analyze_with_gemini(api_key, prompt)
                    st.markdown("---")
                    st.markdown(result)
                except Exception as e:
                    st.error(f"發生錯誤：{e}")
