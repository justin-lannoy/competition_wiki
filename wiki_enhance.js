// wiki_enhance.js — drop-in DOM augmentation for the redesigned wiki.
// Loaded after wiki_app.js. Watches .md-content for re-renders and:
//  1. Tags SAE H2s with a count chip
//  2. Injects a KPI strip + SAE leaderboard at the top of edition pages
//  3. Adds id="silent-partners-today" to the trailing footer H2

(function () {
  const SAE_H2_RE = /^(.+?)\s*\((\d+)\s*events?\)\s*$/i;

  // Escape values taken from page markdown (event/SAE titles can be web-sourced)
  // before they go into any innerHTML string — the React side sanitizes via
  // DOMPurify, but these vanilla-JS builders bypass that path.
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  function decorateSaeHeadings(root) {
    const h2s = root.querySelectorAll('h2');
    h2s.forEach((h) => {
      if (h.dataset.saeDecorated) return;
      const txt = (h.textContent || '').trim();
      const m = txt.match(SAE_H2_RE);
      if (!m) return;
      const name = m[1];
      const count = m[2];
      h.classList.add('sae-h2');
      h.textContent = '';
      const nameEl = document.createElement('span');
      nameEl.className = 'sae-name';
      nameEl.textContent = name;
      const chip = document.createElement('span');
      chip.className = 'sae-count-chip';
      chip.innerHTML = '<strong>' + count + '</strong>EVENTS';
      h.appendChild(nameEl);
      h.appendChild(chip);
      h.dataset.saeDecorated = '1';
      h.dataset.saeName = name;
      h.dataset.saeCount = count;
    });
  }

  function tagSilentH2(root) {
    root.querySelectorAll('h2').forEach((h) => {
      const t = (h.textContent || '').trim().toLowerCase();
      if (t.startsWith('silent partners')) h.id = 'silent-partners-today';
    });
  }

  function buildLeaderboard(saeRows) {
    if (document.querySelector('.sae-leaderboard')) return;
    if (!saeRows.length) return;
    const max = Math.max.apply(null, saeRows.map(r => r.count));
    const lb = document.createElement('div');
    lb.className = 'sae-leaderboard';
    lb.innerHTML =
      '<div class="lb-head">' +
        '<span class="lb-title">SAE Leaderboard — Events This Window</span>' +
        '<span class="lb-meta">Sorted by event volume · click to jump</span>' +
      '</div>' +
      '<div class="lb-body">' +
        saeRows.map(r => {
          const w = Math.max(4, Math.round((r.count / max) * 100));
          const high = r.high > 0 ? '<span class="lb-high">' + r.high + ' high</span>' : '';
          return '<div class="led-row" data-anchor="' + esc(r.anchor) + '">' +
                   '<div class="led-name">' + esc(r.name) + '</div>' +
                   '<div class="led-bar-wrap"><div class="led-bar' + (r.high > 0 ? ' has-high' : '') + '" style="width:' + w + '%"></div></div>' +
                   '<div class="lb-count">' + r.count + high + '</div>' +
                 '</div>';
        }).join('') +
      '</div>';
    lb.addEventListener('click', (e) => {
      const row = e.target.closest('.led-row');
      if (!row) return;
      const id = row.getAttribute('data-anchor');
      const target = document.getElementById(id);
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
    return lb;
  }

  function isEditionView(main) {
    return !!main.querySelector('.briefing-header');
  }

  function collectSaeRows(root) {
    const rows = [];
    root.querySelectorAll('h2.sae-h2').forEach(h => {
      const name = h.dataset.saeName;
      const count = parseInt(h.dataset.saeCount || '0', 10);
      if (!name) return;
      // count high-impact events under this section: inspect siblings until next H2
      let high = 0;
      let n = h.nextElementSibling;
      while (n && n.tagName !== 'H2') {
        if (n.querySelector) {
          high += n.querySelectorAll('a strong, .pill').length;
          // also catch markdown-emitted "**[High Impact]**" inside a link → bold
          n.querySelectorAll('strong').forEach(s => {
            if (/high\s*impact/i.test(s.textContent)) high++;
          });
        }
        n = n.nextElementSibling;
      }
      // dedupe rough estimate
      if (high > count) high = count;
      rows.push({ name, count, high, anchor: h.id || '' });
    });
    rows.sort((a, b) => b.count - a.count);
    return rows;
  }

  function ensureAnchors(root) {
    root.querySelectorAll('h2.sae-h2').forEach(h => {
      if (h.id) return;
      const slug = (h.dataset.saeName || '')
        .toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-');
      h.id = slug + '-' + (h.dataset.saeCount || '0') + '-events';
    });
  }

  function removeJumpNav() {
    const n = document.querySelector('.jump-nav');
    if (n) n.remove();
  }

  function scrollToAnchor(id) {
    const m = document.querySelector('.main-content');
    const t = id && document.getElementById(id);
    if (!m || !t) return;
    const top = t.getBoundingClientRect().top - m.getBoundingClientRect().top + m.scrollTop - 12;
    m.scrollTo({ top, behavior: 'smooth' });
  }

  // ── Signal taxonomy (mirrors the React classifier) ──────────────────────
  var SIG_DEFS = [
    { key: 'growth',  label: 'Expansion',   color: '#1B844A' },
    { key: 'ma',      label: 'M&A',         color: '#3D5CCF' },
    { key: 'partner', label: 'Partnership', color: '#5FA4F9' },
    { key: 'earn',    label: 'Earnings',    color: '#062D4E' },
    { key: 'risk',    label: 'Risk',        color: '#854F0B' },
    { key: 'leader',  label: 'Leadership',  color: '#696969' },
  ];
  var SIG_LABEL = {}; var SIG_COLOR = {};
  SIG_DEFS.forEach(function (d) { SIG_LABEL[d.key] = d.label; SIG_COLOR[d.key] = d.color; });

  function classifyText(t) {
    t = (t || '').toLowerCase();
    if (/lawsuit|class action|investig|bankrupt|deficien|material weakness|noncompli|delist|fraud|wind-down|closure|clos(e|ing|ure)|downgrad|distress|recall|probe/.test(t)) return 'risk';
    if (/acqui|merger|buyout|takeover|\bipo\b|sale-leaseback|divestit|recapitaliz|\bbid\b|spin-?off/.test(t)) return 'ma';
    if (/earning|revenue|q[1-4]\b|quarter|fiscal|dividend|guidance|senior notes|refinanc|buyback|repurchase/.test(t)) return 'earn';
    if (/\bopen(s|ing|ed)?\b|expansion|expand|new store|new location|grand opening|milestone|launch|enters?\b|store count/.test(t)) return 'growth';
    if (/partner|integration|financing|credit card|bnpl|co-?brand/.test(t)) return 'partner';
    if (/\bceo\b|president|chair(man)?\b|board\b|appoint|succession|\bhire|promot|named/.test(t)) return 'leader';
    return 'other';
  }

  // Wrap each ledger event (opp-line / comp date line + its summary & read-
  // through) into a .evt block tagged with its signal, so we can filter.
  function wrapLedgerEvents(md) {
    md.querySelectorAll('.opp-entry').forEach(function (entry) {
      if (entry.dataset.wrapped) return;
      entry.dataset.wrapped = '1';
      var group = null;
      Array.prototype.slice.call(entry.children).forEach(function (node) {
        if (node.classList.contains('opp-name')) { group = null; return; }
        if (node.classList.contains('opp-line')) {
          group = document.createElement('div'); group.className = 'evt';
          var link = node.querySelector('a, .link');
          group.dataset.sig = classifyText(link ? link.textContent : node.textContent);
          entry.insertBefore(group, node); group.appendChild(node);
        } else if (group) { group.appendChild(node); }
      });
    });
    md.querySelectorAll('.comp-entry').forEach(function (entry) {
      if (entry.dataset.wrapped) return;
      entry.dataset.wrapped = '1';
      var group = null;
      Array.prototype.slice.call(entry.children).forEach(function (node) {
        if (node.classList.contains('comp-entry-head')) { group = null; return; }
        if (node.classList.contains('date')) {
          group = document.createElement('div'); group.className = 'evt';
          var link = node.querySelector('a, .link');
          group.dataset.sig = classifyText(link ? link.textContent : node.textContent);
          entry.insertBefore(group, node); group.appendChild(node);
        } else if (group) { group.appendChild(node); }
      });
    });
  }

  var activeFilter = 'all';
  function applyFilter(key) {
    activeFilter = key;
    document.querySelectorAll('.filter-chip').forEach(function (c) {
      var on = c.dataset.sig === key;
      c.classList.toggle('active', on);
      if (c.dataset.sig !== 'all') c.style.background = on ? (c.dataset.color || '') : '';
    });
    var show = function (el, on) { el.classList.toggle('is-hidden', !on); };
    document.querySelectorAll('.evt').forEach(function (e) {
      show(e, key === 'all' || e.dataset.sig === key);
    });
    document.querySelectorAll('.na-card[data-sig]').forEach(function (c) {
      show(c, key === 'all' || c.dataset.sig === key);
    });
    // collapse empty containers
    document.querySelectorAll('.opp-entry').forEach(function (en) {
      var any = en.querySelector('.evt:not(.is-hidden)');
      show(en, !!any);
    });
    document.querySelectorAll('.opp-owner').forEach(function (ow) {
      var any = ow.querySelector('.opp-entry:not(.is-hidden)');
      show(ow, !!any);
    });
    document.querySelectorAll('.comp-entry').forEach(function (ce) {
      var any = ce.querySelector('.evt:not(.is-hidden)');
      show(ce, !!any);
    });
  }

  function buildFilterBar(md) {
    if (md.querySelector('.filter-bar')) return;
    wrapLedgerEvents(md);
    var counts = {}; var total = 0;
    md.querySelectorAll('.evt[data-sig]').forEach(function (e) {
      var k = e.dataset.sig; if (k === 'other') return;
      counts[k] = (counts[k] || 0) + 1; total++;
    });
    var present = SIG_DEFS.filter(function (d) { return counts[d.key]; });
    if (present.length < 2) return; // nothing meaningful to filter
    var bar = document.createElement('div');
    bar.className = 'filter-bar';
    var html = '<span class="filter-bar-label">Filter</span>';
    html += '<button class="filter-chip fc-all active" data-sig="all"><span>All</span><span class="fc-n">' + total + '</span></button>';
    present.forEach(function (d) {
      html += '<button class="filter-chip" data-sig="' + d.key + '" data-color="' + d.color + '">' +
                '<span class="fc-dot" style="background:' + d.color + '"></span>' +
                '<span>' + d.label + '</span><span class="fc-n">' + counts[d.key] + '</span>' +
              '</button>';
    });
    bar.innerHTML = html;
    bar.addEventListener('click', function (e) {
      var chip = e.target.closest('.filter-chip'); if (!chip) return;
      applyFilter(chip.dataset.sig === activeFilter && chip.dataset.sig !== 'all' ? 'all' : chip.dataset.sig);
    });
    var compSection = md.querySelector('section.competitors');
    if (compSection) compSection.parentNode.insertBefore(bar, compSection);
    else md.insertBefore(bar, md.firstChild);
  }

  // ── Sticky context bar ───────────────────────────────────────────────────
  function buildContextBar(main) {
    if (main.querySelector('.context-bar')) return;
    var title = '';
    var h = main.querySelector('.briefing-header h1, .page-header h1');
    if (h) title = h.textContent.trim();
    var bar = document.createElement('div');
    bar.className = 'context-bar';
    bar.innerHTML = '<span class="ctx-title"></span>' +
                    '<span class="ctx-sep" style="display:none">›</span>' +
                    '<span class="ctx-section"></span>' +
                    '<span class="ctx-spacer"></span>' +
                    '<button class="ctx-top">↑ Top</button>';
    bar.querySelector('.ctx-title').textContent = title;
    bar.querySelector('.ctx-top').addEventListener('click', function () {
      main.scrollTo({ top: 0, behavior: 'smooth' });
    });
    main.insertBefore(bar, main.firstChild);
  }

  function attachScrollSpy() {
    var main = document.querySelector('.main-content');
    if (!main || main.dataset.spy) return;
    main.dataset.spy = '1';
    var raf = 0;
    var onScroll = function () {
      if (raf) return;
      raf = requestAnimationFrame(function () {
        raf = 0;
        var nav = document.querySelector('.jump-nav');
        var currentId = null, currentName = '';
        var links = nav ? [].slice.call(nav.querySelectorAll('.jump-link[data-anchor]')) : [];
        links.forEach(function (l) {
          var t = document.getElementById(l.dataset.anchor);
          if (t && t.getBoundingClientRect().top <= 140) { currentId = l.dataset.anchor; currentName = (l.querySelector('span') || {}).textContent || ''; }
        });
        links.forEach(function (l) { l.classList.toggle('current', l.dataset.anchor === currentId); });
        // context bar
        var bar = main.querySelector('.context-bar');
        if (bar) {
          var show = main.scrollTop > 200;
          bar.classList.toggle('show', show);
          var sec = bar.querySelector('.ctx-section'), sep = bar.querySelector('.ctx-sep');
          if (currentName) { sec.textContent = currentName; sep.style.display = ''; }
          else { sec.textContent = ''; sep.style.display = 'none'; }
        }
      });
    };
    main.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  function buildJumpNav(rows) {
    removeJumpNav();
    if (!rows || !rows.length) return;
    const nav = document.createElement('div');
    nav.className = 'jump-nav';
    const icon = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 4h11M2.5 8h11M2.5 12h7"/></svg>';
    nav.innerHTML =
      '<button class="jump-toggle" type="button">' + icon + '<span>Sections</span></button>' +
      '<div class="jump-panel">' +
        '<div class="jump-panel-head">Jump to SAE</div>' +
        '<div class="jump-link" data-top="1"><span>Top of briefing</span></div>' +
        rows.map(r => '<div class="jump-link" data-anchor="' + esc(r.anchor) + '"><span>' + esc(r.name) + '</span><span class="jl-count">' + esc(r.count) + '</span></div>').join('') +
      '</div>';
    document.body.appendChild(nav);
    nav.querySelector('.jump-toggle').addEventListener('click', () => nav.classList.toggle('open'));
    nav.querySelectorAll('.jump-link').forEach(l => {
      l.addEventListener('click', () => {
        if (l.dataset.top) {
          const m = document.querySelector('.main-content');
          if (m) m.scrollTo({ top: 0, behavior: 'smooth' });
        } else {
          scrollToAnchor(l.dataset.anchor);
        }
        nav.classList.remove('open');
      });
    });
    attachScrollSpy();
  }

  function enhance() {
    const main = document.querySelector('.main-content');
    if (!main) return;
    const md = main.querySelector('.md-content');
    if (!md) { removeJumpNav(); return; }

    decorateSaeHeadings(md);
    tagSilentH2(md);
    ensureAnchors(md);
    buildContextBar(main);
    attachScrollSpy();

    if (!isEditionView(main)) { removeJumpNav(); return; }
    if (document.querySelector('.sae-leaderboard')) return;

    const saeRows = collectSaeRows(md);

    const lb = buildLeaderboard(saeRows);
    if (lb) {
      // place leaderboard AFTER competitor section so the hero stays first
      const compSection = md.querySelector('section.competitors');
      if (compSection && compSection.nextElementSibling) {
        compSection.parentNode.insertBefore(lb, compSection.nextElementSibling);
      } else {
        const insertAfter = main.querySelector('.exec-summary') || main.querySelector('.briefing-header');
        if (insertAfter) insertAfter.parentNode.insertBefore(lb, insertAfter.nextSibling);
      }
    }

    buildFilterBar(md);
    buildJumpNav(saeRows);
  }

  // Run after each render. The React app replaces .main-content children on
  // navigation, so observe .main-content. Pause the observer while we mutate
  // so our own insertions can't retrigger us.
  let obs;
  let running = false;
  function safeEnhance() {
    if (running) return;
    running = true;
    try { enhance(); } finally { running = false; }
  }
  const tick = () => {
    clearTimeout(window.__wikiEnhanceT);
    window.__wikiEnhanceT = setTimeout(safeEnhance, 40);
  };
  obs = new MutationObserver(tick);
  function start() {
    safeEnhance();
    const main = document.querySelector('.main-content') || document.body;
    obs.observe(main, { childList: true, subtree: true });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
