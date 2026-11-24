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
    m = re.search(r"【議題主導陣營】[：:\s\*]*(.+?)(?:\n|\*\*【|\$)", report_text)
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
    if n_green >= n_blue
