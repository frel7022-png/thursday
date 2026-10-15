"""new1(Orchestra) 코드 위치 찾기 — agent_view·app이 같이 쓴다 (2026-10-15 새러데이).

써스데이의 계산은 new1 함수를 import해서 쓴다(로직 복제 없음). new1이 어디 있는지는 환경마다 다르다.
1. 환경변수 NEW1_PATH
2. 대표 PC: C:/Users/frel/Desktop/new1
3. 레포 안 .new1/ (Streamlit Cloud 등에서 한 번 받아 둔 사본)
4. 없으면 github.com/frel7022-png/orchestra(public)를 .new1/로 얕게 clone (Streamlit Cloud 첫 실행)
찾으면 sys.path 맨 앞에 넣고 경로를 돌려준다. new1 파일은 읽기만 한다.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ORCHESTRA = "https://github.com/frel7022-png/orchestra.git"


def find_new1() -> Path:
    cands = [os.environ.get("NEW1_PATH"), r"C:\Users\frel\Desktop\new1", str(REPO / ".new1")]
    for c in cands:
        if c and (Path(c) / "portfolio_core.py").exists():
            p = Path(c)
            break
    else:
        p = REPO / ".new1"
        subprocess.run(["git", "clone", "--depth", "1", ORCHESTRA, str(p)], check=True, capture_output=True)
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
    return p
