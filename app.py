"""써스데이 모니터링 앱 — 대표가 써스데이 계좌를 지켜보는 화면 (2026-10-15 새러데이 작성).

구성(1712·1718 합의): 타이틀(총자산·원금 대비·어제 대비·예수금·총계좌 — 2026-10-22 대표) + Today's Take + Holdings.
분석 탭(Fishing·Link·Basecamp·Foreigner·DC/UC 등)은 넣지 않는다 — 분석은 새러데이 리포트 몫.
계산은 tools/agent_view.py와 같은 함수(new1 portfolio_core를 import). 장부는 이 레포의 ledger/를 읽는다.

로컬: streamlit run app.py
"""
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
import agent_view as av  # noqa: E402  (new1 위치 찾기·import까지 여기서 끝남)

LEDGER = Path(os.environ.get("THURSDAY_LEDGER") or Path(__file__).resolve().parent / "ledger" / "transactions.csv")
UP, DN, MUTED = "#c9313d", "#2c5fc4", "#8b909c"

st.set_page_config(page_title="Thursday", layout="centered")
st.markdown("""
<style>
:root { --card:#ffffff; --ink:#191b21; --soft:#5b606b; --rule:#e3e6ec; --green:#e9f6ee; }
.block-container { padding-top: 3rem; max-width: 760px; }
.tw-title { font-size: 1.5rem; font-weight: 700; margin: 0; }
.tw-sub { font-size: 12px; color: var(--soft); margin: 2px 0 12px; }
.tw-box { background: var(--card); border: 1px solid var(--rule); border-radius: 12px; padding: 14px 16px; margin-bottom: 12px; }
.tw-label { font-size: 12px; color: var(--soft); }
.tw-main { font-size: 1.6rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.tw-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px 12px; margin-top: 10px; }
.tw-grid div { font-size: 12px; color: var(--soft); }
.tw-grid b { display: block; font-size: 14px; color: var(--ink); font-variant-numeric: tabular-nums; }
.tw-take div { font-size: 13.5px; margin: 2px 0; }
.tw-card { background: var(--card); border: 1px solid var(--rule); border-radius: 10px; padding: 10px 12px; margin-bottom: 8px; }
.tw-card.green { background: var(--green); }
.tw-card .nm { font-weight: 700; font-size: 14px; }
.tw-card .sec { font-size: 11px; color: var(--soft); margin-left: 6px; }
.tw-card .row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 4px 10px; margin-top: 6px; }
.tw-card .row div { font-size: 11.5px; color: var(--soft); }
.tw-card .row b { display: block; font-size: 13px; color: var(--ink); font-variant-numeric: tabular-nums; }
@media (max-width: 520px) { .tw-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .tw-card .row { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
""", unsafe_allow_html=True)


def color(v):
    if v is None or v != v:
        return MUTED
    return UP if v > 0 else (DN if v < 0 else MUTED)


def signed(v, unit="%", d=2, won=False):
    if v is None or v != v:
        return "-"
    return f"{v:+,.0f}원" if won else f"{v:+.{d}f}{unit}"


@st.cache_data(ttl=60, show_spinner=False)
def load(ledger_mtime: float, code_mtime: float):  # code_mtime: 계산 코드가 바뀌면 캐시된 옛 결과(새 키 없음)를 버린다
    b = av.Book(LEDGER)
    take = av.take_numbers(b)
    rows = []
    for _, r in b.h.iterrows():
        bu = b.trade_points(r["종목명"])
        first = float(bu.iloc[0]["단가"]) if not bu.empty else None
        rows.append({**{k: r[k] for k in ("종목명", "섹터", "수량", "평단가", "현재가", "등락률", "손익률", "손익", "평가금액")},
                     "최초진입가": first, "매수횟수": len(bu),
                     "녹색": bool(len(bu) >= 2 and first and r["현재가"] >= first)})
    last = b.tx["날짜"].max() if not b.tx.empty else None
    return take, pd.DataFrame(rows), b.now.strftime("%Y-%m-%d %H:%M"), last


st.markdown('<p class="tw-title">Thursday</p>', unsafe_allow_html=True)
top_l, top_r = st.columns([4, 1], vertical_alignment="center")
with top_r:
    if st.button("새로고침", use_container_width=True):
        load.clear()
_code = Path(av.__file__).stat().st_mtime + Path(__file__).stat().st_mtime
take, hold, asof, last = load(LEDGER.stat().st_mtime if LEDGER.exists() else 0.0, _code)
with top_l:
    st.markdown(f'<p class="tw-sub">{asof} {take.get("basis", "")} · 장부 마지막 거래 {last or "없음"} · 원금 {take["initial"]:,.0f}원</p>',
                unsafe_allow_html=True)

# ---- 타이틀 박스
gain = take["total"] - take["initial"]
st.markdown(
    f'<div class="tw-box"><div class="tw-label">총자산</div>'
    f'<div class="tw-main">{take["total"]:,.0f}원</div>'
    f'<div class="tw-grid">'
    f'<div>원금 대비<b style="color:{color(gain)}">{signed(gain, won=True)} ({signed(gain / take["initial"] * 100)})</b></div>'
    f'<div>어제 대비(총자산·총계좌)<b style="color:{color(take["day_won"])}">{signed(take["day_won"], won=True)} '
    f'({signed(take["day_pct"])} · {signed(take.get("acct_day_pct"))})</b></div>'
    f'<div>예수금<b>{take["cash"]:,.0f}원 ({take["cash"] / take["total"] * 100:.1f}%)</b></div>'
    f'<div>총평가<b>{take["stock_val"]:,.0f}원</b></div>'
    + (f'<div>총계좌(매입 {take["acct_cost"]:,.0f}원)<b style="color:{color(take.get("acct_pct"))}">'
       f'{signed(take["stock_val"] - take["acct_cost"], won=True)} ({signed(take.get("acct_pct"))})</b></div>'
       if take.get("acct_cost") else "") +
    f'<div>{(take["today"][5:] + " ") if take.get("closed") else "오늘 "}실현손익<b style="color:{color(take["realized_today"])}">{signed(take["realized_today"], won=True)}</b></div>'
    f'<div>보유<b>{take["n"]}종목</b></div>'
    f'</div></div>', unsafe_allow_html=True)

# ---- Today's Take
ex_day, my_day = take.get("ex_day"), take.get("stock_day")
gap = (my_day - ex_day) if (my_day is not None and ex_day is not None) else None
acct_day = take.get("acct_day_pct")
gap2 = (acct_day - ex_day) if (acct_day is not None and ex_day is not None) else None
cum_line = ""
if take.get("start") and take.get("bench_cum") is not None:
    acct_cum = gain / take["initial"] * 100
    cum_line = (f'<div>시작일({take["start"]}) 이후 누적 · 써스데이 <b style="color:{color(acct_cum)}">{signed(acct_cum)}</b>'
                f' · 혼합지수 <b style="color:{color(take["bench_cum"])}">{signed(take["bench_cum"])}</b></div>')
# 당일: 오늘 산 것은 체결가→지금, 전일 산 것은 오늘 하루(어제 종가→지금)를 혼합지수 당일과 같은 눈금으로 댄다(대표 10-22)
day_line = (f'<div>당일 · 총계좌(실제 체결가 반영) <b style="color:{color(acct_day)}">{signed(acct_day)}</b>'
            f' · 혼합지수 <b style="color:{color(ex_day)}">{signed(ex_day)}</b>'
            f' · 대비 <b style="color:{color(gap2)}">{signed(gap2, unit="%p")}</b></div>')
for key, lab in (("buys_today", "오늘 산 것"), ("buys_prev", "전일 산 것")):
    g = take.get(key)
    if not g:
        continue
    rel = (g["today"] - ex_day) if (g["today"] is not None and ex_day is not None) else None
    day_line += (f'<div style="padding-left:10px">{lab}({g["day"][5:]}, {g["n"]}건 {g["cost"]:,.0f}원) · 체결가 대비 '
                 f'<b style="color:{color(g["since_buy"])}">{signed(g["since_buy"])}</b>'
                 f' · 오늘 하루 <b style="color:{color(g["today"])}">{signed(g["today"])}</b>'
                 f' · 혼합지수 대비 <b style="color:{color(rel)}">{signed(rel, unit="%p")}</b></div>')
st.markdown(
    f'<div class="tw-box tw-take"><div class="tw-label" style="font-weight:600;color:#191b21">Today\'s Take</div>'
    f'<div>{("[" + take["basis"] + "] ") if take.get("closed") else ""}혼합지수(삼성·하이닉스 제외) <b style="color:{color(ex_day)}">{signed(ex_day)}</b></div>'
    f'<div>내 지수(지금 보유를 어제 종가부터 들었다면) <b style="color:{color(my_day)}">{signed(my_day)}</b>'
    f' · 혼합지수 대비 <b style="color:{color(gap)}">{signed(gap, unit="%p")}</b></div>'
    f'{cum_line}{day_line}</div>',
    unsafe_allow_html=True)

# ---- Holdings
st.markdown(f'<div class="tw-label" style="font-weight:600;color:#191b21;margin:6px 0">Holdings ({len(hold)})</div>',
            unsafe_allow_html=True)
if hold.empty:
    st.markdown('<div class="tw-card">아직 보유 종목이 없어. 써스데이가 첫 매수를 하면 여기 나와.</div>', unsafe_allow_html=True)
else:
    for _, r in hold.sort_values("평가금액", ascending=False).iterrows():
        cls = "tw-card green" if r["녹색"] else "tw-card"
        w = r["평가금액"] / take["total"] * 100
        wa = r["평가금액"] / take["stock_val"] * 100 if take["stock_val"] else 0.0  # 총계좌 안 무게(대표 2026-10-22)
        st.markdown(
            f'<div class="{cls}"><span class="nm">{r["종목명"]}</span><span class="sec">{r["섹터"]} · {r["매수횟수"]}회 매수</span>'
            f'<div class="row">'
            f'<div>현재가<b>{r["현재가"]:,.0f} <span style="color:{color(r["등락률"])};font-size:11px">{signed(r["등락률"])}</span></b></div>'
            f'<div>평단<b>{r["평단가"]:,.0f}</b></div>'
            f'<div>손익<b style="color:{color(r["손익"])}">{signed(r["손익률"])} ({signed(r["손익"], won=True)})</b></div>'
            f'<div>수량·비중(총자산·총계좌)<b>{r["수량"]:g}주 · {w:.2f}% · {wa:.1f}%</b></div>'
            f'</div></div>', unsafe_allow_html=True)
