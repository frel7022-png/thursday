"""관심종목 긴 일봉 + 발행주식수 받기 — 써스데이 1118 요청(대표 지시), 새러데이 작성 2026-10-19.

    python C:/Users/frel/Desktop/Thursday/tools/fetch_long_daily.py [시작일 YYYY-MM-DD] [--shares-only|--daily-only]

출력 (Thursday/data/, 덮어씀 — 다시 돌리면 그날까지로 갱신):
- daily_long.csv : 종목코드,종목명,날짜,시가,고가,저가,종가,거래량,외국인소진율
    출처 네이버 siseJson(api.finance.naver.com, new1 fetch_daily_price_history와 같은 경로, 여기선 열을 다 받음).
    **수정주가 기준**(액면분할 소급 반영 확인: 카카오 2021-04 5:1 분할 전날도 112,000원으로 나옴. 거래량도 분할 비율만큼 소급).
    **거래정지일은 시가·고가·저가·거래량이 0이고 종가만 전날 값**이 들어온다 — 계산 전에 거래량 0 행을 빼야 한다.
    외국인소진율 = 그날 외국인 보유율(%). 순매수는 이 경로에 없다.
- shares.csv : 종목코드,종목명,발행주식수,유동주식비율,조회일
    출처 wisereport(comp.wisereport.co.kr) 기업현황 "발행주식수/유동주식비율". 지금 값 하나(과거 증자·소각은 반영 안 됨).
관심종목 목록 = new1 watchlist.csv. 요청 사이 0.25초 쉰다(비공식 경로).
"""
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import ast
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from new1_locator import find_new1  # noqa: E402

NEW1 = find_new1()
OUT = Path(__file__).resolve().parent.parent / "data"
H = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"}


def daily(code: str, start: str, end: str) -> list[list]:
    url = (f"https://api.finance.naver.com/siseJson.naver?symbol={code}&requestType=1"
           f"&startTime={start.replace('-', '')}&endTime={end.replace('-', '')}&timeframe=day")
    try:
        rows = ast.literal_eval(requests.get(url, headers=H, timeout=15).text.strip())
    except Exception:
        return []
    out = []
    for r in rows[1:]:
        try:
            d = str(r[0])
            out.append([f"{d[:4]}-{d[4:6]}-{d[6:8]}", *r[1:7]])
        except Exception:
            continue
    return out


def shares(code: str):
    try:
        t = requests.get(f"https://comp.wisereport.co.kr/company/c1010001.aspx?cmp_cd={code}", headers=H, timeout=15).text
    except Exception:
        return None, None
    m = re.search(r"발행주식수/유동주식비율.*?([\d,]+)주\s*/\s*([\d.]+)%", re.sub(r"<[^>]+>", " ", t), re.S)
    return (int(m.group(1).replace(",", "")), float(m.group(2))) if m else (None, None)


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = sys.argv[1:]
    today = datetime.now().strftime("%Y-%m-%d")
    start = next((a for a in args if re.fullmatch(r"\d{4}-\d{2}-\d{2}", a)),
                 (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d"))
    wl = pd.read_csv(NEW1 / "watchlist.csv", dtype=str)
    OUT.mkdir(exist_ok=True)
    if "--shares-only" not in args:
        rows, miss = [], []
        for code, name in zip(wl["종목코드"], wl["종목명"]):
            d = daily(code, start, today)
            if not d:
                miss.append(name)
            rows += [[code, name, *x] for x in d]
            time.sleep(0.25)
        df = pd.DataFrame(rows, columns=["종목코드", "종목명", "날짜", "시가", "고가", "저가", "종가", "거래량", "외국인소진율"])
        df.to_csv(OUT / "daily_long.csv", index=False, encoding="utf-8-sig")
        print(f"daily_long.csv {len(df):,}행 · {df['종목코드'].nunique()}종목 · {df['날짜'].min()} ~ {df['날짜'].max()} · 실패 {miss}")
    if "--daily-only" not in args:
        out = []
        for code, name in zip(wl["종목코드"], wl["종목명"]):
            n, f = shares(code)
            out.append([code, name, n, f, today])
            time.sleep(0.25)
        sh = pd.DataFrame(out, columns=["종목코드", "종목명", "발행주식수", "유동주식비율", "조회일"])
        sh.to_csv(OUT / "shares.csv", index=False, encoding="utf-8-sig")
        print(f"shares.csv {sh['발행주식수'].notna().sum()}/{len(sh)} · 실패 {sh.loc[sh['발행주식수'].isna(), '종목명'].tolist()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
