#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Japan M&A Deal Radar — 공개 데이터 수집기 (日本政策金融公庫 事業承継マッチング)

일본정책금융공고가 공개하는 사업승계 매칭 CSV를 내려받아 조건에 맞는 안건만
Deal Radar 가져오기용 JSON으로 변환합니다. 공공기관 공개 데이터이므로 자동 수집에
제약이 없습니다.

사용법:
    python3 collect_jfc.py                      # 기본 조건
    python3 collect_jfc.py --min-rev 10000      # 매출 1억엔 이상
    python3 collect_jfc.py --all                # 조건 없이 전부
    python3 collect_jfc.py --seen seen.json     # 이전에 본 안건 제외

출력:
    jfc_import_YYYYMMDD.json   → Deal Radar의 [수집 파일 병합]으로 불러오기
    seen.json                  → 다음 실행 때 신규 안건만 뽑기 위한 기록

금액 단위는 Deal Radar와 동일하게 万円(만엔) 정수입니다.
"""

import argparse, csv, io, json, os, re, sys, urllib.parse, urllib.request
from datetime import date

CSV_URL = "https://www.jfc.go.jp/n/finance/jigyosyokei/matching/search/companies.csv"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# JFC 업종 → Deal Radar 업종 라이브러리 키
INDUSTRY_MAP = {
    "建設業": "建設業",
    "製造業": "製造業",             # 본문 키워드로 아래에서 더 좁게 재판정
    "情報通信業": "IT・システム開発",
    "運輸業": "運輸業",
    "卸売業": "卸売業",
    "小売業": "小売業",
    "不動産業": "不動産業",
    "飲食店": "飲食店",
    "宿泊業": "宿泊業",
    "医療": "医療",
    "福祉": "福祉",
    "教育･学習支援業": "教育",
    "教育・学習支援業": "教育",
    "理容･美容業": "理容・美容業",
    "その他サービス業": "その他サービス業",
    "その他": "その他",
}

# 본문 키워드로 업종을 더 좁게 판정 (앞쪽 우선)
KEYWORDS = [
    ("医院", "医療"), ("クリニック", "医療"), ("診療所", "医療"), ("歯科", "医療"),
    ("薬局", "医療"), ("介護", "福祉"), ("デイサービス", "福祉"), ("保育", "福祉"),
    ("印刷", "印刷業"), ("運送", "運輸業"), ("物流", "運輸業"),
    ("電気工事", "電気工事業"), ("電気設備", "電気工事業"),
    ("産業用ロボット", "ロボットSIer・産業機械"), ("半導体製造装置", "ロボットSIer・産業機械"),
    ("半導体", "ロボットSIer・産業機械"), ("産業機械", "ロボットSIer・産業機械"),
    ("自動化装置", "ロボットSIer・産業機械"), ("省力化機械", "ロボットSIer・産業機械"),
    ("工作機械", "ロボットSIer・産業機械"), ("FA機器", "ロボットSIer・産業機械"),
    ("食品", "食品製造"), ("惣菜", "食品製造"), ("菓子", "食品製造"),
    ("発酵", "食品製造"), ("醸造", "食品製造"),
    ("システム開発", "IT・システム開発"), ("ソフトウェア", "IT・システム開発"),
    ("ホームページ", "IT・システム開発"), ("アプリ", "IT・システム開発"),
    ("人材派遣", "人材派遣・紹介"), ("職業紹介", "人材派遣・紹介"),
    ("学習塾", "教育"), ("スクール", "教育"),
    ("注文住宅", "建設業"), ("工務店", "建設業"), ("土木", "建設業"),
]


# ── 일본어 금액 표기 → 万円 정수 ──────────────────────────────
def _one(tok):
    """'3千万円' '5百万円' '1億円' '1,000万円' '2千万' → 万円 정수"""
    if not tok:
        return None
    t = tok.strip().replace(",", "").replace(" ", "")
    t = t.replace("１", "1").replace("２", "2").replace("３", "3").replace("４", "4") \
         .replace("５", "5").replace("６", "6").replace("７", "7").replace("８", "8") \
         .replace("９", "9").replace("０", "0")
    m = re.search(r"([\d.]+)億", t)
    if m:
        base = float(m.group(1)) * 10000
        m2 = re.search(r"億([\d.]+)千万", t)
        if m2:
            base += float(m2.group(1)) * 1000
        return int(round(base))
    m = re.search(r"([\d.]+)千万", t)
    if m:
        return int(round(float(m.group(1)) * 1000))
    m = re.search(r"([\d.]+)百万", t)
    if m:
        return int(round(float(m.group(1)) * 100))
    m = re.search(r"([\d.]+)万", t)
    if m:
        return int(round(float(m.group(1))))
    m = re.search(r"^([\d.]+)$", t)
    if m:
        return int(round(float(m.group(1))))
    return None


def yen(s):
    """레인지 표기는 중앙값. '非公開' '-' '応相談' '赤字' 등은 None."""
    if not s:
        return None
    s = s.strip()
    if s in ("-", "非公開", "応相談", "", "赤字", "債務超過"):
        return None
    if "未満" in s:
        v = _one(s.replace("未満", ""))
        return int(v * 0.6) if v else None
    if "以上" in s:
        v = _one(s.replace("以上", ""))
        return int(v * 1.3) if v else None
    parts = re.split(r"[~～〜]", s)
    if len(parts) == 2:
        # '0～1百万円' 처럼 앞쪽에 단위가 생략된 경우 뒤쪽 단위를 빌려온다
        unit = ""
        for u in ("億", "千万", "百万", "万"):
            if u in parts[1]:
                unit = u
                break
        a = _one(parts[0] if re.search(r"[億万]", parts[0]) else parts[0] + unit)
        b = _one(parts[1])
        if a is not None and b is not None:
            return int(round((a + b) / 2))
        return b if b is not None else a
    return _one(s)


def emp(s):
    if not s or s in ("非公開", "-"):
        return None
    n = re.findall(r"(\d+)", s.replace(",", ""))
    if not n:
        return None
    if len(n) >= 2:
        return int((int(n[0]) + int(n[1])) / 2)
    return int(n[0])


def years(s):
    if not s or s in ("非公開", "-"):
        return None
    n = re.findall(r"(\d+)", s)
    return int(n[0]) if n else None


def industry_of(row):
    blob = " ".join([row.get("タイトル", ""), row.get("事業内容", ""),
                     row.get("商品・サービスの特徴", "")])
    for kw, ind in KEYWORDS:
        if kw in blob:
            return ind
    return INDUSTRY_MAP.get(row.get("業種", "").strip(), row.get("業種", "").strip())


def convert(row):
    profit = yen(row.get("経常利益", ""))
    na_raw = (row.get("純資産※法人企業のみ") or "").strip()
    d = {
        "name": (row.get("タイトル") or "").strip()[:70],
        "industry": industry_of(row),
        "pref": (row.get("都道府県") or "").strip(),
        "source": "JFC",
        "listingId": (row.get("ＩＤ") or "").strip(),
        "dealType": {"事業譲渡": "事業譲渡", "株式譲渡": "株式譲渡"}.get(
            (row.get("譲渡スキーム") or "").strip(), ""),
        "rev": yen(row.get("売上", "")),
        "op": profit,
        "ebitda": None,
        "ask": yen(row.get("譲渡金額", "")),
        "cash": None,
        "debt": yen(row.get("借入金額※法人企業のみ", "")),
        "netAssets": yen(row.get("純資産※法人企業のみ", "")),
        "emp": emp(row.get("従業員数", "")),
        "reason": (row.get("譲渡理由") or "").strip().replace("-", "") or "미확인",
        "hold": 5,
        "url": ("https://www.jfc.go.jp/n/finance/jigyosyokei/matching/search/?prefecture="
                + urllib.parse.quote((row.get("都道府県") or "").strip())),
        "ownerDep": "", "exitPath": "", "explain": "", "cap": "",
        "flags": [],
        "_years": years(row.get("業歴", "")),
        "_corp": (row.get("法人個人") or "").strip(),
        "_posted": (row.get("掲載日") or "").strip(),
        "_updated": (row.get("更新日") or "").strip(),
        "_open": "交渉可" in (row.get("交渉フラグ") or ""),
        "_deficit": (row.get("経常利益") or "").strip() == "赤字",
    }
    if na_raw == "債務超過":
        d["flags"].append("채무초과")
        d["netAssets"] = None
    if d["_deficit"]:
        d["flags"].append("2년 연속 적자")
    def g(k):
        return (row.get(k) or "").replace("\\r\\n", "\n").replace("\\n", "\n").strip()

    raw = "\n".join([
        "【" + g("タイトル") + "】",
        "案件ID: " + g("ＩＤ") + "   " + g("交渉フラグ"),
        "業種: " + g("業種") + " / " + g("都道府県") + " / " + g("法人個人"),
        "業歴: " + g("業歴") + " / 従業員数: " + g("従業員数"),
        "",
        "売上: " + g("売上"),
        "経常利益: " + g("経常利益"),
        "純資産: " + g("純資産※法人企業のみ"),
        "借入金額: " + g("借入金額※法人企業のみ"),
        "譲渡金額: " + g("譲渡金額"),
        "譲渡スキーム: " + g("譲渡スキーム"),
        "主な譲渡対象資産: " + g("主な譲渡対象資産"),
        "交渉対象: " + g("交渉対象"),
        "",
        "【事業内容】",
        g("事業内容"),
        "",
        "【商品・サービスの特徴】",
        g("商品・サービスの特徴"),
        "",
        "【譲渡理由】 " + g("譲渡理由"),
        "【引き継ぎ協力】 " + g("引き継ぎ協力"),
        "【その他】 " + g("その他"),
        "",
        "掲載日 " + g("掲載日") + " / 更新日 " + g("更新日"),
        "出典: 日本政策金融公庫 事業承継マッチング支援 公開データ",
    ])
    d["raw"] = re.sub(r"\n{3,}", "\n\n", raw)
    d["memo"] = ""
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-rev", type=int, default=5000, help="최소 매출 (만엔)")
    ap.add_argument("--min-profit", type=int, default=500, help="최소 경상이익 (만엔)")
    ap.add_argument("--max-ask", type=int, default=200000, help="최대 희망가 (만엔)")
    ap.add_argument("--corp-only", action="store_true", default=True, help="법인만")
    ap.add_argument("--include-individual", action="store_true", help="개인사업자 포함")
    ap.add_argument("--industries", default="", help="쉼표 구분 업종 필터")
    ap.add_argument("--all", action="store_true", help="조건 없이 전부")
    ap.add_argument("--seen", default="seen.json", help="이미 본 안건 ID 기록 파일")
    ap.add_argument("--out", default="", help="출력 파일명")
    a = ap.parse_args()

    req = urllib.request.Request(CSV_URL, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=60).read()
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    print("내려받음: %d건" % len(rows))

    seen = set()
    if os.path.exists(a.seen):
        try:
            seen = set(json.load(open(a.seen, encoding="utf-8")))
        except Exception:
            pass

    inds = [x.strip() for x in a.industries.split(",") if x.strip()]
    out, stat = [], {"적자": 0, "매출미달": 0, "이익미달": 0, "가격초과": 0,
                     "개인사업자": 0, "업종제외": 0, "이미본안건": 0}

    for r in rows:
        d = convert(r)
        if d["listingId"] in seen:
            stat["이미본안건"] += 1
            continue
        if not a.all:
            if d["_deficit"]:
                stat["적자"] += 1; continue
            if not a.include_individual and d["_corp"] != "法人":
                stat["개인사업자"] += 1; continue
            if d["rev"] is None or d["rev"] < a.min_rev:
                stat["매출미달"] += 1; continue
            if d["op"] is None or d["op"] < a.min_profit:
                stat["이익미달"] += 1; continue
            if d["ask"] is not None and d["ask"] > a.max_ask:
                stat["가격초과"] += 1; continue
            if inds and d["industry"] not in inds:
                stat["업종제외"] += 1; continue
        out.append(d)

    out.sort(key=lambda d: (d["ask"] / d["op"]) if (d["ask"] and d["op"]) else 99)

    print("\n조건 적용 결과")
    for k, v in stat.items():
        if v:
            print("  제외 %-8s %5d" % (k, v))
    print("  통과            %5d\n" % len(out))

    for d in out[:15]:
        ratio = ("%.1f배" % (d["ask"] / d["op"])) if (d["ask"] and d["op"]) else "가격 미정"
        print("  %-34s %-10s 매출%7s 이익%6s 희망%7s  %s"
              % (d["name"][:32], d["pref"],
                 d["rev"] or "-", d["op"] or "-", d["ask"] or "応相談", ratio))
    if len(out) > 15:
        print("  ... 외 %d건" % (len(out) - 15))

    fn = a.out or ("jfc_import_%s.json" % date.today().strftime("%Y%m%d"))
    json.dump({"kind": "deal_radar_import", "source": "JFC",
               "collected": date.today().isoformat(), "deals": out},
              open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(sorted(seen | {d["listingId"] for d in out}),
              open(a.seen, "w", encoding="utf-8"), ensure_ascii=False)
    print("\n저장: %s  (%d건)" % (fn, len(out)))
    print("Deal Radar 좌측 [파일 불러오기]로 넣으십시오.")


if __name__ == "__main__":
    main()
