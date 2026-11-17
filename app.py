import streamlit as st
import json
import os
import re
from collections import Counter

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

    # 3. 萃取可靠度分數 (0~100)
    score = 75
    score_match = re.search(r"可靠度評分.*?(\d{1,3})\s*分", cleaned)
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
            st.markdown("### 📊 儀表板閱讀指南\n* **光譜比例尺**：一眼看出哪個政黨陣營媒體在主導話題。\n* **可靠度分數**：80分以上代表具名官方事實居多；低於60分代表多為匿名放話或情緒推論。\n* **盲點雙欄卡**：左右對照藍綠受眾各自被隱藏的真相。")

        current = history[selected_idx]
        sources = current.get("sources", [])
        parsed = parse_report_data(current.get("report", ""))

        # 找出首發媒體
        valid_sources = [s for s in sources if s.get("time_str") and s.get("time_str") != "未知時間"]
        first_source = valid_sources[0] if valid_sources else (sources[0] if sources else {"source": "無", "time_str": "無", "title": ""})

        # ==========================================
        # 儀表板 1：頂部四大核心戰情指標卡
        # ==========================================
        c1, c2, c3, c4 = st.columns([1.3, 1.1, 1.2, 1.4])
        with c1:
            st.metric("🔥 本時段最大議題", current["topic"], f"{current['period']}｜{current['date_str']}")
        with c2:
            score = parsed["score"]
            score_label = "高可靠度（具名事實為主）" if score >= 75 else ("中等（夾雜政黨推論）" if score >= 60 else "偏低（多匿名放話／帶風向）")
            st.metric("🛡️ 消息來源可靠度", f"{score} / 100 分", score_label)
        with c3:
            st.metric("🥇 最早首發媒體", first_source["source"], f"首發時間：{first_source['time_str'][-5:]}")
        with c4:
            st.metric("📰 跨媒體比對樣本", f"{current['article_count']} 篇報導", "涵蓋藍・綠・白・中立媒體")

        # 中立事實 3 秒快讀區 + 可靠度進度條
        if parsed["summary"]:
            st.markdown(f"""
            <div class="summary-box">
                <strong>⚖️ 【3秒看懂真相】去偏見中立事實摘要：</strong><br>
                {parsed["summary"]}
            </div>
            """, unsafe_allow_html=True)

        # ==========================================
        # 儀表板 2：媒體政黨光譜分佈比例尺 & 發酵時間軸
        # ==========================================
        col_left, col_right = st.columns([1.35, 1])

        with col_left:
            st.subheader("🌈 媒體立場報導聲量光譜（Ground News 視覺化）")
            camp_counts = Counter(classify_camp(s) for s in sources)
            total = max(len(sources), 1)
            
            n_blue = camp_counts["泛藍傾向"]
            n_white = camp_counts["泛白／第三勢力"]
            n_neutral = camp_counts["中立／綜合媒體"]
            n_green = camp_counts["泛綠傾向"]

            p_blue = round(n_blue / total * 100)
            p_white = round(n_white / total * 100)
            p_neutral = round(n_neutral / total * 100)
            p_green = max(0, 100 - p_blue - p_white - p_neutral)

            bar_html = '<div class="spectrum-bar">'
            if p_blue > 0:
                bar_html += f'<div class="spectrum-segment" style="width:{p_blue}%; background:#2563eb;" title="泛藍傾向: {n_blue}篇">🟦 泛藍 {p_blue}%</div>'
            if p_white > 0:
                bar_html += f'<div class="spectrum-segment" style="width:{p_white}%; background:#06b6d4;" title="泛白傾向: {n_white}篇">⬜ 泛白 {p_white}%</div>'
            if p_neutral > 0:
                bar_html += f'<div class="spectrum-segment" style="width:{p_neutral}%; background:#64748b;" title="中立/綜合: {n_neutral}篇">🟨 中立與綜合 {p_neutral}%</div>'
            if p_green > 0:
                bar_html += f'<div class="spectrum-segment" style="width:{p_green}%; background:#16a34a;" title="泛綠傾向: {n_green}篇">🟩 泛綠 {p_green}%</div>'
            bar_html += '</div>'
            st.markdown(bar_html, unsafe_allow_html=True)

            m1, m2, m3, m4 = st.columns(4)
            m1.caption(f"🟦 **泛藍傾向**：{n_blue} 篇")
            m2.caption(f"⬜ **泛白傾向**：{n_white} 篇")
            m3.caption(f"🟨 **中立／綜合**：{n_neutral} 篇")
            m4.caption(f"🟩 **泛綠傾向**：{n_green} 篇")

            # 自動判斷聲量偏見警報
            if p_green >= p_blue * 2 and p_green > 30:
                st.warning("📢 **聲量風向提示**：本時段 **泛綠媒體** 報導密集度明顯高於泛藍媒體，議題主要由綠營或執政視角發動攻防。")
            elif p_blue >= p_green * 2 and p_blue > 30:
                st.warning("📢 **聲量風向提示**：本時段 **泛藍媒體** 報導密集度明顯高於泛綠媒體，議題主要由在野視角發動攻防。")
            else:
                st.success("⚖️ **聲量風向提示**：本時段藍綠與綜合媒體皆有高度關注，屬於跨陣營全面交鋒之焦點議題。")

        with col_right:
            st.subheader("⏱️ 輿論發酵時間軸（各小時發稿量）")
            hour_counts = Counter()
            for s in valid_sources:
                # 取出小時 HH:00
                parts = s["time_str"].split(" ")
                if len(parts) == 2:
                    hh = parts[1][:2] + ":00"
                    hour_counts[hh] += 1
            if hour_counts:
                sorted_hours = dict(sorted(hour_counts.items()))
                st.bar_chart(sorted_hours, height=195, color="#3b82f6")
            else:
                st.info("尚無足夠時間戳記繪製圖表")

        st.divider()

        # ==========================================
        # 儀表板 3：四大結構化分頁（解決長文閱讀疲勞）
        # ==========================================
        tab1, tab2, tab3, tab4 = st.tabs([
            "🕳️ 同溫層盲點雙欄對照",
            "🧭 政黨風向與用詞比較表",
            "🕵️‍♂️ 源頭追蹤與真偽拆解",
            f"📰 原始報導立場篩選器 ({len(sources)}篇)"
        ])

        with tab1:
            st.markdown("#### 👁️ 只看單一陣營媒體，你會錯過什麼關鍵資訊？")
            if parsed["blue_blind"] and parsed["green_blind"]:
                b_col, g_col = st.columns(2)
                with b_col:
                    st.markdown('<div class="blindspot-blue"><h4>🟦 只看【泛藍／泛白媒體】受眾的盲點</h4><p style="font-size:0.9rem;color:#475569;">以下為執政黨數據、背景或反駁，在藍白媒體中較少被凸顯：</p></div>', unsafe_allow_html=True)
                    st.markdown(parsed["blue_blind"])
                with g_col:
                    st.markdown('<div class="blindspot-green"><h4>🟩 只看【泛綠媒體】受眾的盲點</h4><p style="font-size:0.9rem;color:#475569;">以下為在野黨質疑、程序爭議或民意反彈，在綠營媒體中較少被凸顯：</p></div>', unsafe_allow_html=True)
                    st.markdown(parsed["green_blind"])
            elif parsed["sec2"]:
                st.markdown(parsed["sec2"])
            else:
                st.markdown(parsed["cleaned"])

        with tab2:
            st.markdown("#### 🎭 各陣營媒體敘事框架與情緒用字拆解")
            if parsed["sec1"]:
                st.markdown(parsed["sec1"])
            else:
                st.markdown(parsed["cleaned"])

        with tab3:
            st.markdown("#### 🔗 誰是第一家發新聞的源頭？哪些內容只是政黨帶風向？")
            st.progress(parsed["score"] / 100, text=f"🛡️ 本議題消息來源可靠度評分：{parsed['score']} / 100 分")
            if parsed["sec3"]:
                st.markdown(parsed["sec3"])
            else:
                st.markdown(parsed["cleaned"])

        with tab4:
            st.markdown("#### 🔍 依發布時間戳記排序之原始新聞清單（可依政黨光譜篩選）")
            filter_camp = st.radio(
                "點選篩選特定媒體立場：",
                ["全部顯示", "🟦 泛藍傾向", "🟩 泛綠傾向", "⬜ 泛白／第三勢力", "🟨 中立／綜合媒體"],
                horizontal=True
            )
            camp_badge = {
                "泛藍傾向": "🟦 泛藍",
                "泛綠傾向": "🟩 泛綠",
                "泛白／第三勢力": "⬜ 泛白",
                "中立／綜合媒體": "🟨 中立/綜合"
            }
            for idx, src in enumerate(sources, 1):
                c_type = classify_camp(src)
                if filter_camp != "全部顯示" and not filter_camp.endswith(c_type):
                    continue
                badge = camp_badge.get(c_type, "🟨 綜合")
                first_tag = " 🏆 **【全網首發】**" if idx == 1 else ""
                st.markdown(f"`#{idx:02d}` **{src['time_str']}** ｜ {badge} **[{src['source']}]** [{src['title']}]({src['link']}){first_tag}")
