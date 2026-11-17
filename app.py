import streamlit as st
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta

st.set_page_config(
    page_title="台灣政治新聞風向與溯源觀測站",
    page_icon="📡",
    layout="wide"
)

st.markdown("""
<style>
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
    "泛藍", "深藍", "親中", "聯合", "UDN", "中時", "中國時報",
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
        summary = sum_match.group(1).strip().strip("*")

    score = 75
    score_pattern = r"可靠度評分(?:\s*[\(（].*?[\)）])?[：:\s\*]*(\d{1,3})\s*分"
    score_match = re.search(score_pattern, cleaned)
    if score_match:
        score = min(100, max(0, int(score_match.group(1))))

    sec1, sec2, sec3 = "", "", ""
    s1_m = re.search(r"###\s*1\..*?\n(.*?)(?=###\s*2\.|\Z)", cleaned
