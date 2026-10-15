"""실시간 시세 조회 — 써스데이 체결 가격용, 읽기 전용 (2026-10-15 새러데이 작성).

    python C:/Users/frel/Desktop/Thursday/tools/quote.py 종목명 [종목명 ...]
    python C:/Users/frel/Desktop/Thursday/tools/quote.py 005740 214450

종목명 또는 6자리 종목코드를 받아 지금 가격·전일 대비·누적 거래량을 출력한다.
계산·조회는 new1의 portfolio_core.fetch_quotes()를 import해서 쓴다(로직 복제 없음). 파일을 쓰지 않는다.
종목명 → 코드는 new1의 watchlist.csv·stock_code_cache.csv에서 찾는다(관심종목 = 써스데이 유니버스).
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

NEW1 = Path(r"C:\Users\frel\Desktop\new1")
sys.path.insert(0, str(NEW1))
import portfolio_core as core  # noqa: E402


def name_to_code() -> dict:
    m = {}
    for f in ("stock_code_cache.csv", "watchlist.csv"):
        p = NEW1 / f
        if p.exists():
            df = pd.read_csv(p, dtype=str)
            m.update(dict(zip(df["종목명"], df["종목코드"])))
    return m


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    n2c = name_to_code()
    c2n = {v: k for k, v in n2c.items()}
    pairs = []
    for a in args:
        if len(a) == 6 and a[:5].isdigit():
            pairs.append((c2n.get(a, a), a))
        elif a in n2c:
            pairs.append((a, n2c[a]))
        else:
            print(f"{a}: 관심종목에서 코드를 못 찾음")
    q, errs = core.fetch_quotes([c for _, c in pairs])
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 네이버 실시간 시세")
    for name, code in pairs:
        r = q.get(code)
        if not r or r.get("price") is None:
            print(f"{name}({code}): 시세 없음")
            continue
        print(f"{name}({code}) {r['price']:,.0f}원 · 전일 대비 {r.get('change_pct', 0):+.2f}% · 거래량 {r.get('volume') or 0:,.0f}")
    for e in errs:
        print(f"조회 오류: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
