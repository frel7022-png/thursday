"""sector — 섹터별로 혼합지수 대비 움직임을 잰다 (써스데이, 2026-10-21, 테스팅 버전).

    python C:/Users/frel/Desktop/Thursday/tools/sector.py [--base YYYY-MM-DD] [--save]

대표(2026-10-21): "섹터 트래킹 기능을 만들면 될 거 같은데? 섹터별 시장 대비 움직임을 감지하는.
섹터 안 모든 종목 평균 %여야지 시총이면 안 돼. 그럼 시총 큰 놈 하나가 영향을 미칠 수 있으니. 이게 혼합지수 대비 출렁임(변화)겠지?"

입력: data/daily_long.csv(수정주가 일봉, 마지막 행이 오늘이면 장중값), new1/stock_sector_cache.csv(섹터),
      new1 live_check·portfolio_core의 혼합지수(삼성·하이닉스 제외, KOSPI·KOSDAQ 가중 — 계좌 성적과 같은 정의).
계산
- 섹터 n일 % = 섹터 안 종목들의 n일 수익률 **단순 평균**(동일가중, 시총 가중 아님). n = 1·5·20 거래일, 기준 = --base(기본 2026-08-19) 이후.
- 차이{n}%p = 섹터 n일 % − 같은 n일 혼합지수 %.
- 출렁임z1·z5 = 하루 차이(섹터 하루 평균 − 혼합 하루)의 그 섹터 평소(중앙값 기반 σ, 혼합지수가 있는 날 전부) 대비 배수. 1일은 그대로, 5일은 σ×√5로 나눈다.
- 폭1·폭5 = 섹터 안에서 같은 기간 혼합지수보다 나은 종목 비율(한두 종목이 평균을 끌었는지 본다).
- 감지 = |z1| ≥ 2 또는 |z5| ≥ 2. 판정은 하지 않는다. 숫자만 낸다.
- 섹터 종목이 3개 미만이면 평균이 한 종목이라 '얇음'으로 표시한다. '기타'는 모아 둔 칸이라 같은 무리로 읽지 않는다.
--save: data/sector_track.csv에 그날 줄을 덧붙인다(같은 날짜가 있으면 바꿔 씀). 나중에 그날 본 값으로 채점하려고.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from new1_locator import find_new1  # noqa: E402

NEW1 = find_new1()
sys.path.insert(0, str(NEW1))
BASE = "2026-08-19"
NS = (1, 5, 20)


def mixed_daily():
    import live_check
    import portfolio_core as core
    s = live_check.live_snapshot()
    ex = core.synthetic_kospi_ex_bigcap(s["idx"], s["bigdf"])
    ex["날짜"] = pd.to_datetime(ex["날짜"])
    ex = ex.set_index("날짜").sort_index()
    wk = float(s["wk"])
    lvl = wk * ex["KOSPI"] / ex["KOSPI"].iloc[0] + (1 - wk) * ex["KOSDAQ"] / ex["KOSDAQ"].iloc[0]
    return lvl, s["basis"]


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = sys.argv[1:]
    base = pd.Timestamp(args[args.index("--base") + 1] if "--base" in args else BASE)
    d = pd.read_csv(HERE / "data" / "daily_long.csv", encoding="utf-8-sig", dtype={"종목코드": str}, low_memory=False)
    d["날짜"] = pd.to_datetime(d["날짜"])
    d = d[d["거래량"] > 0]
    close = d.pivot(index="날짜", columns="종목명", values="종가").sort_index()
    sec = pd.read_csv(NEW1 / "stock_sector_cache.csv", encoding="utf-8-sig")
    sector = dict(zip(sec["종목명"], sec["섹터"]))
    lvl, basis = mixed_daily()
    days = close.index.intersection(lvl.index)
    close, lvl = close.loc[days], lvl.loc[days]
    ret1 = close.pct_change(fill_method=None)
    m1 = lvl.pct_change()
    today = days[-1]
    i0 = days[days >= base]
    wins = {f"{n}": len(days) - 1 - n for n in NS}
    if len(i0):
        wins["기준"] = days.get_loc(i0[0]) - 1
    groups = {}
    for name in close.columns:
        groups.setdefault(sector.get(name, "(없음)"), []).append(name)

    rows = []
    for s_name, mem in sorted(groups.items(), key=lambda t: -len(t[1])):
        row = {"날짜": today.strftime("%Y-%m-%d"), "섹터": s_name, "종목수": len(mem),
               "표시": "기타칸" if s_name.startswith("기타") else ("얇음" if len(mem) < 3 else "")}
        for w, k in wins.items():
            if k < 0:
                continue
            rw = close[mem].iloc[-1] / close[mem].iloc[k] - 1
            mw = float(lvl.iloc[-1] / lvl.iloc[k] - 1)
            row[f"섹터{w}%"] = round(float(rw.mean()) * 100, 2)
            row[f"혼합{w}%"] = round(mw * 100, 2)
            row[f"차이{w}%p"] = round((float(rw.mean()) - mw) * 100, 2)
            if w in ("1", "5"):
                row[f"폭{w}"] = round(float((rw.dropna() > mw).mean()), 2)
        ex1 = (ret1[mem].mean(axis=1) - m1).dropna()
        sd = float((ex1 - ex1.median()).abs().median() * 1.4826)
        row["평소σ%p"] = round(sd * 100, 2)
        if sd > 0:
            row["출렁임z1"] = round(float(ex1.iloc[-1]) / sd, 2)
            row["출렁임z5"] = round(float(ex1.tail(5).sum()) / (sd * math.sqrt(5)), 2)
        row["감지"] = "감지" if max(abs(row.get("출렁임z1", 0)), abs(row.get("출렁임z5", 0))) >= 2 else ""
        row["종목"] = "·".join(mem)
        rows.append(row)

    df = pd.DataFrame(rows)
    print(f"# sector · {today:%Y-%m-%d} ({basis}) · 섹터 {len(df)}개 · 동일가중 평균 vs 혼합지수(삼성·하이닉스 제외)"
          f" · 혼합지수 자료 {days[0]:%Y-%m-%d}~ · 기준일 {base:%Y-%m-%d}")
    show = [c for c in ["섹터", "종목수", "표시", "섹터1%", "차이1%p", "폭1", "차이5%p", "폭5", "차이20%p", "차이기준%p",
                        "평소σ%p", "출렁임z1", "출렁임z5", "감지"] if c in df]
    print(df[show].to_string(index=False))
    if "--save" in args:
        p = HERE / "data" / "sector_track.csv"
        old = pd.read_csv(p, encoding="utf-8-sig") if p.exists() else pd.DataFrame()
        if not old.empty:
            old = old[old["날짜"] != df["날짜"].iloc[0]]
        pd.concat([old, df], ignore_index=True).to_csv(p, index=False, encoding="utf-8-sig")
        print(f"# 저장: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
