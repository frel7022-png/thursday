"""agent_view — 써스데이가 앱 기능을 텍스트로 보는 조회 도구 (2026-10-15 새러데이 작성, 대표 승인 스펙).

    python C:/Users/frel/Desktop/Thursday/tools/agent_view.py <명령> [인자] [--ledger 경로] [--verdicts]

[써스데이 장부 기준]
  holdings          보유 종목·수량·평단·현재가·손익률·비중, 녹색 여부, 최초진입가·마지막 매수가
  watering          물타기 중(2회 이상) 종목: 마지막 매수가·최초진입가·평단 대비 %, 매수 횟수
  updown            전부 판 종목: 마지막 매도가 대비 %, 매도일, 매도 후 저점
  take              총자산·예수금·원금 대비, 오늘 변화 vs 혼합지수(삼성·하이닉스 제외), 시작일 이후 누적
  report            16:30 보고서용: 오늘 거래 + take + 보유별 다음 행동 가격 + 외인 최신일
  cap               종목당 상한(총자산 5%) 대비 현재 비중과 남은 매수 여력
[공통 원자료]
  flow 종목 [시작일]   주가·외인·기관 원숫자(구간 수익률, 유니버스 평균, 보유율 %p, 하루 변화 σ 배수, 외인몫·기관몫, 순매수일)
  series 종목 [시작일] 일별 원시 시계열 CSV(날짜·종가·거래량·외인순매수·기관순매수·외인보유율)
  screen [시작일]      관심종목 전부를 flow와 같은 원숫자로 한 번에 CSV(주가 수익률 낮은 순). 후보 풀은 써스데이가 직접 거른다

원칙
- 기본 출력은 원숫자만. 판정(새러데이 CFG 문턱 통과, 착시, 꺾임)은 --verdicts를 붙여야 나온다.
  자기 판단을 먼저 기록한 뒤 판정을 본다(Thursday CLAUDE.md).
- 계산은 new1 함수를 import해서 쓴다(로직 복제 없음). 파일은 하나도 쓰지 않는다.
  new1에서 쓰지 않는 함수: refresh_*, save_*, snapshot_*, update_*_cache, append_* (new1 파일을 덮어씀).
- 장부: Thursday/ledger/transactions.csv(new1과 같은 열), ledger/account_state.csv(예수금·최초자본·수수료율).
  매도 거래세 0.2%는 new1 apply_transaction 규칙 그대로(매수 수수료 0).
"""
import math
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from new1_locator import find_new1  # noqa: E402

NEW1 = find_new1()
import portfolio_core as core  # noqa: E402

CAP = 0.05          # 종목당 상한 = 총자산의 5% (대표 결정, 2026-10-15)
REENTRY = -0.05     # 재진입 참고가 = 마지막 매도가 −5% (대표 행동 문턱)


# ------------------------------------------------------------------ 공통
def _out(s=""):
    print(s)


def pct(v, d=2, unit="%"):
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:+.{d}f}{unit}"


def name_to_code() -> dict:
    m = {}
    for f in ("stock_code_cache.csv", "watchlist.csv"):
        p = NEW1 / f
        if p.exists():
            df = pd.read_csv(p, dtype=str)
            m.update(dict(zip(df["종목명"], df["종목코드"])))
    return m


def load_ledger(path: Path):
    tx = pd.read_csv(path, dtype={"id": str}, keep_default_na=False, na_values=[""]) if path.exists() else pd.DataFrame(columns=core.TX_COLUMNS)
    for c in core.TX_COLUMNS:
        if c not in tx.columns:
            tx[c] = ""
    st = pd.read_csv(path.parent / "account_state.csv").iloc[0]
    return tx[core.TX_COLUMNS], float(st["최초자본"]), float(st.get("수수료율", 0.002))


class Book:
    """써스데이 장부를 재생한 결과 + 실시간 시세."""

    def __init__(self, ledger: Path):
        self.tx, self.initial, self.fee = load_ledger(ledger)
        self.now = datetime.now(core.KST)
        self.today = self.now.strftime("%Y-%m-%d")
        self.n2c = name_to_code()
        h, st, self.tx = core.rebuild_portfolio_from_transactions(self.tx, self.initial, self.fee)
        h = h.copy()
        h["종목코드"] = [c if isinstance(c, str) and c else self.n2c.get(n, "") for n, c in zip(h["종목명"], h["종목코드"])]
        self.cash = float(st["cash"])
        codes = [c for c in h["종목코드"] if c]
        sold = self.tx[self.tx["구분"] == "매도"]["종목명"].unique().tolist()
        extra = [self.n2c[n] for n in sold if n in self.n2c]
        self.quotes, _ = core.fetch_quotes(list(dict.fromkeys(codes + extra))) if codes or extra else ({}, [])
        h["현재가"] = [float((self.quotes.get(c) or {}).get("price") or 0) or float(p or 0) for c, p in zip(h["종목코드"], h["현재가"])]
        h["등락률"] = [float((self.quotes.get(c) or {}).get("change_pct") or 0) for c in h["종목코드"]]
        h["수량"] = pd.to_numeric(h["수량"])
        h["평단가"] = pd.to_numeric(h["평단가"])
        h["평가금액"] = h["수량"] * h["현재가"]
        h["손익"] = (h["현재가"] - h["평단가"]) * h["수량"]
        h["손익률"] = (h["현재가"] / h["평단가"] - 1) * 100
        self.h = h
        self.stock_val = float(h["평가금액"].sum())
        self.total = self.stock_val + self.cash

    def trade_points(self, name):
        pts = core.get_holding_trade_points(self.tx, name)
        return pts[pts["구분"] == "매수"]

    def header(self):
        last = self.tx["날짜"].max() if not self.tx.empty else "거래 없음"
        _out(f"[써스데이 장부] {self.now:%Y-%m-%d %H:%M} 실시간 시세 · 장부 마지막 거래 {last} · 원금 {self.initial:,.0f}원")


# ------------------------------------------------------------------ 써스데이 장부 기준
def cmd_holdings(b: Book):
    b.header()
    if b.h.empty:
        _out("보유 없음")
        return
    _out(f"보유 {len(b.h)}종목 · 총평가 {b.stock_val:,.0f}원 · 예수금 {b.cash:,.0f}원 · 총자산 {b.total:,.0f}원")
    _out("종목 | 코드 | 섹터 | 수량 | 평단 | 현재가 | 오늘 | 손익률 | 손익 | 비중 | 최초진입가 | 마지막매수가 | 매수횟수 | 녹색")
    for _, r in b.h.sort_values("평가금액", ascending=False).iterrows():
        bu = b.trade_points(r["종목명"])
        first = float(bu.iloc[0]["단가"]) if not bu.empty else float("nan")
        last = float(bu.iloc[-1]["단가"]) if not bu.empty else float("nan")
        green = "녹색" if len(bu) >= 2 and r["현재가"] >= first else "-"
        _out(f"{r['종목명']} | {r['종목코드']} | {r['섹터']} | {r['수량']:g} | {r['평단가']:,.0f} | {r['현재가']:,.0f} | "
             f"{pct(r['등락률'])} | {pct(r['손익률'])} | {r['손익']:+,.0f} | {r['평가금액'] / b.total * 100:.2f}% | "
             f"{first:,.0f} | {last:,.0f} | {len(bu)} | {green}")
    _out("녹색 = 물 탄 종목(매수 2회 이상)이 최초진입가를 회복 — 대표의 익절 검토 신호")


def cmd_watering(b: Book):
    b.header()
    rows = []
    for _, r in b.h.iterrows():
        bu = b.trade_points(r["종목명"])
        if len(bu) < 2:
            continue
        first, last = float(bu.iloc[0]["단가"]), float(bu.iloc[-1]["단가"])
        rows.append((r["종목명"], len(bu), bu.iloc[-1]["날짜"], (r["현재가"] / last - 1) * 100,
                     (r["현재가"] / first - 1) * 100, (r["평단가"] / first - 1) * 100, r["현재가"], last, first, r["평단가"]))
    if not rows:
        _out("물타기 중인 종목 없음")
        return
    _out("종목 | 매수횟수 | 마지막매수일 | 마지막매수가 대비 | 최초진입가 대비(지금) | 최초진입가 대비(평단) | 현재가 | 마지막매수가 | 최초진입가 | 평단")
    for x in sorted(rows, key=lambda x: x[3]):
        _out(f"{x[0]} | {x[1]} | {x[2]} | {pct(x[3])} | {pct(x[4])} | {pct(x[5])} | {x[6]:,.0f} | {x[7]:,.0f} | {x[8]:,.0f} | {x[9]:,.0f}")


def cmd_updown(b: Book, ph=None):
    b.header()
    closed = core.get_closed_out_last_sells(b.h, b.tx)
    if closed.empty:
        _out("전부 판 종목 없음")
        return
    _out("종목 | 매도일 | 매도가 | 지금 | 매도가 대비 | 매도 후 최저 종가(날짜) | 재진입 참고가(매도가 −5%)")
    rows = []
    for _, r in closed.iterrows():
        code = b.n2c.get(r["종목명"], "")
        now = (b.quotes.get(code) or {}).get("price")
        low = "-"
        if ph is not None and code:
            g = ph[(ph["종목코드"] == code) & (ph["날짜"] > r["매도일"])]
            if not g.empty:
                i = g["종가"].astype(float).idxmin()
                low = f"{float(g.loc[i, '종가']):,.0f}({g.loc[i, '날짜'][5:]})"
        rows.append((r["종목명"], r["매도일"], float(r["매도가"]), now, low))
    for nm, d, sp, now, low in sorted(rows, key=lambda x: (x[3] / x[2] - 1) if x[3] else 0):
        _out(f"{nm} | {d} | {sp:,.0f} | {f'{now:,.0f}' if now else '-'} | {pct((now / sp - 1) * 100) if now else '-'} | {low} | {sp * (1 + REENTRY):,.0f}")


def _index_frames(b: Book):
    import live_check
    s = live_check.live_snapshot(holdings=b.h if not b.h.empty else None, quotes=b.quotes or None)
    return s


def take_numbers(b: Book) -> dict:
    """오늘 성적 숫자 — cmd_take와 모니터링 앱이 같이 쓴다."""
    tx = b.tx
    prev_tx = tx[tx["날짜"] < b.today]
    hp, sp, _ = core.rebuild_portfolio_from_transactions(prev_tx, b.initial, b.fee)
    prev_val = 0.0
    for _, r in hp.iterrows():
        code = r["종목코드"] or b.n2c.get(r["종목명"], "")
        q = b.quotes.get(code) or core.fetch_quotes([code])[0].get(code) or {}
        px, chg = q.get("price"), q.get("change_pct") or 0
        if px:
            prev_val += float(r["수량"]) * px / (1 + chg / 100)
    prev_total = prev_val + float(sp["cash"])
    t = tx[tx["날짜"] == b.today]
    out = {"total": b.total, "initial": b.initial, "cash": b.cash, "stock_val": b.stock_val, "n": len(b.h),
           "day_won": b.total - prev_total, "day_pct": (b.total / prev_total - 1) * 100 if prev_total else 0.0,
           "realized_today": float(pd.to_numeric(t.loc[t["구분"] == "매도", "실현손익"], errors="coerce").sum()),
           "stock_day": None, "ex_day": None, "main_day": None, "basis": "", "start": None, "bench_cum": None}
    if not b.h.empty and b.stock_val:
        prev_sv = float((b.h["평가금액"] / (1 + b.h["등락률"] / 100)).sum())
        out["stock_day"] = (b.stock_val / prev_sv - 1) * 100 if prev_sv else None
    try:
        s = _index_frames(b)
        out.update(ex_day=s["ex"][1] * 100, main_day=s["main"][1] * 100, basis=s["basis"])
        if not tx.empty:
            start = tx["날짜"].min()
            ex = core.synthetic_kospi_ex_bigcap(s["idx"], s["bigdf"])
            base = ex[ex["날짜"] < start]
            if not base.empty:
                k0, q0 = float(base["KOSPI"].iloc[-1]), float(base["KOSDAQ"].iloc[-1])
                k1, q1 = float(ex["KOSPI"].iloc[-1]), float(ex["KOSDAQ"].iloc[-1])
                out.update(start=start, bench_cum=(s["wk"] * (k1 / k0 - 1) + (1 - s["wk"]) * (q1 / q0 - 1)) * 100)
    except Exception as e:  # 지수 조회 실패해도 계좌 숫자는 보여준다
        out["index_error"] = str(e)
    return out


def cmd_take(b: Book, header=True):
    if header:
        b.header()
    tx = b.tx
    # 어제 종가 기준 장부(오늘 거래 전)와 그 평가액
    prev_tx = tx[tx["날짜"] < b.today]
    hp, sp, _ = core.rebuild_portfolio_from_transactions(prev_tx, b.initial, b.fee)
    prev_val = 0.0
    for _, r in hp.iterrows():
        code = r["종목코드"] or b.n2c.get(r["종목명"], "")
        q = b.quotes.get(code) or core.fetch_quotes([code])[0].get(code) or {}
        px, chg = q.get("price"), q.get("change_pct") or 0
        if px:
            prev_val += float(r["수량"]) * px / (1 + chg / 100)
    prev_total = prev_val + float(sp["cash"])
    t = tx[tx["날짜"] == b.today]
    realized = pd.to_numeric(t.loc[t["구분"] == "매도", "실현손익"], errors="coerce").sum()
    _out(f"총자산 {b.total:,.0f}원 · 원금 대비 {b.total - b.initial:+,.0f}원 ({pct((b.total / b.initial - 1) * 100)})")
    _out(f"예수금 {b.cash:,.0f}원 ({b.cash / b.total * 100:.1f}%) · 총평가 {b.stock_val:,.0f}원 · 보유 {len(b.h)}종목")
    _out(f"어제 대비 {b.total - prev_total:+,.0f}원 ({pct((b.total / prev_total - 1) * 100)}) · 오늘 실현손익 {realized:+,.0f}원")
    try:
        s = _index_frames(b)
        _out(f"혼합지수(삼성·하이닉스 제외) 오늘 {pct(s['ex'][1] * 100)} · 일반 {pct(s['main'][1] * 100)} · 기준 {s['basis']}")
        if not tx.empty:
            start = tx["날짜"].min()
            ex = core.synthetic_kospi_ex_bigcap(s["idx"], s["bigdf"])
            base = ex[ex["날짜"] < start]
            if not base.empty:
                k0, q0 = float(base["KOSPI"].iloc[-1]), float(base["KOSDAQ"].iloc[-1])
                k1, q1 = float(ex["KOSPI"].iloc[-1]), float(ex["KOSDAQ"].iloc[-1])
                bench = s["wk"] * (k1 / k0 - 1) + (1 - s["wk"]) * (q1 / q0 - 1)
                _out(f"시작일({start}) 이후 누적: 써스데이 계좌 {pct((b.total / b.initial - 1) * 100)} · "
                     f"혼합지수(삼성·하이닉스 제외) {pct(bench * 100)}")
    except Exception as e:  # 지수 조회 실패해도 계좌 숫자는 보여준다
        _out(f"지수 조회 실패: {e}")


def cmd_cap(b: Book):
    b.header()
    lim = b.total * CAP
    _out(f"종목당 상한 {CAP:.0%} = {lim:,.0f}원 (총자산 {b.total:,.0f}원 기준, 조금 넘는 건 괜찮음 — 대표)")
    if b.h.empty:
        _out("보유 없음 — 모든 종목 여력 = 상한 전액")
        return
    _out("종목 | 평가금액 | 비중 | 남은 여력(원) | 남은 여력(주, 현재가 기준)")
    for _, r in b.h.sort_values("평가금액", ascending=False).iterrows():
        room = lim - r["평가금액"]
        _out(f"{r['종목명']} | {r['평가금액']:,.0f} | {r['평가금액'] / b.total * 100:.2f}% | {room:,.0f} | "
             f"{max(0, math.floor(room / r['현재가'])) if r['현재가'] else '-'}")


def cmd_report(b: Book, data):
    b.header()
    _out()
    _out("■ 오늘 거래")
    t = b.tx[b.tx["날짜"] == b.today]
    if t.empty:
        _out("오늘 거래 없음")
    for _, r in t.iterrows():
        q, p = float(r["수량"]), float(r["단가"])
        rp = pd.to_numeric(r["실현손익"], errors="coerce")
        _out(f"{r['구분']} {r['종목명']} {q:g}주 @ {p:,.0f} = {q * p:,.0f}원"
             + (f" · 실현 {rp:+,.0f}원" if r["구분"] == "매도" and pd.notna(rp) else "") + (f" · {r['메모']}" if isinstance(r["메모"], str) and r["메모"] else ""))
    _out()
    _out("■ 오늘 성적")
    cmd_take(b, header=False)
    _out()
    _out("■ 보유별 다음 행동 가격")
    if b.h.empty:
        _out("보유 없음")
    for _, r in b.h.iterrows():
        bu = b.trade_points(r["종목명"])
        first, last = float(bu.iloc[0]["단가"]), float(bu.iloc[-1]["단가"])
        tip = (f"익절 검토 = 최초진입가 {first:,.0f} 회복" if len(bu) >= 2
               else f"익절 참고 = 평단 +3.9% {r['평단가'] * 1.039:,.0f} (대표 익절 중앙값)")
        _out(f"{r['종목명']} 지금 {r['현재가']:,.0f} · 물타기 기준 = 마지막 매수가 {last:,.0f} (−1.4% {last * 0.986:,.0f} · −3.9% {last * 0.961:,.0f}) · {tip}")
    closed = core.get_closed_out_last_sells(b.h, b.tx)
    for _, r in closed.iterrows():
        _out(f"{r['종목명']} (전부 매도) 재진입 참고 = 매도가 {float(r['매도가']):,.0f} −5% → {float(r['매도가']) * (1 + REENTRY):,.0f}")
    if data is not None:
        _out()
        _out(f"외인·거래량 DB 최신일 {data['fh']['날짜'].max()} (오늘 외인은 16:13 적재 이후 들어옴)")


# ------------------------------------------------------------------ 공통 원자료
def _resolve(arg, n2c, ph):
    if len(arg) == 6 and arg[:5].isdigit():
        return arg
    if arg in n2c:
        return n2c[arg]
    m = ph[ph["종목명"] == arg]
    return m["종목코드"].iloc[0] if not m.empty else None


def _window(df, code, start):
    g = df[df["종목코드"] == code].sort_values("날짜")
    return g, g[g["날짜"] >= start] if start else g


def _uni_avg(ph, live, start, before):
    """같은 구간 관심종목 평균 수익률(%)과 종목 수. before=True면 시작일 직전 종가가 기준."""
    base = ph[ph["날짜"] < start].sort_values("날짜").groupby("종목코드").last()["종가"] if before else \
        ph[ph["날짜"] >= start].sort_values("날짜").groupby("종목코드").first()["종가"]
    uni = [(live[c] / float(v) - 1) * 100 for c, v in base.items() if live.get(c) and float(v) > 0]
    return (sum(uni) / len(uni) if uni else float("nan")), len(uni)


def flow_numbers(data, code, start, uni=None):
    """flow·screen 공용 원숫자. 주가 기록이 없으면 None, 외인 기록이 없으면 외인 칸이 빠진 dict."""
    ph, fh, live = data["ph"], data["fh"], data["live"]
    pg, pw = _window(ph, code, start)
    fg, fw = _window(fh, code, start)
    if pg.empty or pw.empty:
        return None
    if not start:  # 시작일을 안 주면 주가 첫 기록일. 외인 구간도 같은 날부터 잘라 같은 기간으로 맞춘다
        start = pg["날짜"].iloc[0]
        fw = fg[fg["날짜"] >= start]
    prev_p = pg[pg["날짜"] < start]
    p0 = float(prev_p["종가"].iloc[-1]) if not prev_p.empty else float(pw["종가"].iloc[0])
    p_now = live.get(code) or float(pg["종가"].iloc[-1])
    if uni is None:
        uni = _uni_avg(ph, live, start, not prev_p.empty)
    r = dict(code=code, name=pg["종목명"].iloc[-1], start=start, p0=p0, p_now=p_now, ret=(p_now / p0 - 1) * 100,
             uni_avg=uni[0], uni_n=uni[1], f_last=fg["날짜"].max() if not fg.empty else "-", has_f=not (fg.empty or fw.empty))
    if not r["has_f"]:
        return r
    prev_f = fg[fg["날짜"] < start]
    f0 = float(prev_f["외국인보유율"].iloc[-1]) if not prev_f.empty else float(fw["외국인보유율"].iloc[0])
    f1 = float(fg["외국인보유율"].iloc[-1])
    hi_i, lo_i = fw["외국인보유율"].astype(float).idxmax(), fw["외국인보유율"].astype(float).idxmin()
    d_all = fg["외국인보유율"].astype(float).diff().dropna()
    sd = float(d_all.std()) if len(d_all) > 2 else float("nan")
    n = len(fw)
    z = (f1 - f0) / (sd * math.sqrt(n)) if sd and sd == sd and sd > 0 else float("nan")
    fhi = float(fw.loc[hi_i, "외국인보유율"])
    give = (fhi - f1) / (fhi - f0) * 100 if fhi > f0 else float("nan")
    w = fw.merge(pg[["날짜", "종가"]], on="날짜", how="left")
    fn = pd.to_numeric(w["외국인순매수"], errors="coerce").fillna(0)
    inn = pd.to_numeric(w["기관순매수"], errors="coerce").fillna(0)
    vol = pd.to_numeric(w["거래량"], errors="coerce").fillna(0)
    px = pd.to_numeric(w["종가"], errors="coerce").ffill().bfill()
    vs = float(vol.sum())
    streak = best = 0
    for v in fn:
        streak = streak + 1 if v > 0 else 0
        best = max(best, streak)
    r.update(f0=f0, f1=f1, dp=f1 - f0, rel=(f1 / f0 - 1) * 100 if f0 else float("nan"),
             fhi=fhi, fhi_d=fw.loc[hi_i, "날짜"], flo=float(fw.loc[lo_i, "외국인보유율"]), flo_d=fw.loc[lo_i, "날짜"],
             give=give, sd=sd, n=n, z=z, fn_sh=float(fn.sum()), fn_won=float((fn * px).sum()),
             in_sh=float(inn.sum()), in_won=float((inn * px).sum()), vol=vs,
             f_share=fn.sum() / vs * 100 if vs else float("nan"), i_share=inn.sum() / vs * 100 if vs else float("nan"),
             f_days=int((fn > 0).sum()), best=best,
             peak_age=len(fg[fg["날짜"] > fw.loc[hi_i, "날짜"]]),
             last5=float(fg["외국인보유율"].astype(float).tail(6).diff().dropna().sum()))
    return r


def _verdict(r):
    cfg = r["dp"] >= 0.3 or (r["f0"] >= 3 and (r["rel"] if r["rel"] == r["rel"] else 0) >= 5)
    illusion = r["give"] == r["give"] and r["give"] >= 30
    bent = r["peak_age"] >= 5 and r["last5"] < 0
    return cfg, illusion, bent


def cmd_flow(data, n2c, arg, start, verdicts):
    code = _resolve(arg, n2c, data["ph"])
    if not code:
        _out(f"{arg}: 관심종목에서 못 찾음")
        return
    r = flow_numbers(data, code, start)
    if r is None:
        _out(f"{arg}: 주가 기록 없음")
        return
    _out(f"[{r['name']}({code})] 구간 {r['start']} ~ 지금 · 주가 {datetime.now(core.KST):%m-%d %H:%M} 실시간 · 외인 DB 최신일 {r['f_last']}")
    _out(f"주가 {r['p0']:,.0f} → {r['p_now']:,.0f} ({pct(r['ret'])}) · 같은 구간 관심종목 {r['uni_n']}개 평균 {pct(r['uni_avg']) if r['uni_n'] else '-'}")
    if not r["has_f"]:
        _out("외인 기록 없음")
        return
    _out(f"외인 보유율 {r['f0']:.2f}% → {r['f1']:.2f}% ({r['dp']:+.2f}%p) · 상대(참고) {pct(r['rel'], 1)}")
    give = f"{r['give']:.0f}%" if r["give"] == r["give"] else "-"
    _out(f"구간 고점 {r['fhi']:.2f}%({r['fhi_d'][5:]}) · 저점 {r['flo']:.2f}%({r['flo_d'][5:]}) · 고점 대비 반납 {give}")
    _out(f"하루 변화 표준편차 {r['sd']:.3f}%p (전 기간) · 구간 {r['n']}일 · 증가 / (σ×√n) = {r['z']:.2f}배" if r["z"] == r["z"] else f"하루 변화 표준편차 계산 불가 · 구간 {r['n']}일")
    _out(f"외인 순매수 {r['fn_sh']:+,.0f}주 (약 {r['fn_won']:+,.0f}원) · 기관 순매수 {r['in_sh']:+,.0f}주 (약 {r['in_won']:+,.0f}원) · 거래량 합 {r['vol']:,.0f}주")
    _out(f"외인몫 {pct(r['f_share'], 1)} · 기관몫 {pct(r['i_share'], 1)} "
         f"(구간 순매수 합 ÷ 거래량 합) · 외인 순매수일 {r['f_days']}/{r['n']}일 · 최장 연속 {r['best']}일")
    if verdicts:
        cfg, illusion, bent = _verdict(r)
        _out(f"[판정] 새러데이 CFG 외인 문턱(+0.3%p 또는 기준 3%↑·상대 +5%↑): {'통과' if cfg else '미달'} · "
             f"착시(고점 대비 30%↑ 반납): {'예' if illusion else '아니오'} · "
             f"꺾임(고점 5거래일 경과 + 최근 5일 감소): {'예' if bent else '아니오'}")


def cmd_screen(data, start, verdicts):
    """관심종목 전부를 flow와 같은 원숫자로 한 번에 잰다. CSV로 출력(주가 수익률 낮은 순). 거르는 건 써스데이 몫."""
    ph, live = data["ph"], data["live"]
    codes = ph["종목코드"].dropna().unique().tolist()
    uni_cache = {}
    rows = []
    for code in codes:
        pg = ph[ph["종목코드"] == code]
        s = start or pg["날짜"].min()
        before = not pg[pg["날짜"] < s].empty
        key = (s, before)
        if key not in uni_cache:
            uni_cache[key] = _uni_avg(ph, live, s, before)
        r = flow_numbers(data, code, start, uni_cache[key])
        if r is None:
            continue
        row = {"종목명": r["name"], "종목코드": code, "구간시작": r["start"], "시작가": round(r["p0"]), "지금": round(r["p_now"]),
               "주가%": round(r["ret"], 2), "유니버스평균%": round(r["uni_avg"], 2), "유니버스대비%p": round(r["ret"] - r["uni_avg"], 2)}
        if r["has_f"]:
            row.update({"외인시작%": round(r["f0"], 2), "외인지금%": round(r["f1"], 2), "외인%p": round(r["dp"], 2),
                        "σ배수": round(r["z"], 2) if r["z"] == r["z"] else "", "고점반납%": round(r["give"]) if r["give"] == r["give"] else "",
                        "외인몫%": round(r["f_share"], 1) if r["f_share"] == r["f_share"] else "",
                        "기관몫%": round(r["i_share"], 1) if r["i_share"] == r["i_share"] else "",
                        "외인순매수원": round(r["fn_won"]), "순매수일": r["f_days"], "구간일수": r["n"], "최장연속": r["best"],
                        "외인최신일": r["f_last"]})
            if verdicts:
                cfg, illusion, bent = _verdict(r)
                row.update({"CFG문턱": "통과" if cfg else "미달", "착시": "예" if illusion else "", "꺾임": "예" if bent else ""})
        rows.append(row)
    df = pd.DataFrame(rows).sort_values("주가%")
    _out(f"# screen · 관심종목 {len(df)}개 · 주가 {datetime.now(core.KST):%Y-%m-%d %H:%M} 실시간 · 구간 시작 = {start or '종목별 기준일(DB 첫 기록)'}")
    _out(df.to_csv(index=False).rstrip())


def cmd_series(data, n2c, arg, start):
    ph, fh = data["ph"], data["fh"]
    code = _resolve(arg, n2c, ph)
    if not code:
        _out(f"{arg}: 관심종목에서 못 찾음")
        return
    p = ph[ph["종목코드"] == code][["날짜", "종가"]]
    f = fh[fh["종목코드"] == code][["날짜", "거래량", "외국인순매수", "기관순매수", "외국인보유율"]]
    m = p.merge(f, on="날짜", how="outer").sort_values("날짜")
    if start:
        m = m[m["날짜"] >= start]
    _out(m.to_csv(index=False).rstrip())


# ------------------------------------------------------------------ main
def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    import warnings
    warnings.filterwarnings("ignore")
    args = [a for a in sys.argv[1:]]
    verdicts = "--verdicts" in args
    args = [a for a in args if a != "--verdicts"]
    ledger = HERE / "ledger" / "transactions.csv"
    if "--ledger" in args:
        i = args.index("--ledger")
        ledger = Path(args[i + 1])
        del args[i:i + 2]
    if not args:
        _out(__doc__)
        return 1
    cmd, rest = args[0], args[1:]
    need_data = cmd in ("flow", "series", "report", "updown", "screen")
    data = None
    if need_data:
        import daily_link_report as link
        data = link.load_data()
    if cmd == "screen":
        is_date = lambda s: len(s) == 10 and s[4] == "-" and s[7] == "-"
        cmd_screen(data, next((a for a in rest if is_date(a)), None), verdicts)
        return 0
    if cmd in ("flow", "series"):
        if not rest:
            _out("종목명 또는 코드를 줘")
            return 1
        n2c = name_to_code()
        # 공백 든 종목명("JYP Ent.")은 셸이 쪼갠다 — 날짜(YYYY-MM-DD)가 아닌 인자는 이어 붙여 이름으로 본다
        is_date = lambda s: len(s) == 10 and s[4] == "-" and s[7] == "-"
        start = next((a for a in rest if is_date(a)), None)
        target = " ".join(a for a in rest if not is_date(a))
        (cmd_flow(data, n2c, target, start, verdicts) if cmd == "flow" else cmd_series(data, n2c, target, start))
        return 0
    b = Book(ledger)
    if cmd == "holdings":
        cmd_holdings(b)
    elif cmd == "watering":
        cmd_watering(b)
    elif cmd == "updown":
        cmd_updown(b, data["ph"])
    elif cmd == "take":
        cmd_take(b)
    elif cmd == "cap":
        cmd_cap(b)
    elif cmd == "report":
        cmd_report(b, data)
    else:
        _out(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
