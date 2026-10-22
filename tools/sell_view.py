"""매도 판단표 — 보유 종목마다 "산 이유가 어디까지 왔나 + 일봉이 지금 뭐라 하나 + 계좌 안 크기".

대표(2026-10-22): "대표가 팔았을 자리가 기준이 돼서 매도 시기를 정하면 안 돼. 너가 매도하는 시기를 알아서 정해야 해.
예로) 종목별로 일별 그래프를 분석한다든지. … 이 종목을 고른 근거가 뭐였는데, 그런 관점으로 오늘자 그래프를 보니 아직 팔 데가 아니다.
또는 이 종목은 전체 원금 비중의 ~%를 넣었는데 다른 종목들에 비해 수익률이 좋다. 여기서 분할매도에 들어간다."
→ 내_기준.md §7. 숫자는 문턱이 아니라 눈금이다. 모든 폭은 그 종목 평소 출렁임(일σ, 60일 중앙값 기반 — profile.py와 같음)으로 잰다.

사용: python tools/sell_view.py [--base 2026-08-19]

열
- 일σ%       : 평소 하루 출렁임
- 기준→저점% : 기준일(08-19 직전 종가, Fishing 누적 기준) 이후 가장 깊었던 곳까지
- 되찾은몫   : (지금 − 저점) ÷ (기준가 − 저점). 산 이유가 "많이 빠진 자리"였다면 이게 그 이유가 얼마나 소진됐는지다
- 저점후일   : 저점 이후 거래일 수
- 반등z      : 저점 대비 반등 ÷ (일σ × √저점후일). 평소 걸음으로 갈 거리 대비 몇 배 왔나
- 최대하루몫 : 저점 이후 오른 날들(로그 합) 중 제일 큰 하루가 차지하는 몫. 크면 하루 사건 위에 서 있다([[평균의 함정]]의 오르는 쪽)
- 반납/σ     : 저점 이후 고점에서 지금까지 밀린 폭 ÷ 일σ. 오름이 꺾였나
- 거래량비   : 반등 구간 하루 평균 거래량 ÷ 하락 구간(기준→저점) 평균. 1 아래면 받치는 손 없이 오르는 중
- 투자비중% : 이 종목 평가금액 ÷ 보유 종목 평가금액 합(굴리는 돈 안에서의 무게). 쏠림·매도 판단은 이걸로 본다(대표 2026-10-22: "1억 중 1,700만원 남짓을 썼어. 계좌자산을 기준으로")
- 총자산%    : 총자산 대비 비중(성적은 여전히 총자산 %)
- 손익률%·기여% : 평단 대비, 이 종목 평가손익 ÷ 보유 평가이익(+쪽) 합
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "tools"))
import agent_view as av  # noqa: E402

BASE = "2026-08-19"
SD_WIN = 60


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = sys.argv[1:]
    base = pd.Timestamp(args[args.index("--base") + 1] if "--base" in args else BASE)
    b = av.Book(HERE / "ledger" / "transactions.csv")
    b.header()
    d = pd.read_csv(HERE / "data" / "daily_long.csv", dtype={"종목코드": str}, encoding="utf-8-sig")
    d = d[d["거래량"] > 0].copy()
    d["날짜"] = pd.to_datetime(d["날짜"])
    today = pd.Timestamp(str(b.today))
    _last = d["날짜"].max().date()
    av._out(f"일봉 마지막일 {_last} · 오늘({b.today}) 값은 실시간 현재가로 붙임(장중이면 미완성 봉) · 기준일 {base.date()} 직전 종가")

    pos_sum = float(b.h.loc[b.h["손익"] > 0, "손익"].sum()) or 1.0
    cols = ["종목", "매수", "녹색", "일σ%", "기준→저점%", "되찾은몫", "저점후일", "반등z", "최대하루몫", "반납/σ", "거래량비",
            "투자비중%", "총자산%", "손익률%", "기여%"]
    av._out(" | ".join(cols))
    rows = []
    for _, r in b.h.iterrows():
        g = d[d["종목코드"] == r["종목코드"]].sort_values("날짜").set_index("날짜")
        if g.empty:
            continue
        px, vol = g["종가"].astype(float), g["거래량"].astype(float)
        if today not in px.index and r["현재가"] > 0:
            px.loc[today] = float(r["현재가"])
            vol.loc[today] = np.nan
        ret = px.pct_change().dropna()
        rt = ret.tail(SD_WIN)
        sd = float((rt - rt.median()).abs().median() * 1.4826) or float(rt.std())
        before = px[px.index < base]
        if before.empty:
            continue
        b0 = float(before.iloc[-1])
        seg = px[px.index >= base]
        lo_day = seg.idxmin()
        lo = float(seg.min())
        now = float(px.iloc[-1])
        after = px[px.index > lo_day]
        n = len(after)
        back = (now - lo) / (b0 - lo) if b0 > lo else np.nan
        reb = math.log(now / lo)
        rz = reb / (sd * math.sqrt(n)) if n else np.nan
        lr = np.log(after / after.shift(1).fillna(lo))
        up = float(lr[lr > 0].sum())
        maxday = float(lr.max() / up) if n and up > 0 else np.nan  # 오른 날들 합 중 하루 몫(지그재그면 순반등이 작아 순반등 대비는 부풀어서)
        hi = float(after.max()) if n else lo
        giveback = (hi - now) / hi / sd if n else 0.0
        v_down = vol[(vol.index >= base) & (vol.index <= lo_day)].mean()
        v_up = vol[vol.index > lo_day].mean()
        vr = float(v_up / v_down) if n and v_down else np.nan
        bu = b.trade_points(r["종목명"])
        first = float(bu.iloc[0]["단가"]) if not bu.empty else np.nan
        green = "녹색" if len(bu) >= 2 and r["현재가"] >= first else "-"
        rows.append([r["종목명"], len(bu), green, sd * 100, (lo / b0 - 1) * 100, back, n, rz, maxday, giveback, vr,
                     r["평가금액"] / b.stock_val * 100, r["평가금액"] / b.total * 100, r["손익률"], max(r["손익"], 0) / pos_sum * 100])
    rows.sort(key=lambda x: -x[11])

    def f(v, fmt):
        return "-" if v is None or (isinstance(v, float) and np.isnan(v)) else format(v, fmt)
    for x in rows:
        av._out(" | ".join([x[0], str(x[1]), x[2], f(x[3], ".1f"), f(x[4], "+.1f"), f(x[5], ".2f"), str(x[6]), f(x[7], ".2f"),
                            f(x[8], ".2f"), f(x[9], ".2f"), f(x[10], ".2f"), f(x[11], ".1f"), f(x[12], ".2f"), f(x[13], "+.2f"), f(x[14], ".0f")]))
    cost = float((b.h["수량"] * b.h["평단가"]).sum())
    pnl = float(b.h["손익"].sum())
    av._out(f"보유 평가금액 {b.stock_val:,.0f}원(총자산의 {b.stock_val / b.total * 100:.1f}%) · 매입 {cost:,.0f}원 · 평가손익 {pnl:+,.0f}원"
            f"(투자금 대비 {pnl / cost * 100:+.2f}%, 총자산 대비 {pnl / b.total * 100:+.2f}%) · 평가이익(+쪽) 합 {pos_sum:,.0f}원")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
