"""관심종목 투자자별 순매수 2년치 — 써스데이 1545 요청(대표 지시), 새러데이 작성 2026-10-19.

    python C:/Users/frel/Desktop/Thursday/tools/fetch_investor_long.py [시작일 YYYY-MM-DD]   # 기본 2024-10-01

출력 (Thursday/data/investor_long.csv, 덮어씀 — 다시 돌리면 그날까지로 갱신):
    날짜,종목코드,종목명,외국인,기관,개인,종가,거래량,외국인보유율,외국인_금액근사,기관_금액근사,개인_금액근사
출처: 네이버 모바일 API `m.stock.naver.com/api/stock/{코드}/trend?pageSize=60&bizdate=YYYYMMDD`
    (new1 investor_flow가 쓰는 integration API의 같은 계열. bizdate **이전** 거래일부터 60일씩 거꾸로 준다 — 그날은 빠진다).
- 외국인·기관·개인 = 그날 **순매수 수량(주)**. 기관은 합계뿐(세부 연기금·투신 등은 이 출처에 없다).
- 금액은 이 출처가 주지 않는다 → `*_금액근사` = 순매수 수량 × 그날 종가(원). 실제 체결 단가 평균과 다르니 근사로만 쓸 것.
- 종가는 수정주가가 아니라 그날 표시 종가(액면분할 전후로 끊김 가능 — 수정주가가 필요하면 daily_long.csv).
- 외국인보유율 = 그날 %(new1 investor_flow와 같은 값 계열).
- 개인 = 이 출처의 individualPureBuyQuant. 외국인+기관+개인 합이 0이 아닐 수 있다(기타법인 등 빠짐).
관심종목 목록 = new1 watchlist.csv. 요청 사이 0.2초 쉰다(비공식 경로).
"""
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from new1_locator import find_new1  # noqa: E402

NEW1 = find_new1()
OUT = Path(__file__).resolve().parent.parent / "data"
H = {"User-Agent": "Mozilla/5.0"}
PAGE = 60


def _num(s) -> float | None:
    try:
        return float(str(s).replace(",", "").replace("%", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def trend(code: str, start: str) -> list[dict]:
    """start(포함)부터 오늘까지. bizdate 앞쪽으로 60일씩 거꾸로 받는다."""
    biz = (date.today() + timedelta(days=1)).strftime("%Y%m%d")
    start8 = start.replace("-", "")
    out, seen = [], set()
    for _ in range(40):
        try:
            rows = requests.get(f"https://m.stock.naver.com/api/stock/{code}/trend",
                                params={"pageSize": PAGE, "bizdate": biz}, headers=H, timeout=15).json()
        except Exception:
            break
        if not rows:
            break
        for r in rows:
            d = r.get("bizdate", "")
            if d < start8 or d in seen:
                continue
            seen.add(d)
            out.append({"날짜": f"{d[:4]}-{d[4:6]}-{d[6:]}", "외국인": _num(r.get("foreignerPureBuyQuant")),
                        "기관": _num(r.get("organPureBuyQuant")), "개인": _num(r.get("individualPureBuyQuant")),
                        "종가": _num(r.get("closePrice")), "거래량": _num(r.get("accumulatedTradingVolume")),
                        "외국인보유율": _num(r.get("foreignerHoldRatio"))})
        last = rows[-1].get("bizdate", "")
        if not last or last <= start8 or last >= biz:
            break
        biz = last
        time.sleep(0.2)
    return out


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    start = next((a for a in sys.argv[1:] if len(a) == 10 and a[4] == "-"), "2024-10-01")
    wl = pd.read_csv(NEW1 / "watchlist.csv", dtype=str)
    OUT.mkdir(exist_ok=True)
    rows, miss = [], []
    for code, name in zip(wl["종목코드"], wl["종목명"]):
        t = trend(code, start)
        if not t:
            miss.append(name)
        rows += [{"종목코드": code, "종목명": name, **r} for r in t]
    df = pd.DataFrame(rows, columns=["날짜", "종목코드", "종목명", "외국인", "기관", "개인", "종가", "거래량", "외국인보유율"])
    for k in ("외국인", "기관", "개인"):
        df[f"{k}_금액근사"] = df[k] * df["종가"]
    df = df.sort_values(["종목코드", "날짜"])
    df.to_csv(OUT / "investor_long.csv", index=False, encoding="utf-8-sig")
    print(f"investor_long.csv {len(df):,}행 · {df['종목코드'].nunique()}종목 · {df['날짜'].min()} ~ {df['날짜'].max()} · 실패 {miss}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
