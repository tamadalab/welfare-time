/**
 * 臨時店舗の JSON を作るフォーム（ヘルプの「臨時店舗の JSON を作る」）。
 *
 * 入力を検証し、掲載を依頼する JSON と、サイトでの表示例を作る。
 * 検証の規則は scripts/generator.py の validate_extra_entry() と揃える。どちらかを変えるときは、
 * もう一方も変える（resources/spec/data.md の「臨時店舗」に規則の一覧がある）。
 * カードの組み立て（buildCardHtml）と、建物の判定（findBuildingByLocation）は main.js のものを使う。
 */
document.addEventListener('DOMContentLoaded', () => {
    const root = document.getElementById('xf');
    if (!root) return;

    const ID_PATTERN = /^[a-z0-9][a-z0-9-]*$/;
    const IMAGE_WIDTH = 1019, IMAGE_HEIGHT = 747;
    const ISSUE_URL = 'https://github.com/tamadalab/welfare-time/issues/new';
    // Issue の URL に載せられる長さには限りがあるため、超えるときは本文を載せない
    const MAX_ISSUE_URL_LENGTH = 7000;
    const BASE_PATH = window.BASE_PATH || '';

    const $ = (id) => document.getElementById(id);
    const els = {
        name: $('xf-name'), id: $('xf-id'), idAuto: $('xf-id-auto'), category: $('xf-category'),
        location: $('xf-location'), locationNote: $('xf-location-note'), buildings: $('xf-buildings'),
        headline: $('xf-headline'), url: $('xf-url'), note: $('xf-note'),
        rows: $('xf-rows'), addRow: $('xf-add-row'),
        status: $('xf-status'), errors: $('xf-errors'), preview: $('xf-preview'),
        viewGrid: $('xf-view-grid'), viewList: $('xf-view-list'),
        mapBox: $('xf-map-box'), mapImg: $('xf-map-img'), mapArea: $('xf-map-area'),
        json: $('xf-json'), copy: $('xf-copy'), copyNote: $('xf-copy-note'), issue: $('xf-issue'),
    };
    let view = 'grid';

    const today = () => new Date().toLocaleDateString('sv-SE');
    const escapeHtml = (s) => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const toMinutes = (hhmm) => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + m; };

    function addDays(dateStr, days) {
        const d = new Date(dateStr + 'T00:00:00');
        d.setDate(d.getDate() + days);
        return d.toLocaleDateString('sv-SE');
    }

    // --- 営業する日の行 ---
    function addRow(date, start, end) {
        const row = document.createElement('div');
        row.className = 'xf-row flex flex-wrap items-center gap-2';
        row.innerHTML = `
            <input type="date" class="xf-input xf-auto xf-date" value="${date}" aria-label="日付">
            <input type="time" class="xf-input xf-auto xf-start" value="${start}" aria-label="開始時刻">
            <span class="text-slate-500">～</span>
            <input type="time" class="xf-input xf-auto xf-end" value="${end}" aria-label="終了時刻">
            <button type="button" class="xf-button xf-remove" aria-label="この日を削除する">削除</button>`;
        els.rows.appendChild(row);
    }

    function readRows() {
        return [...els.rows.querySelectorAll('.xf-row')].map(row => ({
            el: row,
            date: row.querySelector('.xf-date').value,
            start: row.querySelector('.xf-start').value,
            end: row.querySelector('.xf-end').value,
        }));
    }

    // --- 検証 ---
    const hasTag = (s) => /[<>]/.test(s);

    /** 入力を検証して、誤りの一覧を返す。誤りのある入力欄には aria-invalid を付ける。 */
    function validate(v, rows) {
        const errors = [];
        const mark = (el, bad) => el.setAttribute('aria-invalid', bad ? 'true' : 'false');
        const check = (el, bad, message) => { mark(el, bad); if (bad) errors.push(message); };

        check(els.name, !v.name, '店名を入れてください。');
        if (v.name) check(els.name, hasTag(v.name), '店名に < と > は使えません。');
        check(els.id, !ID_PATTERN.test(v.id), 'id は、半角の英小文字・数字・ハイフンだけで、英小文字か数字から書き始めてください。');
        check(els.location, !v.location, '場所を入れてください。');
        if (v.location) check(els.location, hasTag(v.location), '場所に < と > は使えません。');
        check(els.headline, hasTag(v.headline), 'ひとこと紹介に < と > は使えません。');
        check(els.note, hasTag(v.note), '備考に < と > は使えません。');
        check(els.url, v.url && (!/^https?:\/\//.test(v.url) || hasTag(v.url)),
            'URL は http:// または https:// で始め、< と > は使わないでください。');

        if (rows.length === 0) errors.push('営業する日を1つ以上入れてください。');
        const seen = new Set();
        rows.forEach((r, i) => {
            const label = `${i + 1}行目`;
            const bad = (cls, cond, message) => {
                r.el.querySelector(cls).setAttribute('aria-invalid', cond ? 'true' : 'false');
                if (cond) errors.push(`${label}：${message}`);
            };
            bad('.xf-date', !r.date, '日付を入れてください。');
            bad('.xf-start', !r.start, '開始時刻を入れてください。');
            bad('.xf-end', !r.end, '終了時刻を入れてください。');
            if (r.start && r.end) bad('.xf-end', toMinutes(r.start) >= toMinutes(r.end), '終了時刻は開始時刻より後にしてください。');
            if (r.date) {
                bad('.xf-date', seen.has(r.date), `${r.date} が重なっています。`);
                seen.add(r.date);
            }
        });
        return errors;
    }

    // --- JSON ---
    function buildEntries(v, rows) {
        return rows.map(r => {
            const e = { id: v.id, name: v.name, date: r.date, location: v.location, category: v.category };
            if (v.headline) e.headline = v.headline;
            if (v.url) e.url = v.url;
            e.start_time = r.start;
            e.end_time = r.end;
            if (v.note) e.note = v.note;
            return e;
        });
    }

    // --- 表示例 ---
    function renderPreview(v, rows) {
        els.preview.innerHTML = '';
        els.preview.className = view === 'grid' ? 'grid grid-cols-1 sm:grid-cols-2 gap-3' : 'flex flex-col gap-2';
        rows.filter(r => r.date && r.start && r.end).forEach(r => {
            const shop = {
                id: 'preview', temporary: true, category: escapeHtml(v.category),
                name: escapeHtml(v.name || '（店名）'), location: escapeHtml(v.location || '（場所）'),
                headline: escapeHtml(v.headline), note: escapeHtml(v.note),
                url: /^https?:\/\//.test(v.url) ? escapeHtml(v.url) : '',
                start_time: r.start, end_time: r.end,
            };
            const wrapper = document.createElement('div');
            wrapper.innerHTML = `<div class="mb-1 text-[11px] font-bold text-slate-500 dark:text-slate-400">${escapeHtml(r.date)}</div>`
                + buildCardHtml(shop, getShopStatus(r.start, r.end, r.date), view);
            // 同じ id が重ならないよう、表示例のカードからは id を外す
            wrapper.querySelectorAll('[id]').forEach(el => el.removeAttribute('id'));
            els.preview.appendChild(wrapper);
        });
        els.viewGrid.className = 'px-3 py-1 ' + (view === 'grid' ? 'xf-view-on' : 'xf-view-off');
        els.viewList.className = 'px-3 py-1 ' + (view === 'list' ? 'xf-view-on' : 'xf-view-off');
    }

    /** 場所から建物を調べて、メモとマップの表示を更新する。マスターを読み込めていないときは何もしない。 */
    function renderLocation(v) {
        els.mapBox.classList.add('hidden');
        els.locationNote.textContent = '';
        if (typeof master === 'undefined' || !master || !v.location) return;
        const buildingId = findBuildingByLocation(v.location);
        if (buildingId) {
            const b = master.buildings[buildingId];
            els.locationNote.textContent = `✔ ${b.name} と連動します。`;
            els.locationNote.className = 'text-xs font-bold text-emerald-600 dark:text-emerald-400';
            els.mapImg.src = `${BASE_PATH}/assets/campus_map.jpg`;
            const pct = (n, total) => (n / total * 100) + '%';
            Object.assign(els.mapArea.style, {
                left: pct(b.area.x1, IMAGE_WIDTH), top: pct(b.area.y1, IMAGE_HEIGHT),
                width: pct(b.area.x2 - b.area.x1, IMAGE_WIDTH), height: pct(b.area.y2 - b.area.y1, IMAGE_HEIGHT),
            });
            els.mapBox.classList.remove('hidden');
        } else {
            els.locationNote.textContent = '地図上の建物の名前で始まっていないため、「マップ外」として表示されます。学外などの場合は、このままで構いません。';
            els.locationNote.className = 'text-xs font-bold text-amber-600 dark:text-amber-400';
        }
    }

    // --- 全体の更新 ---
    function update() {
        const v = {
            name: els.name.value.trim(), id: els.id.value.trim(), category: els.category.value,
            location: els.location.value.trim(), headline: els.headline.value.trim(),
            url: els.url.value.trim(), note: els.note.value.trim(),
        };
        const rows = readRows();
        const errors = validate(v, rows);

        els.errors.innerHTML = errors.map(e => `<li>${escapeHtml(e)}</li>`).join('');
        els.status.textContent = errors.length === 0 ? '✔ 入力に問題はありません。' : `入力に ${errors.length} 件の問題があります。`;
        els.status.className = 'text-sm font-bold ' + (errors.length === 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400');

        renderLocation(v);
        renderPreview(v, rows);

        const ok = errors.length === 0;
        const json = ok ? JSON.stringify(buildEntries(v, rows), null, 2) : '';
        els.json.value = json || '入力の問題を直すと、ここに JSON が出ます。';
        els.copy.disabled = !ok;
        els.issue.setAttribute('aria-disabled', ok ? 'false' : 'true');

        let href = ISSUE_URL;
        if (ok) {
            const withBody = `${ISSUE_URL}?title=${encodeURIComponent('臨時店舗の掲載依頼：' + v.name)}`
                + `&body=${encodeURIComponent('```json\n' + json + '\n```\n')}`;
            href = withBody.length <= MAX_ISSUE_URL_LENGTH ? withBody : `${ISSUE_URL}?title=${encodeURIComponent('臨時店舗の掲載依頼：' + v.name)}`;
        }
        els.issue.href = href;
    }

    // --- 操作 ---
    const randomId = () => 'shop-' + Math.random().toString(36).slice(2, 8).padEnd(6, '0');

    els.idAuto.addEventListener('click', () => { els.id.value = randomId(); update(); });
    els.addRow.addEventListener('click', () => {
        const rows = readRows();
        const last = rows[rows.length - 1];
        const date = last && last.date ? addDays(last.date, 1) : today();
        addRow(date, last ? last.start : '11:00', last ? last.end : '14:00');
        update();
    });
    els.rows.addEventListener('click', (e) => {
        const button = e.target.closest('.xf-remove');
        if (!button) return;
        button.closest('.xf-row').remove();
        update();
    });
    els.viewGrid.addEventListener('click', () => { view = 'grid'; update(); });
    els.viewList.addEventListener('click', () => { view = 'list'; update(); });
    root.addEventListener('input', update);
    root.addEventListener('change', update);

    els.copy.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(els.json.value);
        } catch (e) {
            els.json.select();
            document.execCommand('copy');
        }
        els.copyNote.textContent = 'コピーしました。Issue に貼り付けてください。';
        setTimeout(() => { els.copyNote.textContent = ''; }, 4000);
    });

    // --- 初期化 ---
    els.id.value = randomId();
    addRow(today(), '11:00', '14:00');
    update();

    // 建物の名前は、サイトが使っているマスターから読む。読めなくてもフォームは使える。
    fetch(`${BASE_PATH}/assets/facilities.json`)
        .then(res => res.ok ? res.json() : null)
        .then(data => {
            if (!data) return;
            master = data;
            els.buildings.innerHTML = Object.values(master.buildings).map(b => `<option value="${escapeHtml(b.name)}"></option>`).join('');
            update();
        })
        .catch(() => {});
});
