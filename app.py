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
[data-testid="stMetricValue"] > div {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: unset !important;
    line-height: 1.3 !important;
}
.summary-box {
    background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
    border-left: 6px solid #2563eb;
    padding: 18px 22px;
    border-radius: 10px;
    font-size: 1.05rem;
    line-height: 1.7;
    color: #1e293b;
    margin-top: 10px;
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

GREEN_KEYS = [
    "泛綠", "深綠", "偏綠", "自由", "三立", "民視",
    "新頭殼", "Newtalk", "太報", "鏡週刊", "放言"
]
BLUE_KEYS = [
    "泛藍", "深藍", "親中", "聯合", "UDN", "udn", "中時", "中國時報",
    "中天", "TVBS", "風傳媒", "中視", "中廣", "工商", "經濟日報"
]
WHITE_KEYS = ["泛白", "民眾", "匯流", "CNEWS"]


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


def parse_report_data(report_md):
    cleaned = re.sub(r"^好的，.*?\n+", "", report_md.strip())

    summary = ""
    sum_pattern = r"【中立客觀事實摘要】[：:\s\*]*(.+?)(?=\n---|\n###|\n\n)"
    sum_match = re.search(sum_pattern, cleaned, re.DOTALL)
    if sum_match:
        summary =
