/* Deal Radar — 안건 담기 (북마클릿)
 *
 * 사용자가 직접 로그인해 열어둔 목록 페이지에서, 화면에 이미 표시된 내용을
 * 구조화해 모읍니다. 페이지를 넘기며 버튼을 누르면 계속 쌓이고,
 * [JSON 저장]을 누르면 Deal Radar 가져오기 형식으로 내려받습니다.
 *
 * 이 스크립트는 스스로 페이지를 넘기거나 다른 주소를 부르지 않습니다.
 * 지금 보고 있는 화면만 읽습니다.
 */
(function () {
  var KEY = 'deal_radar_grab';

  /* ── 금액 파싱 (万円 단위 정수) ── */
  function z2h(s) {
    return String(s).replace(/[０-９]/g, function (c) {
      return String.fromCharCode(c.charCodeAt(0) - 65248);
    }).replace(/，/g, ',').replace(/～|〜|ー|―/g, '~');
  }
  function one(str) {
    if (!str) return null;
    var s = z2h(str).replace(/,/g, '').replace(/\s/g, '').replace(/約|およそ|概算|[（(].*?[)）]/g, '');
    var neg = /^[▲△\-−]/.test(s); s = s.replace(/^[▲△\-−]/, '');
    var v = null, m;
    if (m = s.match(/([\d.]+)億([\d.]+)千万/)) v = parseFloat(m[1]) * 10000 + parseFloat(m[2]) * 1000;
    else if (m = s.match(/([\d.]+)億([\d.]+)万/)) v = parseFloat(m[1]) * 10000 + parseFloat(m[2]);
    else if (m = s.match(/([\d.]+)億/)) v = parseFloat(m[1]) * 10000;
    else if (m = s.match(/([\d.]+)千万/)) v = parseFloat(m[1]) * 1000;
    else if (m = s.match(/([\d.]+)百万/)) v = parseFloat(m[1]) * 100;
    else if (m = s.match(/([\d.]+)万/)) v = parseFloat(m[1]);
    else if (m = s.match(/([\d.]+)円/)) v = parseFloat(m[1]) / 10000;
    else if (m = s.match(/^([\d.]+)$/)) v = parseFloat(m[1]);
    if (v == null) return null;
    if (/未満|以下/.test(s)) v *= 0.75;
    if (/以上|超/.test(s)) v *= 1.25;
    return Math.round(neg ? -v : v);
  }
  function yen(str) {
    if (!str) return null;
    var s = z2h(str);
    if (/非公開|応相談|要相談/.test(s)) return null;
    var p = s.split(/~|から/);
    if (p.length >= 2) {
      var u = '';
      ['億', '千万', '百万', '万'].some(function (x) { if (p[1].indexOf(x) >= 0) { u = x; return true; } });
      var a = one(/[億万円]/.test(p[0]) ? p[0] : p[0] + u), b = one(p[1]);
      if (a != null && b != null) return Math.round((a + b) / 2);
      return b != null ? b : a;
    }
    return one(s);
  }
  function grab(t, keys) {
    for (var i = 0; i < keys.length; i++) {
      var re = new RegExp(keys[i] + '[^0-9０-９▲△]{0,14}([▲△]?[0-9０-９,.]+\\s*[億万百千円]{0,3}(?:\\s*~\\s*[0-9０-９,.]+\\s*[億万百千円]{0,3})?)');
      var m = t.match(re);
      if (m) return m[1];
    }
    return null;
  }

  var PREFS = ('北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|埼玉県|千葉県|東京都|神奈川県|' +
    '新潟県|富山県|石川県|福井県|山梨県|長野県|岐阜県|静岡県|愛知県|三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|' +
    '和歌山県|鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|佐賀県|長崎県|熊本県|大分県|' +
    '宮崎県|鹿児島県|沖縄県').split('|');
  var REGIONS = ['中部・北陸', '中国・四国', '九州・沖縄', '甲信越', '北海道', '東北', '関東', '東海', '近畿', '関西', '北陸', '中部', '中国', '四国', '九州', '沖縄'];
  var SKIP = /^(お問い合わせ|詳しく見る|詳細|続き|検索|一覧|もっと|NEW|新着|会員|ログイン|前へ|次へ|お気に入り|気になる|興味ない|無料|相談|閲覧|交渉|公開|更新|案件No|所在地|スキーム|営業利益|従業員|概算売上|売上高|希望金額|純資産|譲渡理由|業種|財務内容|事業内容|譲渡希望額|売却希望価格|会社譲渡|事業譲渡|経営資源譲渡|専門家|値下げ|個人（|法人（|地域|規模|エリア|非公開|応相談)/;

  function txt(el) {
    return (el.innerText || el.textContent || '')
      .replace(/[\t\u3000]+/g, ' ')
      .split('\n').map(function (l) { return l.trim(); }).filter(Boolean).join('\n');
  }

  /* ── 사이트별 카드 수집 ── */
  function cards() {
    var host = location.hostname, out = [];
    if (/batonz\.jp/.test(host)) {
      var seen = {};
      [].forEach.call(document.querySelectorAll('a[href^="/sell_cases/"]'), function (a) {
        var id = (a.getAttribute('href').match(/\/sell_cases\/(\d+)/) || [])[1];
        if (!id || seen[id]) return;
        var box = a;
        for (var i = 0; i < 7 && box.parentElement; i++) {
          box = box.parentElement;
          if (txt(box).length > 120) break;
        }
        seen[id] = 1;
        out.push({ src: 'BATONZ', id: id, url: 'https://batonz.jp/sell_cases/' + id, t: txt(box) });
      });
    } else if (/tranbi\.com/.test(host)) {
      [].forEach.call(document.querySelectorAll('.buyListCard, [class*="buyListCard"]'), function (c) {
        var t = txt(c);
        if (t.length < 60) return;
        var a = c.querySelector('a[href]');
        var href = a ? a.getAttribute('href') : '';
        var id = (href.match(/(\d{4,})/) || [])[1] || '';
        out.push({
          src: 'TRANBI', id: id ? 'TB' + id : '',
          url: href ? (href.indexOf('http') === 0 ? href : 'https://www.tranbi.com' + href) : location.href,
          t: t
        });
      });
    }
    if (!out.length) {
      /* 알 수 없는 사이트: 상세 페이지 하나로 취급 */
      var body = txt(document.body);
      if (body.length > 150) out.push({ src: location.hostname, id: '', url: location.href, t: body.slice(0, 4000) });
    }
    return out;
  }

  function title(t) {
    var ls = t.split('\n'), c = [];
    for (var i = 0; i < ls.length; i++) {
      var l = ls[i].replace(/^[\s・|#*>◎■●\-]+/, '').replace(/^[【\[]([^】\]]{1,14})[】\]]\s*/, '').trim();
      if (l.length < 4 || l.length > 90) continue;
      if (SKIP.test(l)) continue;
      if (/^[▲△]?[\d,.]+\s*[億万百千]?円/.test(l)) continue;
      if (/^[\d,.\s億万百千円~名人-]+$/.test(l)) continue;
      if (PREFS.indexOf(l) >= 0 || REGIONS.indexOf(l) >= 0) continue;
      c.push(l);
      if (c.length >= 8) break;
    }
    if (!c.length) return '무제';
    return c.sort(function (a, b) { return b.length - a.length; })[0].slice(0, 70);
  }

  function toDeal(c) {
    var t = c.t, d = {
      source: c.src, listingId: c.id, url: c.url, name: title(t),
      rev: yen(grab(t, ['概算売上', '売上高', '年商', '売上'])),
      op: yen(grab(t, ['調整後営業利益', '修正後営業利益', '営業利益'])),
      ebitda: yen(grab(t, ['調整後EBITDA', '修正後EBITDA', 'EBITDA', '償却前利益'])),
      ask: yen(grab(t, ['譲渡希望額', '売却希望価格', '譲渡希望価格', '希望金額', '希望価格', '譲渡価格'])),
      cash: yen(grab(t, ['現金・預金等', '現預金', '現金同等物'])),
      debt: yen(grab(t, ['有利子負債等', '有利子負債', '借入金'])),
      netAssets: yen(grab(t, ['調整後純資産', '時価純資産', '簿価純資産', '純資産'])),
      emp: null, pref: '', industry: '', dealType: '', reason: '미확인',
      flags: [], hold: 5, memo: '', ownerDep: '', exitPath: '', explain: '', cap: '',
      raw: t.slice(0, 2000)
    };
    var em = z2h(t).match(/従業員[^0-9]{0,10}([0-9]+)/); if (em) d.emp = parseInt(em[1]);
    function nd(x) {
      if (!x) return '';
      var m = String(x).match(/(\d{4})\s*[\/\-年.]\s*(\d{1,2})\s*[\/\-月.]\s*(\d{1,2})/);
      if (!m) return '';
      return m[1] + '-' + ('0' + m[2]).slice(-2) + '-' + ('0' + m[3]).slice(-2);
    }
    var mp = t.match(/(?:公開日?|掲載日?)\s*[：:]?\s*(\d{4}[\/\-年.]\d{1,2}[\/\-月.]\d{1,2})/);
    var mu = t.match(/(?:更新日?|最終更新)\s*[：:]?\s*(\d{4}[\/\-年.]\d{1,2}[\/\-月.]\d{1,2})/);
    d.posted = mp ? nd(mp[1]) : '';
    d.updated = mu ? nd(mu[1]) : '';
    for (var i = 0; i < PREFS.length; i++) if (t.indexOf(PREFS[i]) >= 0) { d.pref = PREFS[i]; break; }
    if (!d.pref) for (var j = 0; j < REGIONS.length; j++) if (t.indexOf(REGIONS[j]) >= 0) { d.pref = REGIONS[j]; break; }
    d.dealType = t.indexOf('事業譲渡') >= 0 ? '事業譲渡' : (t.indexOf('株式譲渡') >= 0 || t.indexOf('会社譲渡') >= 0 ? '株式譲渡' : '');
    if (/後継者/.test(t)) d.reason = '후계자 부재';
    else if (/選択と集中|事業再編/.test(t)) d.reason = '사업 재편';
    else if (/引退|高齢/.test(t)) d.reason = '오너 은퇴';
    if (/債務超過/.test(t) || (d.netAssets != null && d.netAssets < 0)) d.flags.push('채무초과');
    if (d.rev != null && d.op != null && d.op > d.rev) d.op = null;
    ['rev', 'op', 'ebitda', 'ask', 'cash', 'debt'].forEach(function (k) {
      if (d[k] === 0) d[k] = null;                 /* 0은 미공개 표기의 오독 */
      if (d[k] != null && Math.abs(d[k]) > 3000000) d[k] = null;
    });
    if (d.ask != null && (d.cash != null || d.debt != null)) {
      var nc = (d.cash || 0) - (d.debt || 0);
      if (nc >= d.ask) { d.flags.push('수치 확인 필요'); d.cash = d.debt = null; }
    }
    return d;
  }

  /* ── 누적 저장 ── */
  function load() { try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch (e) { return []; } }
  function store(a) { try { localStorage.setItem(KEY, JSON.stringify(a)); } catch (e) { } }

  var pool = load(), have = {};
  pool.forEach(function (d) { have[d.source + ':' + (d.listingId || d.name)] = 1; });
  var got = cards().map(toDeal), added = 0;
  got.forEach(function (d) {
    var k = d.source + ':' + (d.listingId || d.name);
    if (have[k]) return;
    have[k] = 1; pool.push(d); added++;
  });
  store(pool);

  /* ── 화면 표시 ── */
  var old = document.getElementById('dr-grab-box'); if (old) old.remove();
  var box = document.createElement('div');
  box.id = 'dr-grab-box';
  box.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;background:#0A1628;color:#E6EDF5;' +
    'border:1px solid #1E3A57;border-radius:10px;padding:14px 16px;font:13px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif;' +
    'box-shadow:0 8px 28px rgba(0,0,0,.45);min-width:250px';
  box.innerHTML =
    '<div style="font-weight:600;margin-bottom:6px">Deal Radar 담기</div>' +
    '<div style="color:#9DB2C9">이 페이지에서 <b style="color:#00D9FF">' + added + '</b>건 추가' +
    (got.length - added > 0 ? ' <span style="color:#647D99">(중복 ' + (got.length - added) + ')</span>' : '') + '</div>' +
    '<div style="color:#9DB2C9;margin-bottom:10px">모은 안건 <b style="color:#00D9FF">' + pool.length + '</b>건</div>' +
    '<div style="display:flex;gap:7px;flex-wrap:wrap">' +
    '<button id="dr-save" style="background:#00D9FF;color:#04222B;border:0;border-radius:6px;padding:7px 12px;font-weight:600;cursor:pointer;font-size:12.5px">JSON 저장</button>' +
    '<button id="dr-clear" style="background:transparent;color:#E4636B;border:1px solid #4A2028;border-radius:6px;padding:7px 12px;cursor:pointer;font-size:12.5px">비우기</button>' +
    '<button id="dr-close" style="background:transparent;color:#9DB2C9;border:1px solid #1E3A57;border-radius:6px;padding:7px 12px;cursor:pointer;font-size:12.5px">닫기</button>' +
    '</div>' +
    '<div style="color:#647D99;font-size:11.5px;margin-top:9px;max-width:250px">페이지를 넘기며 다시 눌러 계속 모으고, 끝나면 JSON 저장 → Deal Radar의 [파일 불러오기]</div>';
  document.body.appendChild(box);

  box.querySelector('#dr-close').onclick = function () { box.remove(); };
  box.querySelector('#dr-clear').onclick = function () {
    if (!confirm('모아둔 ' + pool.length + '건을 비웁니다.')) return;
    store([]); box.remove();
  };
  box.querySelector('#dr-save').onclick = function () {
    var out = { kind: 'deal_radar_import', source: 'bookmarklet', collected: new Date().toISOString().slice(0, 10), deals: pool };
    var blob = new Blob([JSON.stringify(out, null, 1)], { type: 'application/json' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'grab_' + new Date().toISOString().slice(0, 10).replace(/-/g, '') + '.json';
    a.click();
  };
})();
