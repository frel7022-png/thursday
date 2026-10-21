"""profile — 관심종목마다 '자기 성격'을 재고, 지금 움직임을 그 종목 평소 대비로 본다 (써스데이, 2026-10-19).

    python C:/Users/frel/Desktop/Thursday/tools/profile.py [--out 경로.csv]

대표(2026-10-19): "5%·10% 수치에 목매지 말고. 일일 하락폭은 1%라도 주 5%, 월 10%일 수 있다.
다지는 구간도 기간에 따라 다르다. '이 종목은 변동폭이 크네, 회전이 빠르네'를 알아낼 수 있을 거야."

입력: data/daily_long.csv(새러데이, 2년 수정주가 일봉 + 외국인소진율), data/shares.csv(발행주식수·유동비율),
      new1/stock_sector_cache.csv(대표 섹터). 거래량 0 행(거래정지일)은 뺀다. 마지막 행이 오늘 장중이면 그 값이 '지금'이다.

출력 열(종목마다 한 줄)
- 성격: 일σ%(최근 60일 하루 수익률, 중앙값 기반) · 일σ250%(같은 방식 250일, 국면 오염 비교용) · 회전%(최근 60일 거래량 중간값 ÷ 유동주식수) · 베타(유니버스 동일가중 대비)
        · 표본일수
- 지금, 여러 기간(n = 1·5·20·60·120거래일):
  · r{n}%      : n일 수익률
  · z{n}       : r{n} ÷ (일σ × √n). 그 종목 평소 변동 대비 몇 배 움직였나
  · 분위{n}    : 자기 2년 n일 수익률 분포에서 지금의 위치(0 = 2년 중 가장 많이 빠진 n일). 국면이 섞여 있어 비교용
  · 초과분위{n}: 유니버스 평균을 뺀 n일 수익률의 자기 2년 분위. 시장 국면을 덜어 낸 값
  · 초과{n}%p  : r{n} − 같은 n일 유니버스 평균. 섹터{n}%p: r{n} − 같은 섹터 평균
- 과거 비슷한 자리: 자기 20일 수익률이 하위 10%였던 날들 뒤 20거래일 수익률 중간값(후20%)과 그날 수(후20n),
                   같은 종목 아무 날 뒤 20거래일 중간값(평소20%). 이 종목이 많이 빠진 뒤 대체로 어땠나
- 평지(창 10·20·40일): 밴드%(창 안 고−저 ÷ 평균) ÷ 일σ로 정규화한 값(평탄{w}, 작을수록 평평),
                       거래량배{w}(창 거래량 중간값 ÷ 창 직전 60일 중간값), 거래량2배일10(최근 10일 중 직전 60일 중간값 2배 이상인 날 수)
- 외인: f{n}%p = n일 외국인소진율 변화, fz{n} = 그 변화 ÷ (외인 하루 변화 σ × √n)
- 세 층 나누기(창 = 기준일 이후 '기준', 20일): 수익률 = 시장몫 + 섹터몫 + 자기몫 (2026-10-21, 대표와 유니버스 약점 이야기에서)
  · 시장몫{w}%p = 베타120 × 유니버스 '중앙값' 수익률(평균은 한 섹터·몇 종목에 끌려간다)
  · 섹터몫{w}%p = 비교군 종목들의 (수익률 − 자기 베타 × 중앙값)의 중앙값. 자기 자신은 뺀다
  · 자기몫{w}%p = 나머지. 비교군 = 같은 섹터(자기 빼고 3개 이상, '기타' 칸 제외, 시장 뺀 평균 상관 0.2 이상)일 때 그 섹터, 아니면 최근 60일 시장 뺀 하루 수익률이 가장 닮은 10종목(닮은꼴)
  · 베타120 = 최근 120거래일 유니버스 동일가중 대비(250일 베타는 국면 오염 비교용으로 그대로 둔다)
판정은 하지 않는다. 숫자만 낸다. 거르고 판단하는 건 써스데이 몫(내_기준.md).
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
NS = (1, 5, 20, 60, 120)
WS = (10, 20, 40)
BASE = "2026-08-19"  # 세 층 나누기의 긴 창 시작일(Fishing 누적 기준일). --base 로 바꾼다
CORR_MIN = 0.2  # 이름표 섹터를 비교군으로 쓰는 최소 평균 상관(시장 뺀 60일). 이보다 낮으면 닮은꼴 10종목
SD_WIN = 60  # '평소'를 재는 창(거래일). 국면이 바뀐 구간을 섞지 않으려고 최근만 쓴다(기억/셀/국면_오염.md)


def load():
    d = pd.read_csv(HERE / "data" / "daily_long.csv", dtype={"종목코드": str}, encoding="utf-8-sig")
    d = d[d["거래량"] > 0].copy()
    d["날짜"] = pd.to_datetime(d["날짜"])
    d = d.sort_values(["종목코드", "날짜"])
    sh = pd.read_csv(HERE / "data" / "shares.csv", dtype={"종목코드": str}, encoding="utf-8-sig")
    sec_p = Path("C:/Users/frel/Desktop/new1/stock_sector_cache.csv")
    sec = pd.read_csv(sec_p, encoding="utf-8-sig") if sec_p.exists() else pd.DataFrame(columns=["종목명", "섹터"])
    return d, sh, dict(zip(sec["종목명"], sec["섹터"]))


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]) if "--out" in args else None
    base = pd.Timestamp(args[args.index("--base") + 1] if "--base" in args else BASE)
    d, sh, sector = load()

    close = d.pivot(index="날짜", columns="종목코드", values="종가")
    vol = d.pivot(index="날짜", columns="종목코드", values="거래량")
    fx = d.pivot(index="날짜", columns="종목코드", values="외국인소진율")
    names = d.groupby("종목코드")["종목명"].last()
    ret1 = close.pct_change(fill_method=None)
    uni1 = ret1.mean(axis=1)                      # 유니버스 동일가중 하루 수익률
    float_sh = (sh.set_index("종목코드")["발행주식수"] * sh.set_index("종목코드")["유동주식비율"].fillna(100) / 100)

    # 세 층 나누기 준비: 종목별 베타120, 시장 뺀 하루 수익률로 닮은꼴 10종목
    r120 = ret1.tail(120)
    u120 = uni1.tail(120)
    beta120 = (r120.apply(lambda x: x.cov(u120)) / u120.var()).round(2)
    resid = ret1.tail(SD_WIN).sub(uni1.tail(SD_WIN), axis=0)
    corr = resid.corr(min_periods=40)
    def look(c):
        own = sector.get(names.get(c, ""), "")
        same = [x for x in close.columns if x != c and own and sector.get(names.get(x, ""), "") == own]
        # 이름표 섹터는 실제로 같이 움직일 때만 쓴다. '기타'는 모아 둔 칸이고, 현대백화점(레저)처럼 이름표가 실제 무리와 다를 수 있다
        fit = float(corr.loc[c, same].mean()) if same and c in corr else np.nan
        if len(same) >= 3 and not own.startswith("기타") and fit >= CORR_MIN:
            return same, f"섹터:{own}", round(fit, 2)
        sim = corr[c].drop(c).dropna().sort_values(ascending=False).head(10).index.tolist() if c in corr else []
        return sim, "닮은꼴:" + "·".join(names[x] for x in sim[:3]), round(float(corr.loc[c, sim].mean()), 2) if sim else np.nan
    i0 = close.index[close.index >= base]
    wins = {"기준": close.index.get_loc(i0[0]) - 1 if len(i0) else None, "20": len(close) - 21}
    wret = {w: (close.iloc[-1] / close.iloc[k] - 1) for w, k in wins.items() if k is not None and k >= 0}

    rows = []
    for c in close.columns:
        p = close[c].dropna()
        if len(p) < 60:
            continue
        r = p.pct_change().dropna()
        sd_raw = float(r.tail(250).std())
        # 평소 출렁임은 중앙값 기반(MAD×1.4826)으로 잰다. 하루 −25% 같은 사건 하루가 '평소'를 부풀리지 않게.
        # 창은 최근 SD_WIN일(지금 국면). 250일은 2026-01~08 격변 국면이 대부분이라 '평소'가 부푼다(국면 오염, 비교용으로만 남김)
        rt = r.tail(SD_WIN)
        sd = float((rt - rt.median()).abs().median() * 1.4826) or sd_raw
        r250 = r.tail(250)
        sd250 = float((r250 - r250.median()).abs().median() * 1.4826)
        v = vol[c].dropna()
        row = {"종목명": names[c], "종목코드": c, "섹터": sector.get(names[c], ""), "표본일수": len(p),
               "마지막일": p.index[-1].strftime("%Y-%m-%d"), "지금": p.iloc[-1], "일σ%": round(sd * 100, 2),
               "일σ표준%": round(sd_raw * 100, 2), "일σ250%": round(sd250 * 100, 2)}
        fs = float_sh.get(c)
        row["회전%"] = round(float(v.tail(60).median()) / fs * 100, 3) if fs and fs == fs and fs > 0 else np.nan
        u = uni1.reindex(r.index).tail(250)
        rr = r.tail(250)
        row["베타"] = round(float(np.cov(rr, u)[0, 1] / u.var()), 2) if u.var() > 0 else np.nan
        for n in NS:
            if len(p) <= n:
                continue
            hist = (p / p.shift(n) - 1).dropna()
            now = float(hist.iloc[-1])
            row[f"r{n}%"] = round(now * 100, 2)
            row[f"z{n}"] = round(now / (sd * math.sqrt(n)), 2) if sd > 0 else np.nan
            row[f"분위{n}"] = round(float((hist < now).mean()), 2)
            uh = (close / close.shift(n) - 1)
            ur = uh.iloc[-1]
            # 시장(유니버스 평균)을 뺀 n일 수익률의 자기 분위. 오르는 장·빠지는 장의 바닥이 섞이는 국면 오염을 덜어 낸다
            ex = (hist - uh.mean(axis=1).reindex(hist.index)).dropna()
            row[f"초과분위{n}"] = round(float((ex < ex.iloc[-1]).mean()), 2) if len(ex) > 20 else np.nan
            row[f"초과{n}%p"] = round((now - float(ur.mean())) * 100, 2)
            peers = [x for x in close.columns if sector.get(names.get(x, ""), "") == row["섹터"] and x != c]
            row[f"섹터{n}%p"] = round((now - float(ur[peers].mean())) * 100, 2) if row["섹터"] and peers else np.nan
            if n >= 5:
                # 경로: 그 n일 하락이 하루 사건인가, 꾸준히 흘러내린 것인가
                win = r.tail(n)
                worst = float(win.min())
                row[f"최악일{n}%"] = round(worst * 100, 2)
                row[f"최악일비중{n}"] = round(math.log1p(worst) / math.log1p(now), 2) if now < 0 and worst < 0 else np.nan
                row[f"하락일{n}"] = int((win < 0).sum())
                rest = (1 + now) / (1 + worst) - 1 if worst < 0 else now
                row[f"최악일빼고{n}%"] = round(rest * 100, 2)
        # 최근 20일 안 가장 큰 하락일(사건일)과 그 뒤 흐름
        w20 = r.tail(20)
        if len(w20) == 20:
            ev = w20.idxmin()
            row["사건일"] = ev.strftime("%Y-%m-%d")
            row["사건일%"] = round(float(w20.min()) * 100, 2)
            row["사건배"] = round(float(w20.min()) / sd, 1) if sd > 0 else np.nan
            # 그날 시장(유니버스 평균)과 비교: 시장 전체의 날인가, 이 종목만의 날인가
            um = float(uni1.get(ev, np.nan))
            row["사건일시장%"] = round(um * 100, 2)
            row["사건초과%p"] = round((float(w20.min()) - um) * 100, 2)
            after = p[p.index >= ev]
            row["사건후%"] = round(float(after.iloc[-1] / after.iloc[0] - 1) * 100, 2)
            row["사건후일수"] = len(after) - 1
        # 과거 비슷한 자리: 자기 20일 수익률 하위 10% 뒤 20거래일
        r20 = (p / p.shift(20) - 1)
        f20 = (p.shift(-20) / p - 1)
        ok = r20.notna() & f20.notna()
        if ok.sum() > 40:
            cut = r20[ok].quantile(0.10)
            sel = f20[ok & (r20 <= cut)]
            row["후20%"] = round(float(sel.median()) * 100, 2)
            row["후20n"] = int(len(sel))
            row["평소20%"] = round(float(f20[ok].median()) * 100, 2)
        # 평지 여러 창
        for w in WS:
            if len(p) < w + 60:
                continue
            pw = p.tail(w)
            band = (pw.max() - pw.min()) / pw.mean()
            row[f"평탄{w}"] = round(band / (sd * math.sqrt(w)), 2) if sd > 0 else np.nan
            vw = v.reindex(pw.index).median()
            vpre = v[v.index < pw.index[0]].tail(60).median()
            row[f"거래량배{w}"] = round(float(vw / vpre), 2) if vpre and vpre > 0 else np.nan
        # 거래량 지속: 최근 10일 중 직전 60일 중간값의 2배 이상이었던 날 수(하루 튄 것과 며칠 이어진 것을 가른다)
        if len(v) >= 70:
            base = v.iloc[-70:-10].median()
            row["거래량2배일10"] = int((v.tail(10) >= 2 * base).sum()) if base > 0 else np.nan
        # 세 층: 시장몫 · 섹터몫 · 자기몫 (단순 수익률 기준 덧셈 근사)
        grp, label, fit = look(c)
        row["비교군"] = label
        row["비교군상관"] = fit  # 낮으면(0.2 안팎) 닮은꼴도 우연일 수 있어 섹터몫을 믿지 않는다
        row["베타120"] = float(beta120.get(c, np.nan))
        for w, wr in wret.items():
            if pd.isna(wr.get(c)):
                continue
            med = float(wr.median())
            mkt = row["베타120"] * med
            g = [(wr[x] - beta120.get(x, np.nan) * med) for x in grp if pd.notna(wr.get(x)) and pd.notna(beta120.get(x))]
            sec_part = float(np.median(g)) if len(g) >= 3 else 0.0
            row[f"시장몫{w}%p"] = round(mkt * 100, 2)
            row[f"섹터몫{w}%p"] = round(sec_part * 100, 2)
            row[f"자기몫{w}%p"] = round((float(wr[c]) - mkt - sec_part) * 100, 2)
        # 외인 보유율
        f = fx[c].dropna()
        if len(f) > 60:
            fsd = float(f.diff().dropna().tail(SD_WIN).std())
            for n in (5, 20, 60):
                dn = float(f.iloc[-1] - f.iloc[-1 - n])
                row[f"f{n}%p"] = round(dn, 2)
                row[f"fz{n}"] = round(dn / (fsd * math.sqrt(n)), 2) if fsd > 0 else np.nan
            row["외인%"] = float(f.iloc[-1])
        rows.append(row)

    df = pd.DataFrame(rows)
    print(f"# profile · 관심종목 {len(df)}개 · 데이터 {d['날짜'].min():%Y-%m-%d} ~ {d['날짜'].max():%Y-%m-%d}"
          f" (마지막 행이 오늘이면 장중값) · 거래정지일 제외")
    if out:
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"# 저장: {out}")
    else:
        print(df.to_csv(index=False).rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
