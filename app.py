import streamlit as st
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta

st.set_page_config(page_title="台灣政治新聞風向與溯源觀測站", page_icon="📡", layout="wide")

# 自訂 CSS 美化儀表板卡片與光譜條
st.markdown("""
<style>
.kpi-card {
    background-color: #f8fafc;
    border-radius: 12px;
    padding: 18px 20px;
    border: 1px solid #e2e8f0;
    height: 100%;
}
.summary-box {
    background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
    border-left: 6px solid #2563eb;
    padding: 18px 22px;
    border-radius: 10px;
    font-size: 1.05rem;
    line-height: 1.7;
    color: #1e293b;
    margin-bottom: 16px;
}
.blindspot-blue {
    background-color: #eff6ff;
    border-top: 5px solid #2563eb;
    padding: 18px;
    border-radius: 10px;
    color: #1e293b;
}
.blindspot-green {
    background-color: #f0fdf4;
    border-top: 5px solid #16a34a;
    padding: 18px;
    border-radius: 10px;
    color: #1e293b;
}
.spectrum-bar {
    display: flex;
    height: 34px;
    border-radius: 17px;
    overflow: hidden;
    margin: 12px 0;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
}
.spectrum-segment {
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 700;
    font-size: 0.88rem;
    white-space: nowrap;
}
</style>
""", unsafe_allow_html=True)

def classify_camp(source_item):
    """根據媒體名稱與標籤歸類為四大光譜陣營"""
    tag = source_item.get("bias_tag", "")
    name = source_item.get("source", "")
    text = f"{name} {tag}"
    if any(k in text for k in ["泛綠", "深綠", "偏綠", "自由", "三立", "民視", "新頭殼", "Newtalk", "太報", "鏡週刊", "放言"]):
        return "泛綠傾向"
    if any(k in text for k in ["泛藍", "深藍", "親中", "聯合", "UDN", "中時", "中國時報", "中天", "TVBS", "風傳媒", "中視", "中廣", "工商", "經濟日報"]):
        return "泛藍傾向"
    if any(k in text for k in ["泛白", "民眾", "匯流", "CNEWS"]):
        return "泛白／第三勢力"
    return "中立／綜合媒體"

def parse_report_data(report_md):
    """從 AI 報告文字中自動萃取摘要、可靠度分數與各章節內容"""
    # 1. 移除開頭的 AI 客套話
    cleaned = re.sub(r"^好的，.*?\n+", "", report_md.strip())

    # 2. 萃取中立事實摘要
    summary = ""
    sum_match = re.search(r"【中立客觀事實摘要】[：:\s\*]*(.+?)(?=\n---|\n###|\n\n)", cleaned, re.DOTALL)
    if sum_match:
        summary = sum_match.group(1).strip().strip("*")

    # 3. 萃取可靠度分數 (跳過括號內的 0~100分，精準抓取冒號後的實際分數)
    score = 75
    score_match = re.search(r"可靠度評分(?:\s*[\(（].*?[\)）])?[：:\s\*]*(\d{1,3})\s*分", cleaned)
    if score_match:
        score = min(100, max(0, int(score_match.group(1))))

    # 4. 切割三大章節
    sec1, sec2, sec3 = "", "", ""
    s1_m = re.search(r"###\s*1\..*?\n(.*?)(?=###\s*2\.|\Z)", cleaned, re.DOTALL)
    s2_m = re.search(r"###\s*2\..*?\n(.*?)(?=###\s*3\.|\Z)", cleaned, re.DOTALL)
    s3_m = re.search(r"###\s*3\..*?\n(.*?)(?=\Z)", cleaned, re.DOTALL)
    if s1_m: sec1 = s1_m.group(1).strip()
    if s2_m: sec2 = s2_m.group(1).strip()
    if s3_m: sec3 = s3_m.group(1).strip()

    # 5. 拆分藍白盲點與泛綠盲點
    blue_blind, green_blind = "", ""
    if sec2:
        b_m = re.search(r"(?:只看泛藍|泛藍).*?盲點[：:\*\s]*(.*?)(?=(?:\*\s*)?\*\*?(?:只看泛綠|泛綠)|\Z)", sec2, re.DOTALL)
        g_m = re.search(r"(?:只看泛綠|泛綠).*?盲點[：:\*\s]*(.*?)(?=\Z)", sec2, re.DOTALL)
        if b_m: blue_blind = b_m.group(1).strip()
        if g_m: green_blind = g_m.group(1).strip()

    return {
        "cleaned": cleaned,
        "summary": summary,
        "score": score,
        "sec1": sec1,
        "sec2": sec2,
        "sec3": sec3,
        "blue_blind": blue_blind,
        "green_blind": green_blind
    }

st.title("📡 台灣政治新聞風向、盲點與源頭追蹤觀測站")
st.caption("每日早（08:00）、中（12:30）、晚（19:00）自動鎖定全台報導量最大之政治議題，透過視覺化儀表板秒懂政黨立場、同溫層盲點與首發消息源頭。")

data_file = "news_history.json"

if not os.path.exists(data_file):
    st.info("⏳ 系統正在準備第一份自動分析報告！請先至 GitHub Actions 點擊一次「Run workflow」即可立即產生第一篇報告。")
else:
    with open(data_file, "r", encoding="utf-8") as f:
        history = json.load(f)

    if not history:
        st.warning("目前尚無歷史資料。")
    else:
        with st.sidebar:
            st.header("🗓️ 選擇觀測時段")
            options = [f"【{item['period']}】{item['date_str']} - {item['topic']}" for item in history]
            selected_idx = st.radio("歷史分析紀錄（最新在最上方）：", range(len(options)), format_func=lambda i: options[i])
            st.divider()
            st.markdown("### 📊 儀表板閱讀指南\n* **光譜比例尺**：一眼看出哪個政黨陣營媒體在主導話題。\n* **可靠度分數**：80分以上代表具名官方事實居多；低於60分代表多為匿名放話或情緒推論。\n* **盲點雙欄卡**：左右對照藍
