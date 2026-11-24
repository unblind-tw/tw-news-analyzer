import streamlit as st
import altair as alt
import html
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta

st.set_page_config(
    page_title="政治解盲 | 跨媒體立場對照與盲點觀測站",
    page_icon="🔍",
    layout="wide"
)

# ==========================================
# 🔗 外部導流與贊助連結設定區（修改這裡即可同步全站按鈕）
# ==========================================
LINE_ADD_URL = "https://lin.ee/請換成你的LINE加好友網址"
DONATE_URL = "https://vocus.cc/pay/donate/@unblindnews?donateSourceType=exclusiveLink"

# ==========================================
# 📢 改版公告設定區（改成 True 即開啟進站彈跳小視窗）
# ==========================================
SHOW_UPDATE_BANNER = True   # 頂部可摺疊通知條（不擋畫面，推薦常駐）
SHOW_UPDATE_POPUP = False   # 進站自動彈出小視窗（短期強提醒用，預設關閉）
UPDATE_TITLE = "📢 【v2.0 深度證據改版】跨陣營內文讀取・情緒詞高亮檢核・LINE 機器人上線"
UPDATE_NOTES = """
本次系統完成全面深度與透明化升級，讓每一項分析都看得到原始證據：

1. **📖 突破「只看標題」限制**：早中晚報現已自動跨陣營抓取代表性報導內文，看得到真實數據、法條與完整原話，並新增 **「同一事實兩邊怎麼切」** 與 **「標題 vs. 內文落差抓包」**。
2. **🧩 盲點加註媒體出處 ＋「缺失拼圖」卡片**：所有同溫層盲點皆標註實際報導出處，並獨立呈現藍綠雙方都未講明的事實基準線。
3. **🛡️ 可查證度四維度公開拆解**：將原本單一評分拆解為「具名來源、跨陣營共識、具體數據與文本、單一來源風險控管」四項各 25 分，評分依據公開可檢驗。
4. **🔴 標題情緒煽動詞透明高亮**：修正舊版單字誤判，並於第 4 分頁原始報導清單直接紅底高亮計分用詞，提供一鍵篩選檢驗。
5. **💬 LINE 隨手解盲機器人上線**：貼新聞網址或關鍵字 5 秒拆解盲點，支援免費拉進親友群組（平常靜默，點名才回應）。
"""

if SHOW_UPDATE_POPUP and hasattr(st, "dialog"):
    @st.dialog(UPDATE_TITLE)
    def show_changelog_dialog():
        st.markdown(UPDATE_NOTES)
        st.write("")
        if st.button("我知道了，開始閱讀", type="primary", use_container_width=True):
            st.session_state["seen_update_popup"] = True
            st.rerun()

    if not st.session_state.get("seen_update_popup", False):
        show_changelog_dialog()

st.markdown("""
<style>
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
#MainMenu { visibility: hidden !important; }
footer { visibility: hidden !important; }

/* LINE 隨手解盲導流橫幅 */
.line-promo-banner {
    background: linear-gradient(90deg, #064e3b 0%, #0f172a 100%);
    border: 1px solid #10b981;
    border-radius: 12px;
    padding: 14px 20px;
    margin: 8px 0 18px 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
}
.line-promo-title {
    color: #6ee7b7;
    font-weight: 800;
    font-size: 0.98rem;
}
.line-promo-desc {
    color: #cbd5e1;
    font-size: 0.86rem;
    margin-top: 4px;
    line-height: 1.5;
}
.line-promo-btn {
    background-color: #06c755;
    color: #ffffff !important;
    text-decoration: none !important;
    font-weight: 800;
    font-size: 0.9rem;
    padding: 10px 18px;
    border-radius: 8px;
    white-space: nowrap;
    display: inline-block;
}
.line-promo-btn:hover {
    background-color: #05b34c;
}

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
    padding: 4px 12px;
    border-radius: 99px;
    font-size: 0.85rem;
    font-weight: 600;
    line-height: 1.5;
}

/* 四大戰情指標獨立卡片 */
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

/* 3秒看懂爭點摘要框 */
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
    min-height: 120px;
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
.blind-card-puzzle {
    background: linear-gradient(135deg, #272011 0%, #1e293b 100%);
    border: 1px solid #b45309;
    border-left: 6px solid #f59e0b;
    padding: 18px 22px;
    border-radius: 12px;
    color: #fef3c7;
    line-height: 1.8;
    margin-top: 4px;
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
.cite-tag {
    display: inline-block;
    background-color: rgba(148, 163, 184, 0.22);
    color: #e2e8f0;
    font-size: 0.82rem;
    padding: 1px 7px;
    border-radius: 6px;
    margin-left: 4px;
    font-weight: 600;
}

/* 四維度可查證度拆解卡 */
.verify-card {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 12px;
    height: 100%;
}
.verify-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
}
.verify-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: #e2e8f0;
}
.verify-score {
    font-size: 0.92rem;
    font-weight: 800;
    color: #38bdf8;
}
.verify-bar-bg {
    background-color: #0f172a;
    height: 7px;
    border-radius: 99px;
    overflow: hidden;
    margin-bottom: 8px;
}
.verify-bar-fill {
    height: 100%;
    border-radius: 99px;
}
.verify-desc {
    font-size: 0.83rem;
    color: #cbd5e1;
    line-height: 1.55;
}

/* 原始報導清單與情緒詞高亮 */
.news-row {
    background-color: rgba(30, 41, 59, 0.55);
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 8px;
    line-height: 1.65;
    font-size: 0.94rem;
    color: #e2e8f0;
}
.news-row a {
    color: #93c5fd;
    text-decoration: none;
    font-weight: 600;
}
.news-row a:hover {
    text-decoration: underline;
    color: #bfdbfe;
}
.emo-hit {
    background-color: rgba(239, 68, 68, 0.28);
    color: #fecaca;
    padding: 1px 4px;
    border-radius: 4px;
    font-weight: 700;
}
.emo-badge {
    display: inline-block;
    background-color: rgba(239, 68, 68, 0.18);
    border: 1px solid rgba(248, 113, 113, 0.45);
    color: #fca5a5;
    font-size: 0.74rem;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 5px;
    margin-left: 6px;
    vertical-align: middle;
}
.first-badge {
    display: inline-block;
    background-color: rgba(234, 179, 8, 0.2);
    border: 1px solid rgba(250, 204, 21, 0.5);
    color: #fde047;
    font-size: 0.76rem;
    font-weight: 800;
    padding: 1px 7px;
    border-radius: 5px;
    margin-left: 6px;
    vertical-align: middle;
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

# 排除純轉載入口平台（確保前台歷史資料也即時過濾）
AGGREGATOR_BLACKLIST = [
    "LINE TODAY", "LINE新聞", "Yahoo", "MSN", "PChome",
    "蕃新聞", "Match生活網", "HiNet", "Hinet"
]

GREEN_KEYS = [
    "泛綠", "深綠", "偏綠", "自由", "三立", "民視",
    "新頭殼", "Newtalk", "太報", "鏡週刊", "鏡報", "放言", "民報"
]
BLUE_KEYS = [
    "泛藍", "深藍", "親中", "聯合", "UDN", "udn", "中時", "中國時報",
    "中天", "TVBS", "風傳媒", "中視", "中廣", "工商", "經濟日報", "梅花"
]
WHITE_KEYS = ["泛白", "民眾", "匯流", "CNEWS"]

# v2.0 精準政治情緒詞典（移除「救、驚、爆、轟、嗆」等高誤判單字，改用明確情緒詞組）
SENSATIONAL_WORDS = [
    "狠酸", "狂酸", "酸爆", "打臉", "洗臉", "翻車", "大翻車",
    "砲轟", "怒轟", "痛轟", "轟爆", "痛批", "怒批", "狠批", "重批",
    "怒嗆", "痛嗆", "狂嗆", "開嗆", "狠嗆", "反嗆", "嗆爆",
    "怒斥", "痛斥", "大罵", "怒罵", "痛罵", "開罵",
    "踢爆", "怒爆", "驚爆", "爆氣", "引爆口水", "驚傳內幕",
    "急了", "傻眼", "跳腳", "開戰", "開撕", "互槓", "吵成一團", "鬧翻",
    "強行", "硬闖", "闖關", "黑箱", "自肥", "掏空", "神隱", "打假球",
    "變調", "破局", "打槍", "切割", "倒戈", "護航", "硬拗", "甩鍋",
    "鬆一口氣", "炒不起來", "難發酵", "力拚", "力拼", "逼宮", "出征",
    "！", "!"
]

_SENSATIONAL_PATTERN = re.compile(
    "(" + "|".join(re.escape(w) for w in sorted(SENSATIONAL_WORDS, key=len, reverse=True)) + ")"
)
_SENSATIONAL_HTML_PATTERN = re.compile(
    "(" + "|".join(re.escape(html.escape(w)) for w in sorted(SENSATIONAL_WORDS, key=len, reverse=True)) + ")"
)


def is_aggregator(source_name):
    s_lower = (source_name or "").lower()
    return any(b.lower() in s_lower for b in AGGREGATOR_BLACKLIST)


def strip_media_suffix(title, source=""):
    """移除標題尾端重複的『 - 媒體名稱』，避免干擾閱讀與情緒詞偵測。"""
    t = (title or "").strip()
    if " - " in t:
        head, tail = t.rsplit(" - ", 1)
        tail_clean = tail.strip()
        if source and (source in tail_clean or tail_clean in source or len(tail_clean) <= 16):
            return head.strip()
    return t


def find_sensational_hits(title, source=""):
    clean = strip_media_suffix(title, source)
    return _SENSATIONAL_PATTERN.findall(clean)


def highlight_sensational_html(title, source=""):
    clean = strip_media_suffix(title, source)
    safe = html.escape(clean)
    hits = []

    def _repl(m):
        w = m.group(1)
        hits.append(w)
        return f'<mark class="emo-hit">{w}</mark>'

    highlighted = _SENSATIONAL_HTML_PATTERN.sub(_repl, safe)
    return highlighted, hits


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
    return "公媒／通訊社與商業綜合"


def calc_emotion_metric(sources):
    if not sources:
        return "0%", "🟢 平實陳述為主"
    hit_count = 0
    for s in sources:
        if find_sensational_hits(s.get("title", ""), s.get("source", "")):
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
        items = re.split(r"(?:\n\s*[\*\-•]\s*|\s+\*\s+)", raw_block)
        for item in items:
            line = item.strip().lstrip("*-• ").strip("*")
            if "：" in line or ":" in line:
                sep = "：" if "：" in line else ":"
                actor, quote = line.split(sep, 1)
                actor = actor.strip().strip("*[]【】")
                quote = quote.strip().strip("*")

                if any(empty_w in quote for empty_w in ["無相關報導", "無表態", "未表態", "無直接相關", "未提及"]):
                    continue

                prefix_match = re.match(r"^([🟦🟩⬜🏛️⚖️]+)", actor)
                badge = prefix_match.group(1) + " " if prefix_match else "🗣️ "
                cleaned_actor = re.sub(
                    r"^[🟦🟩⬜🏛️⚖️\s]*|當事人或|代表名稱|實際當事人[A-C]姓名|（陣營或職稱）",
                    "",
                    actor
                ).strip()

                if ("：" in quote or ":" in quote) and (not cleaned_actor or "/" in cleaned_actor or "／" in cleaned_actor):
                    q_sep = "：" if "：" in quote else ":"
                    sub_actor, sub_quote = quote.split(q_sep, 1)
                    if len(sub_actor.strip()) <= 12:
                        cleaned_actor = sub_actor.strip()
                        quote = sub_quote.strip()

                final_actor = f"{badge}{cleaned_actor}" if cleaned_actor else f"{badge}關鍵當事人表態"
                if quote:
                    stances.append((final_actor, quote))

    summary = parsed.get("summary", "")
    sentences = [s.strip() for s in re.split(r"[。；]", summary) if len(s.strip()) > 6]

    if len(stances) == 1 and len(sentences) >= 2:
        stances.append(("⚖️ 媒體解讀與事件背景", sentences[-1] + "。"))
        return stances

    if len(stances) >= 2:
        return stances[:4]

    actor_rules = [
        ("🟦 國民黨／藍營立場", ["國民黨", "藍營", "蔣萬安", "韓國瑜"]),
        ("🟩 行政院／綠營立場", ["行政院長", "卓榮泰", "行政院", "民進黨", "賴清德", "沈伯洋"]),
        ("⬜ 民眾黨／白營立場", ["民眾黨", "柯文哲", "黃國昌", "白營", "張天民"]),
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
    if not raw_text:
        return ""
    cleaned = re.sub(r"^這群讀者.*?(?:看不見|錯過)[：:\s]*", "", raw_text.strip())
    parts = re.split(r"(?:\n\s*[\*\-•]\s*|\s+\*\s+)", cleaned)
    parts = [p.strip().strip("*") for p in parts if len(p.strip().strip("*")) > 4]

    if len(parts) == 1 and "。" in parts[0]:
        sents = [s.strip() + "。" for s in parts[0].split("。") if len(s.strip()) > 6]
        if len(sents) > 1:
            parts = sents

    rendered = []
    for p in parts:
        safe_p = html.escape(p)
        # 將（見OO、XX報導）自動包成視覺化出處標籤
        safe_p = re.sub(
            r"([（(]見[^）)]+報導[）)])",
            r'<span class="cite-tag">\1</span>',
            safe_p
        )
        rendered.append(f'<div class="blind-item">• {safe_p}</div>')
    return "".join(rendered)


def parse_report_data(report_md):
    cleaned = re.sub(r"^好的，.*?\n+", "", report_md.strip())

    summary = ""
    sum_pattern = (
        r"【(?:中立客觀|多方對照)事實摘要】[：:\s\*]*(.+?)"
        r"(?=\s*\*{0,2}【議題主導陣營】|\s*\*{0,2}【當事人表態對照】|\n---|\n###|\n\n)"
    )
    sum_match = re.search(sum_pattern, cleaned, re.DOTALL)
    if sum_match:
        summary = sum_match.group(1).strip().strip("*")

    # 同時相容 v1.2「消息可靠度評分（0～100分）：85分」與 v2.0「消息可靠度評分：84分」
    score = 75
    score_pattern = r"可靠度評分(?:\s*[\(（][^\)）]*[\)）])?[\*\s]*[：:]\s*\*?(\d{1,3})\s*分"
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

    # 解析 v2.0 新增：各陣營都沒講的「缺失拼圖」
    missing_puzzle = ""
    mp_m = re.search(
        r"各陣營都沒講的「缺失拼圖」[^：:]*[：:\s\*]*(.+?)(?=\n-\s*\*\*🛡️|\n-\s*🛡️|\n###|\Z)",
        cleaned,
        re.DOTALL
    )
    if mp_m:
        missing_puzzle = mp_m.group(1).strip().strip("*")

    # 解析 v2.0 新增：四維度可查證度拆解（各 25 分）
    breakdown_defs = [
        ("🪪 具名來源", r"具名來源\s*[\(（](\d{1,2})\s*/\s*25分?[\)）][\*]*[：:]\s*([^\n]+)"),
        ("🤝 跨陣營共識", r"跨陣營共識\s*[\(（](\d{1,2})\s*/\s*25分?[\)）][\*]*[：:]\s*([^\n]+)"),
        ("📊 具體數據與文本", r"具體數據與文本\s*[\(（](\d{1,2})\s*/\s*25分?[\)）][\*]*[：:]\s*([^\n]+)"),
        ("🛡️ 單一來源風險控管", r"單一來源風險控管\s*[\(（](\d{1,2})\s*/\s*25分?[\)）][\*]*[：:]\s*([^\n]+)"),
    ]
    score_breakdown = []
    for title_lbl, pat in breakdown_defs:
        bm = re.search(pat, cleaned)
        if bm:
            pts = min(25, max(0, int(bm.group(1))))
            desc = bm.group(2).strip().strip("*")
            score_breakdown.append((title_lbl, pts, desc))

    return {
        "cleaned": cleaned,
        "summary": summary,
        "score": score,
        "sec1": sec1,
        "sec2": sec2,
        "sec3": sec3,
        "blue_blind": blue_blind,
        "green_blind": green_blind,
        "missing_puzzle": missing_puzzle,
        "score_breakdown": score_breakdown
    }


st.title("🔍 政治解盲")
st.caption("每日早（08:00）、中（12:30）、晚（19:00）自動鎖定全台最大政治議題，深度比對藍、綠、白與公媒／商業媒體報導，攤開同溫層盲區，還原多方對照的事實全貌。")

if SHOW_UPDATE_BANNER:
    with st.expander(f"{UPDATE_TITLE}（點擊展開查看）", expanded=False):
        st.markdown(UPDATE_NOTES)

# 頂部 LINE 隨手解盲導流橫幅
st.markdown(f"""
<div class="line-promo-banner">
    <div>
        <div class="line-promo-title">💬 新功能上線｜《政治解盲》LINE 隨手查核機器人（免費免註冊）</div>
        <div class="line-promo-desc">看到疑似帶風向的新聞？直接轉傳網址或輸入關鍵字，5 秒拆解藍綠白盲點；還可免費拉進親友群組（平常靜默不吵人）。</div>
    </div>
    <a href="{LINE_ADD_URL}" target="_blank" class="line-promo-btn">＋ 加入 LINE 免費解盲</a>
</div>
""", unsafe_allow_html=True)

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
            st.markdown(f"""
            <div style="background-color:#064e3b; border:1px solid #10b981; border-left:4px solid #06c755; padding:14px; border-radius:10px; margin-bottom:14px;">
                <div style="font-weight:700; color:#6ee7b7; font-size:0.95rem; margin-bottom:6px;">
                    💬 LINE 隨手解盲機器人
                </div>
                <div style="font-size:0.83rem; color:#e2e8f0; line-height:1.5; margin-bottom:10px;">
                    轉傳新聞網址或輸入關鍵字，5 秒攤開藍綠白盲點！支援拉進親友群組（點名才回話）。
                </div>
                <a href="{LINE_ADD_URL}" target="_blank" style="display:block; text-align:center; background-color:#06c755; color:#ffffff; font-weight:800; padding:9px 12px; border-radius:6px; text-decoration:none; font-size:0.88rem;">
                    ＋ 加入 LINE 官方帳號
                </a>
            </div>
            """, unsafe_allow_html=True)
            st.subheader("📊 儀表板閱讀指南")
            st.caption("• 資訊可查證度：公開拆解具名來源、跨陣營共識、數據文本與單一來源風險。")
            st.caption("• 情緒煽動度：統計標題含政治情緒詞比例，第 4 分頁直接紅底高亮供檢核。")
            st.caption("• 盲點與缺失拼圖：每點均附媒體出處，呈現資訊覆蓋差與雙邊略過的前提。")
            st.caption("• 分類透明公開：點擊第 5 分頁可查閱完整媒體歸類清單。")
            st.divider()
            st.markdown(f"""
            <div style="background-color:#1e293b; border:1px solid #334155; border-left:4px solid #eab308; padding:14px; border-radius:10px;">
                <div style="font-weight:700; color:#fde047; font-size:0.95rem; margin-bottom:6px;">
                    ☕ 支持《政治解盲》獨立運作
                </div>
                <div style="font-size:0.83rem; color:#cbd5e1; line-height:1.5; margin-bottom:10px;">
                    為拒絕政黨與財團介入，本站絕不刊登政治業配。歡迎小額贊助支持 AI 每日運算成本！
                </div>
                <a href="{DONATE_URL}" target="_blank" style="display:block; text-align:center; background-color:#eab308; color:#0f172a; font-weight:800; padding:9px 12px; border-radius:6px; text-decoration:none; font-size:0.88rem;">
                    💛 請 AI 喝杯咖啡（LINE Pay／刷卡）
                </a>
            </div>
            """, unsafe_allow_html=True)

        current = history[selected_idx]
        raw_sources = current.get("sources", [])
        filtered_sources = [s for s in raw_sources if not is_aggregator(s.get("source", ""))]
        sources = filtered_sources if filtered_sources else raw_sources
        excluded_count = len(raw_sources) - len(sources)
        fulltext_count = int(current.get("fulltext_count", 0) or 0)

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
        filter_note = f"・已排除 {excluded_count} 篇轉載入口" if excluded_count > 0 else "・僅計原生媒體"
        fulltext_note = f"・深度讀取 {fulltext_count} 篇跨陣營內文" if fulltext_count > 0 else ""
        st.markdown(f"""
        <div class="topic-banner">
            <div class="topic-label">🔥 本時段最大政治議題</div>
            <div class="topic-title">{html.escape(current["topic"])}</div>
            <span class="topic-meta">
                📅 {current["period"]}｜{current["date_str"]}（跨媒體比對 {len(sources)} 篇原生報導{fulltext_note}{filter_note}）
            </span>
        </div>
        """, unsafe_allow_html=True)

        # 第二排：四大戰情指標
        score = parsed["score"]
        if score >= 75:
            score_label = "🟢 高可查證度（具名與跨媒事實為主）"
        elif score >= 60:
            score_label = "🟡 中等（夾雜政黨推論與解讀）"
        else:
            score_label = "🔴 偏低（多匿名放話／單一來源）"

        emo_val, emo_label = calc_emotion_metric(sources)
        leader_val, leader_label = detect_agenda_leader(current, parsed, camp_counts)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-head">🛡️ 資訊可查證度</div>
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
                <div class="metric-val">{html.escape(first_source["source"])}</div>
                <div class="metric-sub">🕒 首發時間：{first_source["time_str"][-5:]}</div>
            </div>
            """, unsafe_allow_html=True)

        # 第三排：去情緒化多方事實摘要區
        if parsed["summary"]:
            st.markdown(f"""
            <div class="summary-box">
                <strong>⚖️ 【3秒看懂爭點】去情緒化多方事實摘要：</strong><br>
                {html.escape(parsed["summary"])}
            </div>
            """, unsafe_allow_html=True)

        # 第四排：當事人表態對照卡
        stances = extract_stances(current, parsed)
        if stances:
            st.markdown("##### 🗣️ 當事人與各方核心表態對照")
            s_cols = st.columns(len(stances))
            for idx, (actor, quote) in enumerate(stances):
                border_color = "#3b82f6"
                if any(w in actor for w in ["🟩", "綠", "政院", "民進黨", "沈伯洋", "卓榮泰", "賴清德"]):
                    border_color = "#22c55e"
                elif any(w in actor for w in ["⬜", "白", "柯", "民眾黨", "黃國昌", "張天民"]):
                    border_color = "#06b6d4"
                elif any(w in actor for w in ["🏛️", "⚖️", "機關", "院會", "動態", "背景", "財政部"]):
                    border_color = "#eab308"
                with s_cols[idx]:
                    st.markdown(f"""
                    <div class="stance-card" style="border-top-color: {border_color};">
                        <div class="stance-title">{html.escape(actor)}</div>
                        <div class="stance-body">{html.escape(quote)}</div>
                    </div>
                    """, unsafe_allow_html=True)

        st.write("")
        col_left, col_right = st.columns([1.35, 1])

        with col_left:
            st.subheader("🌈 媒體立場報導聲量光譜")
            total = max(len(sources), 1)

            n_blue = camp_counts["泛藍傾向"]
            n_white = camp_counts["泛白／第三勢力"]
            n_other = camp_counts["公媒／通訊社與商業綜合"]
            n_green = camp_counts["泛綠傾向"]

            p_blue = round(n_blue / total * 100)
            p_white = round(n_white / total * 100)
            p_other = round(n_other / total * 100)
            p_green = max(0, 100 - p_blue - p_white - p_other)

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
            if p_other > 0:
                segments.append(
                    f'<div class="spectrum-segment" style="width:{p_other}%;'
                    f'background:#64748b;">{seg_label("🟨 公媒/綜合", p_other)}</div>'
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
            m3.caption(f"🟨 **公媒／綜合**：{n_other} 篇 ({p_other}%)")
            m4.caption(f"🟩 **泛綠傾向**：{n_green} 篇 ({p_green}%)")

            if p_green >= p_blue * 2 and p_green > 30:
                st.warning("📢 聲量提示：本時段泛綠媒體報導密集度明顯較高。")
            elif p_blue >= p_green * 2 and p_blue > 30:
                st.warning("📢 聲量提示：本時段泛藍媒體報導密集度明顯較高。")
            else:
                st.success("⚖️ 聲量提示：本時段藍綠與公媒／商業媒體皆有高度關注，屬跨陣營交鋒議題。")

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

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🕳️ 同溫層盲點與缺失拼圖",
            "🧭 框架對照與標題黨抓包",
            "🕵️‍♂️ 源頭追蹤與可查證拆解",
            f"📰 原始報導與情緒詞檢核 ({len(sources)}篇)",
            "⚖️ 分類方法論與光譜公開"
        ])

        with tab1:
            st.markdown("#### 👁️ 只看單一陣營媒體，你會錯過什麼具體資訊？")
            if n_blue < 2 or n_green < 2:
                missing_side = "泛藍傾向" if n_blue < 2 else "泛綠傾向"
                st.warning(
                    f"⚠️ **單邊聲量提醒**：本時段【{missing_side}】原生報導不足 2 篇。"
                    "為避免偽均衡失真，系統僅呈現實際有媒體報導佐證之資訊覆蓋差，不硬湊對方立場。"
                )

            if parsed["blue_blind"] and parsed["green_blind"]:
                b_col, g_col = st.columns(2)
                with b_col:
                    b_items_html = format_blindspot_items(parsed["blue_blind"])
                    st.markdown(f"""
                    <div class="blind-card-blue">
                        <h4 style="margin:0 0 6px 0; color:#93c5fd;">🟦 只看【泛藍／泛白媒體】可能漏掉：</h4>
                        <div style="font-size:0.86rem; color:#cbd5e1; margin-bottom:10px;">
                            以下具體數據、法理說明或澄清，在藍白報導中較少被凸顯（附實際報導出處）：
                        </div>
                        {b_items_html}
                    </div>
                    """, unsafe_allow_html=True)
                with g_col:
                    g_items_html = format_blindspot_items(parsed["green_blind"])
                    st.markdown(f"""
                    <div class="blind-card-green">
                        <h4 style="margin:0 0 6px 0; color:#86efac;">🟩 只看【泛綠媒體】可能漏掉：</h4>
                        <div style="font-size:0.86rem; color:#cbd5e1; margin-bottom:10px;">
                            以下在野質疑、程序細節或反對聲浪，在綠營報導中較少被凸顯（附實際報導出處）：
                        </div>
                        {g_items_html}
                    </div>
                    """, unsafe_allow_html=True)
            elif parsed["sec2"]:
                st.markdown(parsed["sec2"])
            else:
                st.markdown(parsed["cleaned"])

            # v2.0 獨立呈現：兩邊都沒講的「缺失拼圖」
            if parsed["missing_puzzle"]:
                puzzle_html = format_blindspot_items(parsed["missing_puzzle"])
                st.markdown(f"""
                <div class="blind-card-puzzle">
                    <h4 style="margin:0 0 6px 0; color:#fcd34d;">🧩 各陣營都沒講的「缺失拼圖」（事實基準線）</h4>
                    <div style="font-size:0.86rem; color:#fde68a; margin-bottom:8px;">
                        當藍綠聚焦口水攻防時，雙方常共同略過以下關鍵前提或法規程序：
                    </div>
                    {puzzle_html}
                </div>
                """, unsafe_allow_html=True)

        with tab2:
            st.markdown("#### 🎭 各陣營敘事框架比較、同事件切入法與標題黨檢核")
            if parsed["sec1"]:
                st.markdown(parsed["sec1"])
            else:
                st.markdown(parsed["cleaned"])

        with tab3:
            st.markdown("#### 🔗 源頭追蹤與四維度資訊可查證度檢核")
            st.progress(
                parsed["score"] / 100,
                text=f"🛡️ 本議題資訊可查證度總分：{parsed['score']} / 100 分"
            )

            # v2.0 四維度拆解儀表板（各 25 分，舊期無資料時自動略過）
            if parsed["score_breakdown"]:
                v_cols = st.columns(len(parsed["score_breakdown"]))
                for idx, (v_title, v_pts, v_desc) in enumerate(parsed["score_breakdown"]):
                    pct = round(v_pts / 25 * 100)
                    bar_color = "#22c55e" if v_pts >= 20 else ("#f59e0b" if v_pts >= 14 else "#ef4444")
                    with v_cols[idx]:
                        st.markdown(f"""
                        <div class="verify-card">
                            <div class="verify-head">
                                <span class="verify-title">{v_title}</span>
                                <span class="verify-score">{v_pts} / 25</span>
                            </div>
                            <div class="verify-bar-bg">
                                <div class="verify-bar-fill" style="width:{pct}%; background-color:{bar_color};"></div>
                            </div>
                            <div class="verify-desc">{html.escape(v_desc)}</div>
                        </div>
                        """, unsafe_allow_html=True)
                st.write("")

            if parsed["sec3"]:
                st.markdown(parsed["sec3"])
            else:
                st.markdown(parsed["cleaned"])

        with tab4:
            st.markdown("#### 🔍 原始原生新聞清單（標題情緒詞透明高亮檢核）")
            st.caption("💡 紅底標記即為計入「標題情緒煽動度」之政治情緒用詞，讀者可直接核對原標題是否涉及標題殺人。")

            f_col1, f_col2 = st.columns([3, 1.3])
            with f_col1:
                filter_camp = st.radio(
                    "點選篩選特定媒體分類：",
                    [
                        "全部顯示",
                        "🟦 泛藍傾向",
                        "🟩 泛綠傾向",
                        "⬜ 泛白／第三勢力",
                        "🟨 公媒／通訊社與商業綜合"
                    ],
                    horizontal=True
                )
            with f_col2:
                only_emo = st.checkbox("🔴 僅顯示含情緒煽動詞之標題", value=False)

            camp_badge = {
                "泛藍傾向": "🟦 泛藍",
                "泛綠傾向": "🟩 泛綠",
                "泛白／第三勢力": "⬜ 泛白",
                "公媒／通訊社與商業綜合": "🟨 公媒/綜合"
            }

            shown_count = 0
            for idx, src in enumerate(sources, 1):
                c_type = classify_camp(src)
                if filter_camp != "全部顯示" and not filter_camp.endswith(c_type):
                    continue

                highlighted_title, emo_hits = highlight_sensational_html(
                    src.get("title", ""), src.get("source", "")
                )
                if only_emo and not emo_hits:
                    continue

                shown_count += 1
                badge = camp_badge.get(c_type, "🟨 公媒/綜合")
                safe_src = html.escape(src.get("source", "未知媒體"))
                safe_time = html.escape(src.get("time_str", "未知時間"))
                safe_link = html.escape(src.get("link", "#"), quote=True)
                emo_tag = '<span class="emo-badge">🎭 含情緒詞</span>' if emo_hits else ""
                first_tag = '<span class="first-badge">🏆 全網首發</span>' if idx == 1 else ""

                st.markdown(f"""
                <div class="news-row">
                    <code>#{idx:02d}</code> <strong>{safe_time}</strong> ｜ {badge}
                    <strong>[{safe_src}]</strong>
                    <a href="{safe_link}" target="_blank">{highlighted_title}</a>
                    {emo_tag}{first_tag}
                </div>
                """, unsafe_allow_html=True)

            if shown_count == 0:
                st.info("此篩選條件下無符合之原始報導。")

        with tab5:
            st.markdown("#### ⚖️ 媒體光譜分類方法論與透明聲明")
            st.info(
                "**透明聲明**：沒有任何單一媒體或 AI 模型是 100% 絕對中立的。"
                "《政治解盲》不替任何媒體背書「絕對中立」，本系統之分類僅依據各媒體長期社論立場、集團屬性與公開研究作為交叉比對基準；"
                "所有原始報導與情緒詞判定皆公開於「原始報導與情緒詞檢核」分頁，供讀者獨立查證。"
            )
            st.markdown("""
**1. 嚴格剔除純轉載入口網站**
- 系統在抓取新聞時，會自動排除 **`LINE TODAY`、`LINE新聞`、`Yahoo`、`MSN`、`PChome`、`蕃新聞`、`Match生活網`、`HiNet`** 等新聞聚合轉載平台。
- 目的在於避免特定陣營原生媒體（例如自由時報、中時、鏡報等）透過入口網站轉載後，被誤歸入綜合分類或造成聲量重複計算。

**2. 系統現行四大媒體觀測群組公開清單**

| 觀測分類 | 歸納判準 | 目前列入之代表媒體 |
| :--- | :--- | :--- |
| **🟦 泛藍傾向** | 長期社論偏向在野監督、兩岸溫和派或藍營／旺中／聯合報系媒體 | 聯合報、聯合新聞網（UDN）、經濟日報、中國時報、中時新聞網、工商時報、中天新聞、中視、TVBS、風傳媒、中廣新聞網、梅花新聞網 |
| **🟩 泛綠傾向** | 長期社論偏向本土執政立場、抗中主軸或自由／三立／民視／鏡系紙媒與網媒 | 自由時報、三立新聞、民視新聞、新頭殼（Newtalk）、太報、鏡週刊、鏡報、放言、民報 |
| **⬜ 泛白／第三勢力** | 民眾黨官方新媒體或高比例聚焦第三勢力與國會攻防之媒體 | 民眾之聲、匯流新聞網（CNEWS） |
| **🟨 公媒／通訊社與商業綜合** | 國家通訊社、公共媒體、獨立調查媒體或以商業流量／綜合即時為主之平台（※ 歸類於此不代表絕對無偏見，單篇報導仍依實際用詞納入分析） | 中央社（CNA）、公視新聞網（PTS）、中央廣播電臺、華視、台視、報導者、ETtoday、NOWnews、壹蘋新聞網、菱傳媒、上報、信傳媒、鏡新聞 |

**3. 資訊可查證度與雙層交叉判讀原則**
- **四維度可查證度（滿分 100 分）**：每期由「具名來源（25分）」、「跨陣營共識（25分）」、「具體數據與文本（25分）」、「單一來源風險控管（25分）」四項加總，公開說明給分依據。
- **預設光譜不等於單篇定罪**：即使媒體長期具特定傾向，若在該議題中僅平實陳述數據與官方說法，AI 分析報告會明確肯定其實際報導表現；反之，公媒或商業媒體若使用強烈情緒化標題，一樣會被計入「標題情緒煽動度」並於原始報導分頁高亮呈現。
- 本光譜字典與情緒詞典將隨台灣媒體生態變化與讀者回饋持續滾動修正。
            """)

        st.divider()
        st.markdown(f"""
        <div style="background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%); border:1px solid #334155; border-radius:12px; padding:20px 24px; text-align:center; margin-top:10px;">
            <div style="font-size:1.15rem; font-weight:800; color:#fde047; margin-bottom:6px;">
                🛡️ 守護獨立運作，拒絕政黨業配介入
            </div>
            <div style="font-size:0.92rem; color:#cbd5e1; margin-bottom:16px;">
                《政治解盲》由獨立系統全自動運作。歡迎免費加入 LINE 機器人隨手查核，或請 AI 喝杯咖啡支持每日運算！
            </div>
            <div style="display:flex; justify-content:center; flex-wrap:wrap; gap:12px;">
                <a href="{LINE_ADD_URL}" target="_blank" style="display:inline-block; background-color:#06c755; color:#ffffff; font-weight:800; padding:10px 24px; border-radius:8px; text-decoration:none; font-size:0.95rem;">
                    💬 加入 LINE 隨手解盲（免費）
                </a>
                <a href="{DONATE_URL}" target="_blank" style="display:inline-block; background-color:#eab308; color:#0f172a; font-weight:800; padding:10px 24px; border-radius:8px; text-decoration:none; font-size:0.95rem;">
                    ☕ 請 AI 喝杯咖啡（LINE Pay ／ 信用卡免註冊）
                </a>
            </div>
        </div>
        """, unsafe_allow_html=True)
