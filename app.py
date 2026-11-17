import streamlit as st
import json
import os

st.set_page_config(page_title="台灣政治新聞風向與溯源觀測站", page_icon="📡", layout="wide")

st.title("📡 台灣政治新聞風向、盲點與源頭追蹤觀測站")
st.caption("每日早（08:00）、中（12:30）、晚（19:00）自動鎖定全台報導量最大之政治議題，拆解政黨立場、同溫層盲點與最早消息源頭。")

data_file = "news_history.json"

if not os.path.exists(data_file):
    st.info("⏳ 系統正在準備第一份自動分析報告！請先至 GitHub Actions 點擊一次「Run workflow」即可立即產生第一篇報告。")
else:
    with open(data_file, "r", encoding="utf-8") as f:
        history = json.load(f)

    if not history:
        st.warning("目前尚無歷史資料。")
    else:
        # 側邊欄：選擇歷史期數
        with st.sidebar:
            st.header("🗓️ 選擇觀測時段")
            options = [f"【{item['period']}】{item['date_str']} - {item['topic']}" for item in history]
            selected_idx = st.radio("歷史分析紀錄（最新在最上方）：", range(len(options)), format_func=lambda i: options[i])
            st.divider()
            st.markdown("### ℹ️ 觀測站三大指標\n1. **政黨風向**：比對藍、綠、白與中立媒體的切角。\n2. **同溫層盲點**：揭露單一陣營刻意忽略的資訊。\n3. **時間戳記溯源**：依發布時間由舊到新排序，抓出首發源頭與轉載鏈。")

        current = history[selected_idx]

        # 頂部資訊卡
        col1, col2, col3 = st.columns(3)
        col1.metric("📅 觀測時段", f"{current['date_str']} ({current['period']})")
        col2.metric("🔥 最大政治議題", current["topic"])
        col3.metric("📰 納入比對報導數", f"{current['article_count']} 篇")

        st.divider()

        # 顯示 AI 深度報告
        st.markdown(current["report"])

        st.divider()

        # 顯示原始時間戳記排序清單（供查證誰是第一家發新聞的媒體）
        with st.expander("🕒 點此展開：各家媒體發布時間戳記完整排序（由最早首發到最新跟進）", expanded=False):
            st.caption("以下清單依新聞發布時間由舊到新排列，最上方即為最早發布該議題之媒體：")
            for idx, src in enumerate(current.get("sources", []), 1):
                st.markdown(f"`{idx:02d}` **{src['time_str']}** ｜ **[{src['source']}]** [{src['title']}]({src['link']})")
