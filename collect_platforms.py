#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Japan M&A Deal Radar — 공개 안건 페이지 수집기

로그인 없이 공개된 M&A 중개사 안건 목록 페이지를 수집합니다.
각 사이트의 robots.txt를 준수하며, 요청 간격을 두고 하루 1회만 접근합니다.

수집 대상 (전부 비로그인 공개 페이지, robots.txt 허용 확인 완료 2026-09-01)
  ma-cp      M&Aキャピタルパートナーズ   조정후EBITDA·순현금까지 공개, 안건별 상세 URL 제공
  nihon-ma   日本M&Aセンター            2,200건대, 전속 안건 중심
  strike     ストライク SMART           제조·건설·B2B 강함

수집하지 않는 곳
  BATONZ / TRANBI — 회원 로그인 뒤에 재무 정보가 있어 자동 수집 대상이 아닙니다.
                    도구의 [목록 일괄] 붙여넣기를 쓰십시오.

사용법
  python3 collect_platforms.py                       # 전부, 각 3페이지
  python3 collect_platforms.py --sites ma-cp --pages 5
  python3 collect_platforms.py --min-profit 3000     # 영업이익 3천만엔 이상만

출력
  platforms_import_YYYYMMDD.json   → Deal Radar 좌측 [파일 불러오기]
  seen_platforms.json              → 다음 실행 때 신규만 뽑기 위한 기록

금액 단위는 Deal Radar와 동일하게 万円(만엔) 정수입니다.
"""

import argparse, html, json, os, re, sys, time, urllib.request
from datetime import date

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
DELAY = 3.0          # 요청 간격(초). 서버에 부담을 주지 않기 위한 최소 예의
TIMEOUT = 45

SITES = {
    "ma-cp": {
        "label": "M&Aキャピタルパートナーズ",
        "url": "https://www.ma-cp.com/deal/?p={p}",
        "base": "https://www.ma-cp.com",
    },
    "nihon-ma": {
        "label": "日本M&Aセンター",
        "url": "https://www.nihon-ma.co.jp/anken/needs_convey.php?p={p}",
        "base": "https://www.nihon-ma.co.jp",
    },
    "strike": {
        "label": "ストライク SMART",
        "url": "https://www.strike.co.jp/smart/search/",
        "base": "https://www.strike.co.jp",
        "single": True,   # 한 페이지에 전 건이 실림
    },
    "batonz": {
        "label": "BATONZ",
        "url": "https://batonz.jp/sell_cases/?sort=new&page={p}",
        "base": "https://batonz.jp",
    },
    "tranbi": {
        "label": "TRANBI",
        "url": "https://www.tranbi.com/buy/list/?page={p}",
        "base": "https://www.tranbi.com",
    },
}

REGIONS = ["中部・北陸", "中国・四国", "九州・沖縄", "甲信越", "北海道", "東北", "関東",
           "東海", "近畿", "関西", "北陸", "中部", "中国", "四国", "九州", "沖縄"]
PREFS = ["北海道","青森県","岩手県","宮城県","秋田県","山形県","福島県","茨城県","栃木県","群馬県",
         "埼玉県","千葉県","東京都","神奈川県","新潟県","富山県","石川県","福井県","山梨県","長野県",
         "岐阜県","静岡県","愛知県","三重県","滋賀県","京都府","大阪府","兵庫県","奈良県","和歌山県",
         "鳥取県","島根県","岡山県","広島県","山口県","徳島県","香川県","愛媛県","高知県","福岡県",
         "佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県","沖縄県"]

KEYWORDS = [
    ("医院", "医療"), ("クリニック", "医療"), ("診療所", "医療"), ("歯科", "医療"), ("薬局", "医療"),
    ("介護", "福祉"), ("デイサービス", "福祉"), ("保育", "福祉"),
    ("電気工事", "電気工事業"), ("電気設備", "電気工事業"),
    ("産業用ロボット", "ロボットSIer・産業機械"), ("半導体製造装置", "ロボットSIer・産業機械"),
    ("半導体", "ロボットSIer・産業機械"), ("産業機械", "ロボットSIer・産業機械"),
    ("工作機械", "ロボットSIer・産業機械"), ("FA機器", "ロボットSIer・産業機械"),
    ("印刷", "印刷業"), ("運送", "運輸業"), ("物流", "運輸業"),
    ("建設", "建設業"), ("工務店", "建設業"), ("土木", "建設業"), ("注文住宅", "建設業"),
    ("配管工事", "設備工事業"), ("空調", "設備工事業"), ("給排水", "設備工事業"),
    ("食品", "食品製造"), ("惣菜", "食品製造"), ("菓子", "食品製造"), ("漬物", "食品製造"),
    ("システム開発", "IT・システム開発"), ("ソフトウェア", "IT・システム開発"),
    ("SES", "IT・システム開発"), ("受託開発", "IT・システム開発"), ("Web", "IT・システム開発"),
    ("人材派遣", "人材派遣・紹介"), ("職業紹介", "人材派遣・紹介"),
    ("学習塾", "教育"), ("スクール", "教育"), ("専門学校", "教育"), ("日本語学校", "教育"),
    ("板金", "金属加工"), ("精密", "金属加工"), ("金属", "金属加工"),
]


# ── 금액 파싱 (万円 단위 정수) ─────────────────────────────
def z2h(s):
    return (s.translate(str.maketrans("０１２３４５６７８９，～〜ー―", "0123456789,~~~~")))


def _one(tok, unit_hint=""):
    if not tok:
        return None
    t = z2h(tok).replace(",", "").replace(" ", "")
    t = re.sub(r"約|およそ|概算|[（(].*?[)）]", "", t)
    neg = bool(re.match(r"^[▲△\-−]", t))
    t = re.sub(r"^[▲△\-−]", "", t)
    v = None
    for pat, mul in ((r"([\d.]+)億([\d.]+)千万", None), (r"([\d.]+)億([\d.]+)万", None),
                     (r"([\d.]+)億", 10000), (r"([\d.]+)千万", 1000),
                     (r"([\d.]+)百万", 100), (r"([\d.]+)万", 1)):
        m = re.search(pat, t)
        if not m:
            continue
        if mul is None:
            v = float(m.group(1)) * 10000 + float(m.group(2)) * (1000 if "千万" in pat else 1)
        else:
            v = float(m.group(1)) * mul
        break
    if v is None:
        m = re.search(r"([\d.]+)円", t)
        if m:
            v = float(m.group(1)) / 10000
    if v is None:
        m = re.match(r"^([\d.]+)$", t)
        if m:
            base = {"億": 10000, "千万": 1000, "百万": 100, "万": 1}.get(unit_hint, 1)
            v = float(m.group(1)) * base
    if v is None:
        return None
    if re.search(r"未満|以下", t):
        v *= 0.75
    if re.search(r"以上|超", t):
        v *= 1.25
    return int(round(-v if neg else v))


def yen(s, unit_hint=""):
    if not s:
        return None
    s = z2h(s).strip()
    if re.match(r"^(非公開|応相談|要相談|-+|—|―)$", s.replace(" ", "")):
        return None
    parts = re.split(r"~|から", s)
    if len(parts) >= 2:
        unit = ""
        for u in ("億", "千万", "百万", "万"):
            if u in parts[1]:
                unit = u
                break
        a = _one(parts[0] if re.search(r"[億万円]", parts[0]) else parts[0] + unit, unit_hint)
        b = _one(parts[1], unit_hint)
        if a is not None and b is not None:
            return int(round((a + b) / 2))
        return b if b is not None else a
    return _one(s, unit_hint)


def grab(text, keys, unit_hint=""):
    for k in keys:
        m = re.search(k + r"[^0-9▲△]{0,14}([▲△]?[0-9,.]+\s*[億万百千円]{0,3}(?:\s*~\s*[0-9,.]+\s*[億万百千円]{0,3})?[^\n]{0,12})", text)
        if m:
            return m.group(1)
    return None


def clean_html(x):
    x = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", x, flags=re.S)
    x = re.sub(r"<br\s*/?>", "\n", x)
    x = re.sub(r"</(div|p|li|dd|dt|h\d|tr|td|th|section|article|span)>", "\n", x)
    x = re.sub(r"<[^>]+>", " ", x)
    x = html.unescape(x)
    x = re.sub(r"[ \t\u3000]+", " ", x)
    return "\n".join(l.strip() for l in x.split("\n") if l.strip())


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "ja,en;q=0.8"})
    return urllib.request.urlopen(req, timeout=TIMEOUT).read().decode("utf-8", "replace")


# ── 사이트별 블록 분리 ────────────────────────────────────
def strip_partial(x):
    """블록 앞머리에 잘려 들어온 태그 조각을 제거"""
    i = x.find(">")
    return x[i + 1:] if 0 <= i < 200 else x


def blocks_macp(raw):
    """각 안건은 본문 뒤에 案件No가 붙는 구조. 番号까지가 한 블록."""
    out, prev = [], 0
    for m in re.finditer(r"案件No[：:\s]*([A-Za-z0-9\-]+)", raw):
        out.append(strip_partial(raw[prev:m.end()]))
        prev = m.end()
    return out


def blocks_nihonma(raw):
    parts = re.split(r'<[^>]*class="[^"]*E02-004-02-anken__inner', raw)
    return [strip_partial(x) for x in parts[1:]]


def blocks_strike(raw):
    parts = re.split(r'<[^>]*class="smart-industry-card"', raw)
    return [strip_partial(x) for x in parts[1:]]


def blocks_batonz(raw):
    """카드는 /sell_cases/{id} 앵커로 시작한다."""
    pos = [m.start() for m in re.finditer(r'href="/sell_cases/\d+"', raw)]
    out = []
    for i, st in enumerate(pos):
        en = pos[i + 1] if i + 1 < len(pos) else min(len(raw), st + 4000)
        out.append(raw[st:en])
    return out


def blocks_tranbi(raw):
    parts = re.split(r'<[^>]*class="buyListCard"', raw)
    return [strip_partial(x) for x in parts[1:]]


SPLIT = {"ma-cp": blocks_macp, "nihon-ma": blocks_nihonma, "strike": blocks_strike,
         "batonz": blocks_batonz, "tranbi": blocks_tranbi}


def industry_of(t):
    for kw, ind in KEYWORDS:
        if kw in t:
            return ind
    return ""


def title_of(t, site):
    lines = [l for l in t.split("\n") if l.strip()]
    skip = re.compile(r"^(お問い合わせ|詳細|続き|検索|一覧|もっと|NEW|新着|会員|ログイン|前へ|次へ|"
                      r"お気に入り|無料|相談|閲覧|交渉|公開日|更新日|案件No|所在地|スキーム|営業利益|"
                      r"従業員|概算売上|売上高|希望金額|純資産|譲渡理由|業種|財務内容|事業内容|"
                      r"ブックマーク|地域|規模|エリア|株式譲渡|事業譲渡|非公開|応相談|PL項目|BS項目|"
                      r"譲渡希望額|売却希望価格|会社譲渡|経営資源譲渡|専門家|お気に入り|気になる|興味ない|"
                      r"詳しく見る|値下げ|個人（|NEW|公開|更新)")
    cands = []
    for l in lines:
        l = re.sub(r"^[\s・|#*>◎■●\-]+", "", l)
        l = re.sub(r"^[【\[]([^】\]]{1,12})[】\]]\s*", "", l).strip()
        if len(l) < 3 or len(l) > 80:
            continue
        if skip.match(l) or re.match(r"^(SS|B-)\d", l):
            continue
        if re.match(r"^[▲△]?[\d,.]+\s*[億万百千]?円", l) or re.match(r"^[\d,.\s億万百千円~名人-]+$", l):
            continue
        if re.match(r"^\d+\s*(名|人)", l) or re.search(r"^\d+名(未満|以上|~)", l):
            continue
        if re.match(r"^(直近期|前期|今期|\d{4}[/年])", l):
            continue
        if re.search(r"[：:]\s*[▲△約]?\d", l):
            continue
        cands.append(l)
        if len(cands) >= (8 if site in ("batonz", "tranbi") else 3):
            break
    cands = [c for c in cands if c not in PREFS and c not in REGIONS]
    if not cands:
        return "무제"
    if site in ("batonz", "tranbi"):
        # 이 두 곳은 카드에 긴 설명형 제목이 그대로 들어 있다
        return max(cands, key=len)[:70]
    # 첫 줄은 업종 대분류인 경우가 많아, 두 번째 줄이 더 구체적인 사업명
    return (cands[1] if len(cands) > 1 and len(cands[0]) < 30 else cands[0])[:70]


def parse_block(rawhtml, site, cfg):
    t = clean_html(rawhtml)
    if len(t) < 60:
        return None

    d = {"source": cfg["label"], "flags": [], "hold": 5, "memo": "",
         "ownerDep": "", "exitPath": "", "explain": "", "cap": ""}

    # 안건번호 + 상세 URL
    no, url = "", ""
    m = re.search(r"案件No[：:\s]*([A-Za-z0-9\-]+)", t)
    if m:
        no = m.group(1)
    if not no:
        m = re.search(r"\b(SS\d{5,})\b", t)
        if m:
            no = m.group(1)
    if not no:
        m = re.search(r'class="ankenid"[^>]*>\s*([^<]+)', rawhtml)
        if m:
            no = m.group(1).strip()
    if site == "batonz":
        m2 = re.search(r'href="/sell_cases/(\d+)"', rawhtml)
        if m2:
            no = m2.group(1)
            url = cfg["base"] + "/sell_cases/" + no
    if site == "tranbi" and not no:
        m2 = re.search(r"公開日[：:\s]*([\d-]+)", t)
        no = "TB-" + (m2.group(1) if m2 else "") + "-" + str(abs(hash(t)) % 100000)
        url = cfg["base"] + "/buy/list/"
    if no and site == "ma-cp":
        url = cfg["base"] + "/deal/" + no + "/"
    elif no and site == "strike":
        url = cfg["base"] + "/smart/search/?keyword=" + no
    elif no and site == "nihon-ma":
        url = cfg["base"] + "/anken/needs_convey.php?keyword=" + no
    d["listingId"] = no
    d["url"] = url or cfg["url"].format(p=1)

    # 百万円 표 형식이면 단위 힌트
    hint = "百万" if re.search(r"[（(]百万円[)）]", t) else ""

    d["rev"] = yen(grab(t, ["概算売上", "売上高", "年商", "売上"], hint) or "", hint)
    d["op"] = yen(grab(t, ["調整後営業利益", "修正後営業利益", "営業利益"], hint) or "", hint)
    d["ebitda"] = yen(grab(t, ["調整後EBITDA", "修正後EBITDA", "調整後EVITDA", "EBITDA"], hint) or "", hint)
    d["ask"] = yen(grab(t, ["譲渡希望額", "譲渡希望価格", "売却希望価格", "希望譲渡価格", "希望金額", "譲渡価格", "希望価格", "譲渡対価"], hint) or "", hint)
    d["cash"] = yen(grab(t, ["現金及び現金同等物", "現金・現金同等物", "現金・預金等", "現金同等物", "現預金"], hint) or "", hint)
    d["debt"] = yen(grab(t, ["ネット有利子負債", "有利子負債等", "有利子負債", "借入金"], hint) or "", hint)
    d["netAssets"] = yen(grab(t, ["調整後純資産", "修正後時価純資産", "想定時価純資産", "簿価純資産", "時価純資産", "純資産"], hint) or "", hint)
    nc = yen(grab(t, ["ネットキャッシュ"], hint) or "", hint)
    if nc is not None and nc > 0 and d["cash"] is None and d["debt"] is None:
        d["cash"], d["debt"] = nc, 0

    m = re.search(r"従業員[^0-9]{0,10}([0-9]+)", z2h(t))
    d["emp"] = int(m.group(1)) if m else None

    d["pref"] = ""
    for p in PREFS:
        if p in t:
            d["pref"] = p
            break
    if not d["pref"]:
        for r in REGIONS:
            if r in t:
                d["pref"] = r
                break

    d["dealType"] = "事業譲渡" if "事業譲渡" in t else ("株式譲渡" if "株式譲渡" in t else "")
    if "後継者" in t:
        d["reason"] = "후계자 부재"
    elif re.search(r"選択と集中|事業再編|カーブアウト", t):
        d["reason"] = "사업 재편"
    elif "成長と発展" in t:
        d["reason"] = "성장·발전"
    elif re.search(r"企業再生|事業再生", t):
        d["reason"] = "기업 재생"
    elif re.search(r"引退|高齢", t):
        d["reason"] = "오너 은퇴"
    else:
        d["reason"] = "미확인"

    if "債務超過" in t or (d["netAssets"] is not None and d["netAssets"] < 0):
        d["flags"].append("채무초과")
    if re.search(r"\b1円\b|一円", z2h(t)):
        d["flags"].append("1엔 매각")

    d["name"] = title_of(t, site)
    d["industry"] = industry_of(t)
    if re.match(r"^(No\.?\d+|SS\d+|B-\d+)$", d["name"]):
        m = re.search(r"(業種|業態)[：:\s]*([^\n]{2,30})", t)
        alt = m.group(2).strip() if m else (d["industry"] or "")
        if alt:
            d["name"] = alt + (" (" + d["name"] + ")")
    # 희망가가 순현금보다 작게 읽힌 건은 배수를 신뢰할 수 없음
    e = d["ebitda"] if d["ebitda"] is not None else d["op"]
    if d["ask"] is not None and e and e > 0 and d["ask"] / e < 1.0:
        if "수치 확인 필요" not in d["flags"]:
            d["flags"].append("수치 확인 필요")
    d["raw"] = t[:1600]

    sanity(d)
    if d["rev"] is None and d["op"] is None and d["ask"] is None:
        return None
    return d


def sanity(d):
    """공개 목록에서 긁은 값은 오독 가능성이 있으므로 명백히 이상한 값은 버린다."""
    CAP = 3000000                      # 300억엔 초과는 이 채널에서 비현실적
    for k in ("rev", "op", "ebitda", "ask", "cash", "debt", "netAssets"):
        v = d.get(k)
        if v is not None and abs(v) > CAP:
            d[k] = None
    # 이익이 매출을 넘을 수 없다
    if d["rev"] is not None:
        for k in ("op", "ebitda"):
            if d[k] is not None and d[k] > d["rev"]:
                d[k] = None
    # 순현금이 희망가를 넘으면 둘 중 하나가 오독 — EV 계산에 쓰지 않는다
    if d["ask"] is not None and (d["cash"] is not None or d["debt"] is not None):
        nc = (d["cash"] or 0) - (d["debt"] or 0)
        if nc >= d["ask"]:
            d["flags"].append("수치 확인 필요")
            d["cash"] = d["debt"] = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", default="ma-cp,nihon-ma,strike,batonz,tranbi")
    ap.add_argument("--pages", type=int, default=3, help="사이트당 수집 페이지 수")
    ap.add_argument("--min-profit", type=int, default=0, help="최소 영업이익/EBITDA (만엔)")
    ap.add_argument("--min-rev", type=int, default=0, help="최소 매출 (만엔)")
    ap.add_argument("--max-ask", type=int, default=0, help="최대 희망가 (만엔, 0=제한없음)")
    ap.add_argument("--seen", default="seen_platforms.json")
    ap.add_argument("--full", action="store_true",
                    help="이미 본 안건도 포함한 전체 스냅샷을 출력 (도구가 중복을 걸러냄)")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    seen = set()
    if not a.full and os.path.exists(a.seen):
        try:
            seen = set(json.load(open(a.seen, encoding="utf-8")))
        except Exception:
            pass

    out, stats, run_seen = [], {}, set()
    for key in [x.strip() for x in a.sites.split(",") if x.strip()]:
        cfg = SITES.get(key)
        if not cfg:
            print("알 수 없는 사이트: " + key)
            continue
        got = 0
        pages = 1 if cfg.get("single") else a.pages
        for p in range(1, pages + 1):
            url = cfg["url"].format(p=p)
            try:
                raw = fetch(url)
            except Exception as e:
                print("  %s p%d 실패: %s" % (key, p, e))
                break
            bl = SPLIT[key](raw)
            for b in bl:
                d = parse_block(b, key, cfg)
                if not d:
                    continue
                uid = key + ":" + (d["listingId"] or d["name"])
                if uid in seen:
                    continue
                e = d["ebitda"] if d["ebitda"] is not None else d["op"]
                if a.min_profit and (e is None or e < a.min_profit):
                    continue
                if a.min_rev and (d["rev"] is None or d["rev"] < a.min_rev):
                    continue
                if a.max_ask and d["ask"] is not None and d["ask"] > a.max_ask:
                    continue
                if uid in run_seen:
                    continue
                run_seen.add(uid)
                d["_uid"] = uid
                out.append(d)
                got += 1
            time.sleep(DELAY)
        stats[cfg["label"]] = got
        print("%-28s %3d건" % (cfg["label"], got))

    def ratio(d):
        e = d["ebitda"] if d["ebitda"] is not None else d["op"]
        if not d["ask"] or not e or e <= 0:
            return 99
        ev = d["ask"]
        if d["cash"] is not None or d["debt"] is not None:
            cand = d["ask"] - ((d["cash"] or 0) - (d["debt"] or 0))
            if cand > 0:
                ev = cand
        return ev / e

    out.sort(key=ratio)
    print("\n합계 %d건\n" % len(out))
    for d in out[:15]:
        r = ratio(d)
        print("  %-30s %-8s 매출%8s 이익%7s 희망%8s  %s"
              % (d["name"][:28], d["pref"] or "-", d["rev"] or "-",
                 (d["ebitda"] if d["ebitda"] is not None else d["op"]) or "-",
                 d["ask"] or "応相談", ("%.1f배" % r) if r < 99 else "가격 미정"))
    if len(out) > 15:
        print("  ... 외 %d건" % (len(out) - 15))

    fn = a.out or ("platforms_import_%s.json" % date.today().strftime("%Y%m%d"))
    json.dump({"kind": "deal_radar_import", "source": "platforms",
               "collected": date.today().isoformat(), "deals": out},
              open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(sorted(seen | {d["_uid"] for d in out}),
              open(a.seen, "w", encoding="utf-8"), ensure_ascii=False)
    print("\n저장: %s  (%d건)" % (fn, len(out)))
    print("Deal Radar 좌측 [파일 불러오기]로 넣으십시오.")


if __name__ == "__main__":
    main()
