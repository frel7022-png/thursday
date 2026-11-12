"""_uni_avg: 시작일 직전 종가가 없는 종목도 시작일 이후 첫 종가로 채워 평균에 넣는지 (2026-11-05 대표 승인 수정).
실행: python -I C:/Users/frel/Desktop/Thursday/tests/test_uni_avg.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from agent_view import _uni_avg  # noqa: E402


def test_fill_missing_pre_start():
    ph = pd.DataFrame([
        ("A", "2026-08-18", 100), ("A", "2026-08-19", 100),  # 직전 종가 있음
        ("B", "2026-08-19", 200), ("B", "2026-08-20", 210),  # 시작일부터 시세
        ("C", "2026-08-20", 50),                              # 시작일 다음 날부터 시세
    ], columns=["종목코드", "날짜", "종가"])
    live = {"A": 90, "B": 220, "C": 55}
    avg, n = _uni_avg(ph, live, "2026-08-19", True)
    assert n == 3, n
    want = ((90 / 100 - 1) + (220 / 200 - 1) + (55 / 50 - 1)) / 3 * 100
    assert abs(avg - want) < 1e-9, (avg, want)
    avg2, n2 = _uni_avg(ph, live, "2026-08-19", False)
    assert n2 == 3


if __name__ == "__main__":
    test_fill_missing_pre_start()
    print("ok")
