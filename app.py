import streamlit as st
import altair as alt
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta

st.set_page_config(
    page_title="政治解盲 | 還原無偏見的純淨事實",
    page_icon="🔍",
    layout="wide"
)

st.markdown("""
<style>
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
#MainMenu { visibility: hidden !important; }
footer { visibility: hidden !important; }

/* 議題主標題橫幅卡片 */
.topic-banner {
    background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-left: 6px solid #f97316;
    border-radius: 12px;
    padding: 18px 24px;
    margin-bottom: 16px;
}
.topic-label {
    font-size: 0.9rem;
    color: #94a3b8;
    margin-bottom: 4px;
}
.topic-title {
    font-size: 2rem;
    font-weight: 800;
    color: #f8fafc;
    line-height: 1.3;
    margin-bottom: 8px;
}
.topic-meta {
    display: inline-block;
    background-color: rgba(34, 197, 94, 0.15);
    color: #4ade80;
    padding: 3px 10px;
    border-radius: 99px;
    font-size: 0.85rem;
    font-weight: 600;
}

/* 四大戰情指標獨立卡片（徹底隔開不碰撞） */
.metric-card {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 16px;
    height: 100%;
}
.metric-head {
    font-size: 0.88rem;
    color: #94a3b8;
    margin-bottom: 8px;
}
.metric-val {
    font-size: 1.5rem;
    font-weight: 800;
    color: #f8fafc;
    line-height: 1.3;
    margin-bottom: 8px;
    word-break: break-word;
}
.metric-sub {
    display: inline-block;
    background-color: rgba(59, 130, 246, 0.15);
    color: #93c5fd;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.82rem;
    line-height: 1.4;
}

/* 3秒看懂真相摘要框 */
.summary-box {
    background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
    border-left: 6px solid #2563eb;
    padding: 20px 24px;
    border-radius: 12px;
    font-size: 1.08rem;
    line-height: 1.85;
    color: #0f172a;
    margin-top: 6px;
    margin-bottom: 22px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

/* 當事人表態對照卡 */
.stance-card {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-top: 4px solid #3b82f6;
    border-radius: 10px;
    padding: 16px 18px;
    margin-bottom: 16px;
    color: #f8fafc;
    min-height: 125px;
}
.stance-title {
    font-weight: 700;
    font-size: 1.02rem;
    margin-bottom: 8px;
    color: #93c5fd;
}
.stance-body {
    font-size: 0.95rem;
    line-height: 1.65;
    color: #e2e8f0;
}

/* 同溫層盲點整合式卡片 */
.blind-card-blue {
    background-color: #172554;
    border: 1px solid #1e40af;
    border-top: 5px solid #3b82f6;
    padding: 20px 22px;
    border-radius: 12px;
    color: #eff6ff;
    line-height: 1.8;
    margin-bottom: 16px;
}
.blind-card-green {
    background-color: #052e16;
    border: 1px solid #166534;
    border-top: 5px solid #22c55e;
    padding: 20px 22px;
    border-radius: 12px;
    color: #f0fdf4;
    line-height: 1.8;
    margin-bottom: 16px;
}
.blind-item {
    background-color: rgba(255, 255, 255, 0.06);
    padding: 10px 14px;
    border-radius: 8px;
    margin-top: 10px;
    font-size: 0.96rem;
    line-height: 1.7;
}

/* 光譜比例尺 */
.spectrum-bar {
    display: flex;
    height: 36px;
    border-radius: 18px;
    overflow: hidden;
    margin: 14px 0;
}
.spectrum-segment {
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 700;
    font-size: 0.86rem;
    white-space: nowrap;
    overflow: hidden;
}
</style>
""", unsafe_allow_html=True)

GREEN_KEYS = [
    "泛綠", "深綠", "偏綠", "自由", "三立", "民視",
    "新頭殼", "Newtalk", "太報", "鏡週刊", "放言"
]
BLUE_KEYS = [
    "泛藍", "深藍", "親中", "聯合", "UDN", "udn", "中時", "中國時報",
    "中天", "TVBS", "風傳媒", "中視", "中廣", "工商", "經濟日報"
]
WHITE_KEYS = ["泛白", "民眾", "匯流", "CNEWS"]

SENSATIONAL_WORDS = [
    "狠酸", "打臉", "翻車", "砲轟", "怒轟", "痛批", "怒批", "嗆", "轟",
    "驚", "爆", "急了", "傻眼", "洗臉", "跳腳", "開戰", "吵成一團",
    "鬆一口氣", "強行", "闖關", "黑箱", "自肥", "掏空", "神隱", "打假球",
    "變調", "鬆口", "大罵", "反擊", "踢爆", "怒斥", "狂酸", "炒不起來",
    "救", "難發酵", "力拚", "力拼", "破局", "打槍", "切割", "！", "!"
]


def classify_camp(source_item):
    tag = source_item.get("bias_tag", "")
    name = source_item.get("source", "")
    text = f"{name} {tag}"
    if any(k in text for k in GREEN_KEYS):
        return "泛綠傾向"
    if any(k in text for k in BLUE_KEYS):
        return "泛藍傾向"
    if any(k in text for k in WHITE_KEYS):
        return "泛白／第三勢力"
    return "中立／綜合媒體"


def calc_emotion_metric(sources):
    if not sources:
        return "0%", "🟢 平實陳述為主"
    hit_count = 0
    for s in sources:
        title = s.get("title", "")
        if any(w in title for w in SENSATIONAL_WORDS):
            hit_count += 1
    ratio = round(hit_count / len(sources) * 100)
    if ratio >= 50:
        label = f"🔴 高度煽動（{hit_count}篇含情緒詞）"
    elif ratio >= 25:
        label = f"🟡 攻防激烈（{hit_count}篇含情緒詞）"
    else:
        label = f"🟢 平實陳述（僅{hit_count}篇含情緒詞）"
    return f"{ratio}% 煽動度", label


def detect_agenda_leader(current, parsed, camp_counts):
    report_text = current.get("report", "")
    m = re.search(r"【議題主導陣營】[：:\s\*]*(.+?)(?:\n|\*\*【|$)", report_text)
    if m:
        raw = m.group(1).strip().strip("*")
        parts = raw.split("｜") if "｜" in raw else [raw, "主導本時段輿論攻防"]
        return parts[0].strip(), parts[1].strip()

    topic = current.get("topic", "")
    summary = parsed.get("summary", "")
    sec1 = parsed.get("sec1", "")
    combined = f"{topic} {summary}"

    has_blue = any(k in combined for k in ["國民黨", "藍營", "蔣萬安", "韓國瑜"])
    has_green = any(k in combined for k in ["民進黨", "綠營", "行政院", "卓榮泰", "賴清德"])
    has_white = any(k in combined for k in ["民眾黨", "白營", "柯文哲", "黃國昌"])

    n_blue = camp_counts["泛藍傾向"]
    n_green = camp_counts["泛綠傾向"]

    if has_blue and has_white and not has_green:
        return "🟦⬜ 藍白雙邊交鋒", "藍白陣營互動成輿論焦點"
    if "拉鋸" in sec1 or (has_blue and has_green):
        if n_blue > n_green + 3:
            return "🟦 藍營主導戰場", "在野拋出議題・執政防守反擊"
        if n_green > n_blue + 3:
            return "🟩 綠營主導戰場", "執政強勢定調・在野攻防"
        return "⚔️ 朝野攻防拉鋸", "藍綠雙方陣營互有攻守"
    if n_green >= n_blue * 1.5 and n_green > 5:
        return "🟩 泛綠主導戰場", "綠營媒體高密度發動議題"
    if n_blue >= n_green * 1.5 and n_blue > 5:
        return "🟦 泛藍主導戰場", "藍營媒體高密度發動議題"
    return "⚖️ 跨陣營共同關注", "各陣營媒體皆高比例跟進"


def extract_stances(current, parsed):
    report_text = current.get("report", "")
    stances = []

    block_m = re.search(
        r"【當事人表態對照】[：:\s\*]*(.*?)(?=\n###|\n---|\Z)",
        report_text,
        re.DOTALL
    )
    if block_m:
        raw_block = block_m.group(1).strip()
        # 支援單行或多行星號切割
        items = re.split(r"(?:\n\s*[\*\-•]\s*|\s+\*\s+)", raw_block)
        for item in items:
            line = item.strip().lstrip("*-• ").strip("*")
            if "：" in line or ":" in line:
                sep = "：" if "：" in line else ":"
                actor, quote = line.split(sep, 1)
                actor = actor.strip().strip("*[]【】")
                quote = quote.strip().strip("*")
                if actor and quote:
                    stances.append((actor, quote))
        if stances:
            return stances[:4]

    summary = parsed.get("summary", "")
    sentences = [s.strip() for s in re.split(r"[。；]", summary) if len(s.strip()) > 6]

    actor_rules = [
        ("🟦 國民黨／藍營立場", ["國民黨", "藍營", "蔣萬安", "韓國瑜"]),
        ("🟩 行政院／綠營立場", ["行政院長", "卓榮泰", "行政院", "民進黨", "賴清德", "沈伯洋"]),
        ("⬜ 民眾黨／白營立場", ["民眾黨", "柯文哲", "黃國昌", "白營"]),
        ("🏛️ 主管機關／院會進度", ["財政部", "立法院", "朝野協商", "院會"])
    ]

    used_sentences = set()
    for label, keywords in actor_rules:
        matched_parts = []
        for idx, sent in enumerate(sentences):
            if idx in used_sentences:
                continue
            if any(k in sent for k in keywords):
                matched_parts.append(sent)
                used_sentences.add(idx)
        if matched_parts:
            stances.append((label, "。".join(matched_parts) + "。"))

    if len(stances) < 2 and sentences:
        stances = []
        for sent in sentences[:3]:
            if "柯文哲" in sent:
                stances.append(("⬜ 柯文哲（民眾黨）", sent + "。"))
            elif "蔣萬安" in sent:
                stances.append(("🟦 蔣萬安（國民黨）", sent + "。"))
            else:
                stances.append(("⚖️ 事件關鍵動態", sent + "。"))

    return stances[:3]


def format_blindspot_items(raw_text):
    """將盲點文字拆解為獨立條列區塊，不再擠成一團"""
    if not raw_text:
        return ""
    cleaned = re.sub(r"^這群讀者.*?(?:看不見|錯過)[：:\s]*", "", raw_text.strip())
    parts = re.split(r"(?:\n\s*[\*\-•]\s*|\s+\*\s+)", cleaned)
    parts = [p.strip().strip("*") for p in parts if len(p.strip().strip("*")) > 4]

    if len(parts) == 1 and "。" in parts[0]:
        sents = [s.strip() + "。" for s in parts[0].split("。") if len(s.strip()) > 6]
        if len(sents) > 1:
            parts = sents

    html_items = "".join([f'<div class="blind-item">• {p}</div>' for p in parts])
    return html_items


def parse_report_data(report_md):
    cleaned = re.sub(r"^好的，.*?\n+", "", report_md.strip())

    # 精準擷取摘要：遇到【議題主導陣營】或【當事人表態對照】立即停止，絕不吸進後續文字
    summary = ""
    sum_pattern = (
        r"【中立客觀事實摘要】[：:\s\*]*(.+?)"
        r"(?=\s*\*{0,2}【議題主導陣營】|\s*\*{0,2}【當事人表態對照】|\n---|\n###|\n\n)"
    )
    sum_match = re.search(sum_pattern, cleaned, re.DOTALL)
    if sum_match:
        summary = sum_match.group(1).strip().strip("*")

    score = 75
    score_pattern = r"可靠度評分(?:\s*[\(（].*?[\)）])?[：:\s\*]*(\d{1,3})\s*分"
    score_match = re.search(score_pattern, cleaned)
    if score_match:
        score = min(100, max(0, int(score_match.group(1))))

    sec1, sec2, sec3 = "", "", ""
    s1_m = re.search(r"###\s*1\..*?\n(.*?)(?=###\s*2\.|\Z)", cleaned, re.DOTALL)
    s2_m = re.search(r"###\s*2\..*?\n(.*?)(?=###\s*3\.|\Z)", cleaned, re.DOTALL)
    s3_m = re.search(r"###\s*3\..*?\n(.*?)(?=\Z)", cleaned, re.DOTALL)
    if s1_m:
        sec1 = s1_m.group(1).strip()
    if s2_m:
        sec2 = s2_m.group(1).strip()
    if s3_m:
        sec3 = s3_m.group(1).strip()

    blue_blind, green_blind = "", ""
    if sec2:
        b_pat = r"(?:只看泛藍|泛藍).*?盲點[：:\*\s]*(.*?)(?=(?:\*\s*)?\*\*?(?:只看泛綠|泛綠)|\Z)"
        g_pat = r"(?:只看泛綠|泛綠).*?盲點[：:\*\s]*(.*?)(?=\Z)"
        b_m = re.search(b_pat, sec2, re.DOTALL)
        g_m = re.search(g_pat, sec2, re.DOTALL)
        if b_m:
            blue_blind = b_m.group(1).strip()
        if g_m:
            green_blind = g_m.group(1).strip()

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


st.title("🔍 政治解盲")
st.caption("每日早（08:00）、中（12:30）、晚（19:00）自動鎖定全台最大政治議題，交叉比對各方媒體，破解同溫層盲區，還原無偏見的純淨事實。")

data_file = "news_history.json"

if not os.path.exists(data_file):
    st.info("⏳ 系統正在準備第一份報告！請先至 GitHub Actions 執行一次 Run workflow。")
else:
    with open(data_file, "r", encoding="utf-8") as f:
        history = json.load(f)

    if not history:
        st.warning("目前尚無歷史資料。")
    else:
        with st.sidebar:
            st.header("🗓️ 選擇觀測時段")
            options = [
                f"【{item['period']}】{item['date_str']} - {item['topic']}"
                for item in history
            ]
            selected_idx = st.radio(
                "歷史分析紀錄（最新在最上方）：",
                range(len(options)),
                format_func=lambda i: options[i]
            )
            st.divider()
            st.subheader("📊 儀表板閱讀指南")
            st.caption("• 情緒煽動度：統計標題含強烈情緒字眼之比例，防範標題殺人。")
            st.caption("• 議題主導陣營：判讀本波輿論戰由哪一方設定戰場。")
            st.caption("• 當事人表態卡：並排對照各方核心說法，秒懂爭點。")
            st.caption("• 盲點雙欄卡：左右對照藍綠受眾各自被隱藏的資訊。")

        current = history[selected_idx]
        sources = current.get("sources", [])
        parsed = parse_report_data(current.get("report", ""))
        camp_counts = Counter(classify_camp(s) for s in sources)

        valid_sources = [
            s for s in sources
            if s.get("time_str") and s.get("time_str") != "未知時間"
        ]
        if valid_sources:
            first_source = valid_sources[0]
        elif sources:
            first_source = sources[0]
        else:
            first_source = {"source": "無", "time_str": "無", "title": ""}

        # 第一排：獨立橫幅卡片顯示本時段最大議題
        st.markdown(f"""
        <div class="topic-banner">
            <div class="topic-label">🔥 本時段最大政治議題</div>
            <div class="topic-title">{current["topic"]}</div>
            <span class="topic-meta">
                📅 {current["period"]}｜{current["date_str"]}（跨媒體比對 {current["article_count"]} 篇報導）
            </span>
        </div>
        """, unsafe_allow_html=True)

        # 第二排：四大戰情指標（各自獨立邊框卡片，絕不擠在一起）
        score = parsed["score"]
        if score >= 75:
            score_label = "🟢 高可靠度（具名事實為主）"
        elif score >= 60:
            score_label = "🟡 中等（夾雜政黨推論）"
        else:
            score_label = "🔴 偏低（多匿名放話／帶風向）"

        emo_val, emo_label = calc_emotion_metric(sources)
        leader_val, leader_label = detect_agenda_leader(current, parsed, camp_counts)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-head">🛡️ 消息來源可靠度</div>
                <div class="metric-val">{score} / 100 分</div>
                <div class="metric-sub">{score_label}</div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-head">🎭 標題情緒煽動度</div>
                <div class="metric-val">{emo_val}</div>
                <div class="metric-sub">{emo_label}</div>
            </div>
            """, unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-head">📣 議題主導陣營</div>
                <div class="metric-val">{leader_val}</div>
                <div class="metric-sub">{leader_label}</div>
            </div>
            """, unsafe_allow_html=True)
        with c4:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-head">🥇 最早首發媒體</div>
                <div class="metric-val">{first_source["source"]}</div>
                <div class="metric-sub">🕒 首發時間：{first_source["time_str"][-5:]}</div>
            </div>
            """, unsafe_allow_html=True)

        # 第三排：純淨版中立事實 3 秒快讀區
        if parsed["summary"]:
            st.markdown(f"""
            <div class="summary-box">
                <strong>⚖️ 【3秒看懂真相】去偏見中立事實摘要：</strong><br>
                {parsed["summary"]}
            </div>
            """, unsafe_allow_html=True)

        # 第四排：當事人表態對照卡
        stances = extract_stances(current, parsed)
        if stances:
            st.markdown("##### 🗣️ 當事人與各方核心表態對照")
            s_cols = st.columns(len(stances))
            for idx, (actor, quote) in enumerate(stances):
                border_color = "#3b82f6"
                if any(w in actor for w in ["綠", "政院", "民進黨", "沈伯洋", "卓榮泰", "賴清德"]):
                    border_color = "#22c55e"
                elif any(w in actor for w in ["白", "柯", "民眾黨", "黃國昌"]):
                    border_color = "#06b6d4"
                elif any(w in actor for w in ["機關", "院會", "動態", "財政部"]):
                    border_color = "#eab308"
                with s_cols[idx]:
                    st.markdown(f"""
                    <div class="stance-card" style="border-top-color: {border_color};">
                        <div class="stance-title">{actor}</div>
                        <div class="stance-body">{quote}</div>
                    </div>
                    """, unsafe_allow_html=True)

        st.write("")
        col_left, col_right = st.columns([1.35, 1])

        with col_left:
            st.subheader("🌈 媒體立場報導聲量光譜")
            total = max(len(sources), 1)

            n_blue = camp_counts["泛藍傾向"]
            n_white = camp_counts["泛白／第三勢力"]
            n_neutral = camp_counts["中立／綜合媒體"]
            n_green = camp_counts["泛綠傾向"]

            p_blue = round(n_blue / total * 100)
            p_white = round(n_white / total * 100)
            p_neutral = round(n_neutral / total * 100)
            p_green = max(0, 100 - p_blue - p_white - p_neutral)

            def seg_label(name, pct):
                if pct >= 14:
                    return f"{name} {pct}%"
                if pct >= 6:
                    return f"{pct}%"
                return ""

            segments = []
            if p_blue > 0:
                segments.append(
                    f'<div class="spectrum-segment" style="width:{p_blue}%;'
                    f'background:#2563eb;">{seg_label("🟦 泛藍", p_blue)}</div>'
                )
            if p_white > 0:
                segments.append(
                    f'<div class="spectrum-segment" style="width:{p_white}%;'
                    f'background:#06b6d4;">{seg_label("⬜ 泛白", p_white)}</div>'
                )
            if p_neutral > 0:
                segments.append(
                    f'<div class="spectrum-segment" style="width:{p_neutral}%;'
                    f'background:#64748b;">{seg_label("🟨 中立與綜合", p_neutral)}</div>'
                )
            if p_green > 0:
                segments.append(
                    f'<div class="spectrum-segment" style="width:{p_green}%;'
                    f'background:#16a34a;">{seg_label("🟩 泛綠", p_green)}</div>'
                )

            bar_html = '<div class="spectrum-bar">' + "".join(segments) + '</div>'
            st.markdown(bar_html, unsafe_allow_html=True)

            m1, m2, m3, m4 = st.columns(4)
            m1.caption(f"🟦 **泛藍傾向**：{n_blue} 篇 ({p_blue}%)")
            m2.caption(f"⬜ **泛白傾向**：{n_white} 篇 ({p_white}%)")
            m3.caption(f"🟨 **中立／綜合**：{n_neutral} 篇 ({p_neutral}%)")
            m4.caption(f"🟩 **泛綠傾向**：{n_green} 篇 ({p_green}%)")

            if p_green >= p_blue * 2 and p_green > 30:
                st.warning("📢 聲量提示：本時段泛綠媒體報導密集度明顯較高。")
            elif p_blue >= p_green * 2 and p_blue > 30:
                st.warning("📢 聲量提示：本時段泛藍媒體報導密集度明顯較高。")
            else:
                st.success("⚖️ 聲量提示：本時段藍綠與綜合媒體皆有高度關注，屬跨陣營交鋒議題。")

        with col_right:
            st.subheader("📈 輿論發酵時間軸（各小時發稿量）")
            parsed_dts = []
            for s in valid_sources:
                try:
                    dt = datetime.strptime(s["time_str"], "%Y-%m-%d %H:%M")
                    parsed_dts.append(dt.replace(minute=0, second=0))
                except Exception:
                    pass

            if parsed_dts:
                min_dt, max_dt = min(parsed_dts), max(parsed_dts)
                dt_counts = Counter(parsed_dts)
                chart_values = []
                curr_dt = min_dt
                idx = 0
                while curr_dt <= max_dt:
                    if min_dt.date() == max_dt.date():
                        label = curr_dt.strftime("%H:00")
                    else:
                        label = curr_dt.strftime("%m/%d %H:00")
                    chart_values.append({
                        "time": label,
                        "count": dt_counts.get(curr_dt, 0),
                        "order": idx
                    })
                    curr_dt += timedelta(hours=1)
                    idx += 1

                line_chart = (
                    alt.Chart(alt.Data(values=chart_values))
                    .mark_line(point=True, color="#3b82f6", strokeWidth=3)
                    .encode(
                        x=alt.X(
                            "time:N",
                            sort=alt.EncodingSortField(field="order", order="ascending"),
                            axis=alt.Axis(
                                labelAngle=0,
                                labelOverlap=True,
                                title=None
                            )
                        ),
                        y=alt.Y(
                            "count:Q",
                            scale=alt.Scale(domainMin=0),
                            axis=alt.Axis(title=None, tickMinStep=1)
                        ),
                        tooltip=[
                            alt.Tooltip("time:N", title="時段"),
                            alt.Tooltip("count:Q", title="發稿篇數")
                        ]
                    )
                    .properties(height=195)
                )
                st.altair_chart(line_chart, use_container_width=True)
            else:
                st.info("尚無足夠時間戳記繪製圖表")

        st.divider()

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
                    b_items_html = format_blindspot_items(parsed["blue_blind"])
                    st.markdown(f"""
                    <div class="blind-card-blue">
                        <h4 style="margin:0 0 6px 0; color:#93c5fd;">🟦 只看【泛藍／泛白媒體】受眾的盲點</h4>
                        <div style="font-size:0.88rem; color:#cbd5e1; margin-bottom:10px;">
                            以下為執政黨數據、背景或反駁，在藍白媒體中較少被凸顯：
                        </div>
                        {b_items_html}
                    </div>
                    """, unsafe_allow_html=True)
                with g_col:
                    g_items_html = format_blindspot_items(parsed["green_blind"])
                    st.markdown(f"""
                    <div class="blind-card-green">
                        <h4 style="margin:0 0 6px 0; color:#86efac;">🟩 只看【泛綠媒體】受眾的盲點</h4>
                        <div style="font-size:0.88rem; color:#cbd5e1; margin-bottom:10px;">
                            以下為在野黨質疑、程序爭議或民意反彈，在綠營媒體中較少被凸顯：
                        </div>
                        {g_items_html}
                    </div>
                    """, unsafe_allow_html=True)
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
            st.progress(
                parsed["score"] / 100,
                text=f"🛡️ 本議題消息來源可靠度評分：{parsed['score']} / 100 分"
            )
            if parsed["sec3"]:
                st.markdown(parsed["sec3"])
            else:
                st.markdown(parsed["cleaned"])

        with tab4:
            st.markdown("#### 🔍 依發布時間戳記排序之原始新聞清單")
            filter_camp = st.radio(
                "點選篩選特定媒體立場：",
                [
                    "全部顯示",
                    "🟦 泛藍傾向",
                    "🟩 泛綠傾向",
                    "⬜ 泛白／第三勢力",
                    "🟨 中立／綜合媒體"
                ],
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
                st.markdown(
                    f"`#{idx:02d}` **{src['time_str']}** ｜ {badge} "
                    f"**[{src['source']}]** [{src['title']}]({src['link']}){first_tag}"
                )
