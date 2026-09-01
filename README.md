# Japan M&A Deal Radar

일본 M&A 안건의 수집·평가·파이프라인 관리 도구.

수집한 안건을 정규화해 배수를 계산하고, 업종별 확인 항목을 붙여 파이프라인으로 관리합니다.
JFC(일본정책금융공고) 공개 데이터는 자동으로 수집됩니다.

---

## 파일

| 파일 | 역할 |
|---|---|
| `Japan_MA_Deal_Radar.html` | 본체. 내려받아 브라우저로 열면 실행됩니다 |
| `collect_jfc.py` | JFC 공개 CSV 수집기 |
| `.github/workflows/collect.yml` | 매일 아침 8시(JST) 자동 실행 |
| `seen.json` | 이미 수집한 안건 ID. 자동 갱신됩니다 |
| `.gitignore` | 백업 파일이 실수로 올라가는 것을 차단 |

---

## 중요 — 이 저장소에 넣지 말 것

이 저장소는 public입니다. 링크를 공유하지 않아도 누구나 접근할 수 있습니다.

**넣어도 되는 것**
`collect_jfc.py`, 워크플로, README, `seen.json`
(seen.json은 JFC 안건 ID 목록일 뿐이고 원본이 이미 공개 데이터입니다)

**절대 넣지 말 것**
Deal Radar 백업 JSON (`ma_radar_*.json`). PASS 사유, 역량 등급, 메모, 실명, IM 내용이 들어갑니다.
`.gitignore`가 막고 있지만, `git add -f`로 강제 추가하지 마십시오.

백업은 로컬 또는 개인 클라우드에 보관하십시오.

---

## 사용법

### 1. 본체 실행

`Japan_MA_Deal_Radar.html`을 내려받아 더블클릭하면 브라우저에서 열립니다.
설치도 서버도 필요 없고, 외부로 나가는 통신이 없습니다.

데이터는 브라우저에 저장되지만 캐시를 지우면 사라집니다.
**하루 작업이 끝나면 좌측 하단 [백업 내보내기]를 누르는 습관을 들이십시오.**

### 2. 안건 넣기

**목록 일괄** — 플랫폼 검색 결과 페이지를 Ctrl+A → Ctrl+C 하고 붙여넣으면 20~30건이 한 번에 들어옵니다. 중복은 자동으로 표시됩니다.

**한 건씩** — 개별 안건 본문을 붙여넣습니다.

**수집 파일 병합** — `collect_jfc.py`가 만든 JSON을 불러옵니다.

**수집 루트** 탭에 매일·주간·월간 확인할 사이트가 링크로 정리되어 있습니다.

### 3. 수집기 직접 실행

```bash
python3 collect_jfc.py                                  # 기본: 매출 5천만·이익 500만 이상, 법인만
python3 collect_jfc.py --min-rev 10000 --min-profit 500 # 매출 1억엔 이상
python3 collect_jfc.py --industries 建設業,製造業,電気工事業
python3 collect_jfc.py --all                            # 조건 없이 전부
```

파이썬 3.8 이상이면 표준 라이브러리만으로 동작합니다. 설치할 패키지가 없습니다.

---

## 수집 루틴

### 매일 10분 — 신착만

정렬을 **新着順**으로 바꾸고 앞 1~2페이지만 봅니다.

1. [BATONZ 売り案件一覧](https://batonz.jp/sell_cases/)
2. [TRANBI 株式譲渡만](https://www.tranbi.com/buy/list/property/1/)
3. [TRANBI 값 내린 안건](https://www.tranbi.com/buy/list/?type=price_down)

### 주 2~3회 15분 — 중견 안건

메인 트랙 플랫폼 후보는 대부분 여기서 나옵니다.

1. [M&Aキャピタルパートナーズ](https://www.ma-cp.com/deal/) — 調整後EBITDA·ネットキャッシュ까지 공개. 여기부터 보십시오
2. [日本M&Aセンター](https://www.nihon-ma.co.jp/anken/needs_convey.php) — 2,200건대, 전속 안건
3. [ストライク SMART](https://www.strike.co.jp/smart/search/) — 제조·건설·B2B 강함
4. [M&Aサクシード 条件検索](https://www.ma-succeed.jp/buy/search) — 법인 전용

### 월 1회 — 오프마켓

- [事業承継・引継ぎ支援センター](https://shoukei.smrj.go.jp/)
- [中小企業庁 事業承継](https://www.chusho.meti.go.jp/zaimu/shoukei/index.html)
- [relay](https://relay.town/)

### 자동

- [JFC 事業承継マッチング](https://www.jfc.go.jp/n/finance/jigyosyokei/matching/search/) — 워크플로가 매일 아침 처리

---

## 자동 수집이 안 되는 것

BATONZ·TRANBI·Strike·サクシード는 이용규약에서 자동 수집을 금지합니다.
계정 정지는 딜 소싱 채널 자체를 잃는 것이라 감수할 이유가 없습니다.

브라우저 보안 정책(CORS)상 로컬 HTML이 외부 사이트에 직접 접속하는 것도 불가능합니다.

---

## 판단 기준

**트랙 분류**
희망가 1억엔 이상 = 메인 트랙 / 1억엔 미만 = 볼트온 후보 풀

**배수**
현금·차입금이 입력되면 실질 EV 기준으로, 없으면 희망가 기준으로 계산하고 화면에 어느 쪽인지 표시합니다.

**점수** (합계 100점, 미입력 항목은 제외 후 정규화)

| 항목 | 배점 |
|---|---|
| 가격 매력도 | 30 |
| 재무 건전성 | 15 |
| 이익 규모 | 12 |
| 오너 의존도 | 10 |
| Exit 경로 | 10 |
| 체크사이즈 적합 | 8 |
| 설명 가능성 | 8 |
| 내 역량 등급 | 7 |

입력이 절반 미만이면 점수를 표시하지 않습니다. 추정보다 공백이 낫습니다.

**PASS**
사유 입력 없이는 PASS로 옮길 수 없습니다. 6개월 뒤 그 기록이 자산이 됩니다.
