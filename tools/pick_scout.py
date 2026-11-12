"""정찰병 후보 거름 (내_기준 §6): 08-19 이후 누적 하락 큼 + 최근 잔잔 + 장부에 없던 종목.

사용: python tools/pick_scout.py [profile.csv 경로] [개수]
먼저 `python tools/profile.py --out 스크래치/profile.csv`로 성격표를 만든다.
순위로 사지 않는다(줄세우기 금지). 이 표는 정찰병 자리를 볼 종목을 모으는 눈금일 뿐이다.
2026-11-03 써스데이: 스크래치/pick_1028.py를 도구로 옮김(스크래치 스크립트 실행이 권한에 막혀서).
"""
import csv
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
prof = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "스크래치" / "profile.csv"
n = int(sys.argv[2]) if len(sys.argv) > 2 else 25

held = {r["종목명"] for r in csv.DictReader(open(ROOT / "ledger" / "transactions.csv", encoding="utf-8-sig"))}
rows = list(csv.DictReader(open(prof, encoding="utf-8-sig")))


def f(r, k):
    v = r.get(k)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


out = []
for r in rows:
    if r["종목명"] in held:
        continue
    base = f(r, "시장몫기준%p") + f(r, "섹터몫기준%p") + f(r, "자기몫기준%p")
    s = f(r, "일σ%")
    out.append((base, r["종목명"], r["섹터"], s, f(r, "r1%"), f(r, "r5%"), f(r, "r5%") / (s * 5 ** 0.5),
                r.get("평탄10"), f(r, "시장몫기준%p"), f(r, "섹터몫기준%p"), f(r, "자기몫기준%p"),
                f(r, "최악일비중20"), f(r, "fz5"), f(r, "fz20"), f(r, "초과분위20"), f(r, "초과분위60"), f(r, "초과분위120")))
out = [o for o in out if o[0] == o[0]]
out.sort()
print("기준누적%p 종목 섹터 일σ r1 r5 r5/σ√5 평탄10 시장몫 섹터몫 자기몫 최악일비중20 fz5 fz20 초과분위20 초과분위60 초과분위120")
for o in out[:n]:
    print("%.1f %s %s %.1f %.1f %.1f %.2f %s %.1f %.1f %.1f %.2f %.2f %.2f %.2f %.2f %.2f" % o)
