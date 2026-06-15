// Competitor Intelligence Wiki v2
// Features: Competitor Watch, SEC filings tracker, Ask Claude, Trend Analysis

const { useState, useMemo, useCallback, useRef, useEffect, Fragment } = React;

function Collapsible({ title, count, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyRef = useRef(null);
  return (
    <div>
      <div className="collapsible-header" onClick={() => setOpen(o => !o)}>
        <span className={'chevron' + (open ? ' open' : '')}>&#9654;</span>
        <h2>{title}</h2>
        {count != null && <span className="section-count">({count})</span>}
      </div>
      <div ref={bodyRef} className={'collapsible-body' + (open ? '' : ' collapsed')}
           style={{maxHeight: open ? (bodyRef.current?.scrollHeight || 9999) + 'px' : '0'}}>
        {children}
      </div>
    </div>
  );
}

function SidebarSection({ title, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="sidebar-section">
      <div className="sidebar-section-title" onClick={() => setOpen(o => !o)}>
        <span className={'sidebar-chevron' + (open ? ' open' : '')}>&#9654;</span>
        {title}
      </div>
      <div className={'sidebar-section-items' + (open ? '' : ' collapsed')}
           style={{maxHeight: open ? '9999px' : '0'}}>
        {children}
      </div>
    </div>
  );
}

// ─── Data ────────────────────────────────────────────────────────────────────
const RAW_PAGES = JSON.parse(document.getElementById('wiki-data').textContent);
const PAGE_MAP = {};
RAW_PAGES.forEach(p => { PAGE_MAP[p.slug] = p; });

const SAE_PAGES = RAW_PAGES
  .filter(p => p.type === 'sae')
  .sort((a, b) => (a.title || a.slug).localeCompare(b.title || b.slug));

const SAE_PARTNER_COUNTS = {};
RAW_PAGES.forEach(p => {
  if (p.type === 'partner' && p.sae) {
    const slug = p.sae.replace(/\[\[|\]\]/g, '').trim();
    SAE_PARTNER_COUNTS[slug] = (SAE_PARTNER_COUNTS[slug] || 0) + 1;
  }
});

const PARTNER_PAGES = RAW_PAGES.filter(p => p.type === 'partner');
const EVENT_PAGES = RAW_PAGES.filter(p => p.type === 'event');
const COMPETITOR_PAGES = RAW_PAGES.filter(p => p.type === 'competitor');

const SEC_FILING_PAGES = RAW_PAGES.filter(p => p.type === 'sec-filing');
// Join a competitor page slug -> its SEC tracker page via the tracker's
// `competitor: [[slug]]` frontmatter (build_wiki strips the brackets).
const SEC_FILING_MAP = {};
SEC_FILING_PAGES.forEach(p => {
  const c = (p.competitor || '').replace(/\[\[|\]\]/g, '').trim();
  if (c) SEC_FILING_MAP[c] = p;
});
const SEC_FILING_INDEX = SEC_FILING_PAGES.find(p => !p.competitor) || null;

// News tracker pages: same competitor join as SEC filings.
const NEWS_PAGES = RAW_PAGES.filter(p => p.type === 'news');
const NEWS_MAP = {};
NEWS_PAGES.forEach(p => {
  const c = (p.competitor || '').replace(/\[\[|\]\]/g, '').trim();
  if (c) NEWS_MAP[c] = p;
});
const NEWS_INDEX = NEWS_PAGES.find(p => !p.competitor) || null;

const OPPORTUNITY_PAGES = RAW_PAGES
  .filter(p => p.type === 'opportunity-list')
  .sort((a, b) => (a.owner_name || a.title || '').localeCompare(b.owner_name || b.title || ''));
const OPPORTUNITY_INDEX = RAW_PAGES.find(p => p.type === 'opportunity-index') || null;
const OPPORTUNITY_TOTAL = OPPORTUNITY_PAGES.reduce((n, p) => n + (parseInt(p.count, 10) || 0), 0);

const INDUSTRY_MAP = {};
const INDUSTRY_LABELS = {
  'wheel-tire': 'Wheel & Tire',
  'auto-service': 'Auto Service',
  'collision': 'Collision',
  'furniture': 'Furniture',
  'mattresses': 'Mattresses',
  'appliances': 'Appliances',
  'elective-medical': 'Elective Medical',
  'medical-devices': 'Medical Devices',
  'car-audio': 'Car Audio',
};
PARTNER_PAGES.forEach(p => {
  const seg = (p.segment || '').replace(/\[\[|\]\]/g, '').trim();
  if (seg && seg !== 'null') {
    INDUSTRY_MAP[seg] = INDUSTRY_MAP[seg] || [];
    INDUSTRY_MAP[seg].push(p);
  }
});

const TYPE_LABELS = {
  edition: 'Edition', event: 'Event', partner: 'Partner',
  competitor: 'Competitor', sae: 'SAE', segment: 'Segment', source: 'Source',
  industry: 'Industry',
  'opportunity-list': 'Opportunities', 'opportunity-index': 'Opportunities',
  'sec-filing': 'SEC Filing', news: 'News',
};
function pluralLabel(type) {
  const l = TYPE_LABELS[type] || type;
  if (/(s|ies)$/i.test(l)) return l;
  if (/y$/i.test(l)) return l.slice(0, -1) + 'ies';
  return l + 's';
}

const EDITION_PAGES = RAW_PAGES
  .filter(p => p.type === 'edition')
  .sort((a, b) => (b.date || '').localeCompare(a.date || ''));
const LATEST_EDITION_SLUG = EDITION_PAGES.length > 0 ? EDITION_PAGES[0].slug : null;
function fmtEditionDate(iso) {
  if (!iso) return '';
  return new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}
// Canonical event-date display, shared across all views so the app never
// mixes raw ISO ("2026-06-03") with formatted ("Jun 3, 2026") on one screen.
function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// ─── Helpers ─────────────────────────────────────────────────────────────────
function sanitize(html) {
  if (typeof window !== 'undefined' && window.DOMPurify) {
    return window.DOMPurify.sanitize(html, { ADD_ATTR: ['target', 'data-slug'] });
  }
  return html;
}

function SafeHTML({ html, className, onRef }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const clean = sanitize(html);
    const parsed = new DOMParser().parseFromString('<div>' + clean + '</div>', 'text/html');
    const wrapper = parsed.body.firstChild;
    while (ref.current.firstChild) ref.current.removeChild(ref.current.firstChild);
    if (wrapper) {
      while (wrapper.firstChild) ref.current.appendChild(wrapper.firstChild);
    }
    if (onRef) onRef(ref.current);
  }, [html]);
  return React.createElement('div', { ref, className });
}

function slugifyHeading(text) {
  return text.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
}

function renderMarkdown(content) {
  let body = content;
  let fm = {};
  if (content.startsWith('---')) {
    const end = content.indexOf('---', 3);
    if (end !== -1) {
      content.slice(3, end).trim().split('\n').forEach(line => {
        const idx = line.indexOf(':');
        if (idx === -1) return;
        const key = line.slice(0, idx).trim();
        let val = line.slice(idx + 1).trim();
        if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) val = val.slice(1, -1);
        fm[key] = val;
      });
      body = content.slice(end + 3).trim();
    }
  }
  const processed = body.replace(/\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]/g, (_, slug, label) => {
    const display = label || slug;
    const clean = slug.trim();
    if (PAGE_MAP[clean]) return '<span class="wikilink" data-slug="' + clean + '">' + display + '</span>';
    return '<span class="wikilink-dead" title="Not found: ' + clean + '">' + display + '</span>';
  });
  return { fm, bodyHtml: marked.parse(processed) };
}

function fixHeadingIds(el) {
  if (!el) return;
  el.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(h => {
    h.setAttribute('id', slugifyHeading(h.textContent));
  });
}

function buildWikiText() {
  return RAW_PAGES.map(page => {
    const meta = [page.type.toUpperCase()];
    if (page.significance) meta.push(page.significance.toUpperCase());
    if (page.date) meta.push(page.date);
    if (page.sae) meta.push('SAE:' + page.sae.replace(/\[\[|\]\]/g, ''));
    let body = page.content;
    if (body.startsWith('---')) { const end = body.indexOf('---', 3); if (end !== -1) body = body.slice(end + 3).trim(); }
    return '[' + meta.join(' | ') + ']\nTitle: ' + page.title + '\n\n' + body;
  }).join('\n\n---\n\n');
}

// ─── Claude API (Flask CORS proxy) ──────────────────────────────────────────
// Snap Finance org disables Anthropic browser CORS, so the wiki POSTs to a
// Flask proxy on R Connect that forwards to api.anthropic.com. The api_key
// travels in the request body; the proxy strips it and sets x-api-key.
const PROXY_BASE = document.querySelector('meta[name="wiki-proxy-url"]')?.content || '';
const EMBEDDED_KEY = document.querySelector('meta[name="wiki-api-key"]')?.content || '';
// When a proxy is configured it holds a server-side Anthropic key, so the
// browser never needs the user to supply one. A user-entered key still works
// (it's forwarded and takes precedence) but is no longer required.
const PROXY_AVAILABLE = !!PROXY_BASE;

const SYSTEM_PROMPT = `You are an analyst assistant for the Snap Finance Competitor Intelligence Wiki. Use the wiki content below as your primary source for partner-, competitor-, and SAE-specific facts. You may also draw on your general knowledge of consumer finance, retail verticals, public-company filings, and macro trends to enrich answers — there is no restriction to wiki content alone. When you cite a fact that came from outside the wiki, label it as such (e.g. "general knowledge:" or "macro context:").

Response format:
- Group findings into 3-6 themes with **bold headers**
- 2-3 bullets per theme, one sentence each
- End with **Key sources:** listing relevant partners/competitors/external sources
- Use numbers to support points, not to lead`;

async function callClaude(apiKey, question, wikiText) {
  const endpoint = PROXY_BASE ? PROXY_BASE.replace(/\/+$/, '') + '/chat' : 'https://api.anthropic.com/v1/messages';
  const headers = { 'Content-Type': 'application/json' };
  if (!PROXY_BASE) {
    headers['x-api-key'] = apiKey;
    headers['anthropic-version'] = '2023-06-01';
    headers['anthropic-dangerous-direct-browser-access'] = 'true';
  }
  const body = {
    model: 'claude-sonnet-4-20250514',
    max_tokens: 2048,
    system: [{ type: 'text', text: SYSTEM_PROMPT + '\n\n=== WIKI CONTENT ===\n' + wikiText, cache_control: { type: 'ephemeral' } }],
    messages: [{ role: 'user', content: question }],
  };
  if (PROXY_BASE && apiKey) body.api_key = apiKey;
  const res = await fetch(endpoint, { method: 'POST', headers, body: JSON.stringify(body) });
  if (!res.ok) {
    const raw = await res.text().catch(() => '');
    let detail = '';
    try { const j = JSON.parse(raw); detail = j.error?.message || j.error || j.detail || ''; } catch(e) { detail = raw.slice(0, 300); }
    throw new Error('API error ' + res.status + ': ' + (detail || '(no detail)'));
  }
  const data = await res.json();
  return data.content[0].text;
}

// ─── Components ──────────────────────────────────────────────────────────────
function ExecSummary({ fm }) {
  // Window to the current edition so these counts agree with EditionHeader,
  // rather than tallying every event ever recorded. Falls back to the edition
  // date, then to all events, if no window is present.
  const start = (fm && (fm.window_start || fm.date)) || '';
  const end = (fm && (fm.window_end || fm.date)) || '';
  const inWindow = (e) => {
    if (!start || !end || !e.date) return true;
    return e.date >= start && e.date <= end;
  };
  const windowEvents = EVENT_PAGES.filter(inWindow);
  const highEvents = windowEvents.filter(e => e.significance === 'high');
  const expansion = windowEvents.filter(e => /acqui|expan|open|launch|new store|partner|grow|grand opening/i.test(e.title || ''));
  const risk = windowEvents.filter(e => /lawsuit|class action|investi|clos|bankrupt|regulatory|deficiency/i.test(e.title || ''));
  if (highEvents.length === 0 && expansion.length === 0 && risk.length === 0) return null;
  const headlines = highEvents.slice(0, 3).map(e => e.title);
  return (
    <div className="exec-summary">
      <div className="exec-summary-label">Executive Summary</div>
      <div className="exec-summary-text">
        <strong>{highEvents.length} high-impact event{highEvents.length !== 1 ? 's' : ''}</strong> this window
        {expansion.length > 0 && <>, with <strong>{expansion.length} expansion signal{expansion.length !== 1 ? 's' : ''}</strong></>}
        {risk.length > 0 && <> and <strong>{risk.length} risk flag{risk.length !== 1 ? 's' : ''}</strong></>}.
        {headlines.length > 0 && <> Top items: {headlines.join('; ')}.</>}
      </div>
    </div>
  );
}

function EditionHeader({ fm }) {
  const pc = fm.partner_event_count || '0', cc = fm.competitor_event_count || '0', sc = fm.saes_with_findings || '0';
  const fmt = (iso) => iso ? new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
  const win = fm.window_start && fm.window_end ? fmt(fm.window_start) + ' – ' + fmt(fm.window_end) : '';
  return (
    <header className="briefing-header">
      <h1>Competitor Intelligence — Weekly Briefing</h1>
      <div className="sub">Prepared for senior leadership · {fm.date ? new Date(fm.date + 'T12:00:00').toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) : ''}</div>
      <div className="meta">
        <span><strong>{pc}</strong> partner events</span>
        <span><strong>{cc}</strong> competitor moves</span>
        <span><strong>{sc}</strong> SAEs with findings</span>
        {win && <span><strong>Window:</strong> {win}</span>}
      </div>
    </header>
  );
}

function PageHeader({ page }) {
  const isEntity = ['partner', 'competitor', 'sae'].includes(page.type);
  const clean = (v) => { const s = (v || '').toString().replace(/\[\[|\]\]/g, '').trim(); return (!s || s === 'null') ? '' : s; };
  return (
    <div className="page-header">
      <span className="page-type">{TYPE_LABELS[page.type] || page.type}</span>
      <h1>{page.title}</h1>
      {!isEntity && (
        <div className="page-meta">
          {clean(page.date) && <span>{clean(page.date)}</span>}
          {clean(page.sae) && <span>SAE: {clean(page.sae)}</span>}
          {clean(page.tier) && <span>Tier: {clean(page.tier)}</span>}
          {clean(page.segment) && <span>Segment: {clean(page.segment)}</span>}
          {clean(page.parent) && <span>Parent: {clean(page.parent)}</span>}
          {clean(page.ticker) && <span>Ticker: {clean(page.ticker)}</span>}
          {clean(page.significance) && <span>Significance: {clean(page.significance)}</span>}
          {page.url && <span><a href={page.url} target="_blank" rel="noopener" style={{color:'var(--accent)'}}>Source</a></span>}
        </div>
      )}
    </div>
  );
}

// ─── Ask Claude Panel ────────────────────────────────────────────────────────
function AskClaudePanel() {
  const [apiKey, setApiKey] = useState(() => EMBEDDED_KEY || sessionStorage.getItem('snap_wiki_api_key') || '');
  const [keyInput, setKeyInput] = useState('');
  // The proxy supplies a server-side key, so no key entry is required when it's
  // configured. Direct-to-Anthropic (no proxy) still needs a user key.
  const [keySet, setKeySet] = useState(() => PROXY_AVAILABLE || !!(EMBEDDED_KEY || sessionStorage.getItem('snap_wiki_api_key')));
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const qRef = useRef(null);
  const wikiText = useMemo(() => buildWikiText(), []);
  const hasEmbeddedKey = !!EMBEDDED_KEY;

  const saveKey = () => {
    const k = keyInput.trim();
    if (!k.startsWith('sk-ant-')) { setError('Key should start with sk-ant-'); return; }
    sessionStorage.setItem('snap_wiki_api_key', k);
    setApiKey(k); setKeySet(true); setKeyInput(''); setError(null);
    setTimeout(() => qRef.current?.focus(), 50);
  };
  const clearKey = () => {
    sessionStorage.removeItem('snap_wiki_api_key');
    setApiKey(EMBEDDED_KEY || ''); setKeySet(PROXY_AVAILABLE || !!EMBEDDED_KEY);
    setResponse(null); setError(null);
  };
  const ask = async () => {
    if (!question.trim() || (!apiKey && !PROXY_AVAILABLE) || loading) return;
    setLoading(true); setError(null); setResponse(null);
    try { setResponse(await callClaude(apiKey, question.trim(), wikiText)); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  };

  if (!keySet) {
    return (
      <div className="main-content">
        <div className="claude-panel">
          <div className="claude-setup">
            <h2>Ask Claude</h2>
            <p>Enter your Anthropic API key to ask questions. Stored in sessionStorage only — cleared when you close the tab.</p>
            <div className="claude-key-row">
              <input type="password" placeholder="sk-ant-api03-..." value={keyInput} onChange={e => setKeyInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && saveKey()} autoFocus />
              <button onClick={saveKey}>Save key</button>
            </div>
            {error && <div className="claude-error">{error}</div>}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="main-content">
      <div className="claude-panel">
        <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14}}>
          <h2 style={{fontSize:20, fontWeight:700}}>Ask Claude</h2>
          {!hasEmbeddedKey && apiKey && <button className="claude-clear" onClick={clearKey}>Clear API key</button>}
        </div>
        <div className="claude-ask-row">
          <textarea ref={qRef} placeholder={'Ask about any partner, competitor, SAE, trend, or general industry topic…\ne.g. "Which partners are expanding fastest?" or "How does AAP compare to O\'Reilly?"'} value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) ask(); }} rows={3} autoFocus />
          <button onClick={ask} disabled={loading || !question.trim()}>{loading ? '…' : 'Ask'}</button>
        </div>
        <div className="claude-hint">Ctrl+Enter to submit · Full wiki context + Claude's general knowledge</div>
        {error && <div className="claude-error">{error}</div>}
        {loading && <div className="claude-loading">Consulting the wiki…</div>}
        {response && !loading && (
          <div className="claude-response">
            <div className="claude-response-header">Claude's analysis</div>
            <SafeHTML className="md-content claude-response-body" html={marked.parse(response)} />
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Industry Groups View ────────────────────────────────────────────────────
function analyzeIndustry(industryKey) {
  const partners = INDUSTRY_MAP[industryKey] || [];
  const partnerSlugs = new Set(partners.map(p => p.slug));
  const events = EVENT_PAGES.filter(e => {
    const ps = (e.partner || '').replace(/\[\[|\]\]/g, '').trim();
    return partnerSlugs.has(ps);
  });

  const catCounts = {};
  events.forEach(e => { const c = e.category || 'other'; catCounts[c] = (catCounts[c] || 0) + 1; });

  const highEvents = events.filter(e => e.significance === 'high');

  const expansion = events.filter(e => /acqui|expan|open|launch|new store|new location|partner|grow|grand opening/i.test(e.title || ''));
  const risk = events.filter(e => /lawsuit|class action|investi|clos|bankrupt|regulatory|ftc|cfpb|deficiency|material weakness|fitch|downgrad/i.test(e.title || ''));
  const ma = events.filter(e => /acqui|ipo|merger|sale|buyout|takeover|bid/i.test(e.title || ''));
  const earnings = events.filter(e => /earning|revenue|q[1-4]|quarter|fiscal/i.test(e.title || ''));

  const compEvents = COMPETITOR_PAGES.map(c => {
    const cEvents = EVENT_PAGES.filter(e => {
      const cs = (e.competitor || '').replace(/\[\[|\]\]/g, '').trim();
      return cs === c.slug;
    });
    return { name: c.title, slug: c.slug, events: cEvents };
  }).filter(c => c.events.length > 0);

  const saeCounts = {};
  partners.forEach(p => {
    const sae = (p.sae || '').replace(/\[\[|\]\]/g, '').trim();
    if (sae) saeCounts[sae] = (saeCounts[sae] || 0) + 1;
  });

  const tierCounts = {};
  partners.forEach(p => { if (p.tier) tierCounts[p.tier] = (tierCounts[p.tier] || 0) + 1; });

  let outlook = 'Stable';
  if (expansion.length > risk.length * 2) outlook = 'Growth';
  else if (risk.length > expansion.length) outlook = 'Cautious';
  else if (ma.length >= 2) outlook = 'Consolidating';

  return { partners, events, catCounts, highEvents, expansion, risk, ma, earnings, compEvents, saeCounts, tierCounts, outlook };
}

const CAT_LABELS = {
  'ma': 'M&A', 'leadership': 'Leadership', 'earnings': 'Earnings', 'closure': 'Closures',
  'regulatory': 'Regulatory', 'partnership': 'Partnership', 'store-move': 'Store Moves',
  'financing': 'Financing', 'other': 'Other',
};

function IndustryView({ industryKey, navigateTo }) {
  const label = INDUSTRY_LABELS[industryKey] || industryKey;
  const analysis = useMemo(() => analyzeIndustry(industryKey), [industryKey]);
  const { partners, events, catCounts, highEvents, expansion, risk, ma, earnings, compEvents, saeCounts, tierCounts, outlook } = analysis;

  const outlookColor = { Growth: '#1B844A', Cautious: '#DC7F4A', Consolidating: '#3D5CCF', Stable: 'var(--muted)' }[outlook] || 'var(--muted)';

  return (
    <div className="main-content">
      <div className="page-header">
        <span className="page-type">Industry Report</span>
        <h1>{label}</h1>
        <div className="page-meta">
          <span><strong>{partners.length}</strong> managed partners</span>
          <span><strong>{events.length}</strong> tracked events</span>
          {highEvents.length > 0 && <span><strong>{highEvents.length}</strong> high-impact</span>}
          <span style={{color: outlookColor, fontWeight: 700}}>Outlook: {outlook}</span>
        </div>
      </div>
      <div className="md-content">

        {/* Signal cards */}
        <h2 style={{display:'inline-block'}}>Vertical Signals</h2>
        <div className="trend-grid">
          <div className="trend-card trend-expansion">
            <div className="trend-number">{expansion.length}</div>
            <div className="trend-label">Expansion</div>
            <div className="trend-desc">New stores, launches, market entries</div>
          </div>
          <div className="trend-card trend-ma">
            <div className="trend-number">{ma.length}</div>
            <div className="trend-label">M&A / Capital</div>
            <div className="trend-desc">Acquisitions, IPOs, financing moves</div>
          </div>
          <div className="trend-card trend-risk">
            <div className="trend-number">{risk.length}</div>
            <div className="trend-label">Risk Signals</div>
            <div className="trend-desc">Legal, regulatory, financial distress</div>
          </div>
          <div className="trend-card trend-high">
            <div className="trend-number">{earnings.length}</div>
            <div className="trend-label">Earnings / Financial</div>
            <div className="trend-desc">Quarterly results, revenue reports</div>
          </div>
        </div>

        {/* Event category breakdown */}
        {Object.keys(catCounts).length > 0 && (
          <>
            <hr className="section-divider" />
            <h2 style={{display:'inline-block'}}>Event Categories</h2>
            <table>
              <thead><tr><th>Category</th><th>Count</th><th>Share</th></tr></thead>
              <tbody>
                {Object.entries(catCounts).sort((a,b) => b[1] - a[1]).map(([cat, count]) => (
                  <tr key={cat}>
                    <td style={{fontWeight:600}}>{CAT_LABELS[cat] || cat}</td>
                    <td>{count}</td>
                    <td>{events.length > 0 ? Math.round(count / events.length * 100) + '%' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {/* Key developments */}
        {highEvents.length > 0 && (
          <>
            <hr className="section-divider" />
            <h2 style={{display:'inline-block'}}>Key Developments</h2>
            {highEvents.sort((a,b) => (b.date||'').localeCompare(a.date||'')).map(e => (
              <div key={e.slug} className="trend-event event-high-impact" onClick={() => navigateTo(e.slug)} style={{cursor:'pointer'}}>
                <SignalChip sig={classifySignal(e)} />
                <strong>{e.title}</strong>
                <span style={{color:'var(--muted)', fontSize:12, marginLeft:8}}>{fmtDate(e.date)}</span>
              </div>
            ))}
          </>
        )}

        {/* Competitive landscape */}
        {compEvents.length > 0 && (
          <>
            <hr className="section-divider" />
            <h2 style={{display:'inline-block'}}>Competitive Landscape</h2>
            <p style={{color:'var(--muted)', fontSize:13, marginBottom:12}}>Competitor activity relevant to this vertical's credit space.</p>
            {compEvents.map(c => (
              <div key={c.slug} style={{marginBottom:16}}>
                <div style={{fontWeight:700, fontSize:15, marginBottom:4, cursor:'pointer', color:'var(--accent)'}} onClick={() => navigateTo(c.slug)}>{c.name}</div>
                {c.events.slice(0, 3).map(e => (
                  <div key={e.slug} className={'industry-event' + (e.significance === 'high' ? ' event-high-impact' : '')} onClick={() => navigateTo(e.slug)}>
                    <span className="industry-event-date">{fmtDate(e.date)}</span>
                    <span className="industry-event-title">{e.title}</span>
                    {e.significance === 'high' && <span className="pill">High Impact</span>}
                  </div>
                ))}
              </div>
            ))}
          </>
        )}

        {/* Portfolio composition */}
        <hr className="section-divider" />
        <h2 style={{display:'inline-block'}}>Portfolio Composition</h2>
        {Object.keys(tierCounts).length > 0 && (
          <div style={{marginBottom:16}}>
            <div style={{fontSize:13, color:'var(--muted)', marginBottom:8}}>By tier:</div>
            <div style={{display:'flex', gap:12, flexWrap:'wrap'}}>
              {Object.entries(tierCounts).sort((a,b) => a[0].localeCompare(b[0])).map(([tier, count]) => (
                <div key={tier} style={{background:'var(--bg-soft)', border:'1px solid var(--line)', borderRadius:6, padding:'6px 14px', fontSize:13}}>
                  <strong>{tier}</strong>: {count} partner{count !== 1 ? 's' : ''}
                </div>
              ))}
            </div>
          </div>
        )}
        {Object.keys(saeCounts).length > 0 && (
          <div style={{marginBottom:16}}>
            <div style={{fontSize:13, color:'var(--muted)', marginBottom:8}}>By SAE coverage:</div>
            <div style={{display:'flex', gap:12, flexWrap:'wrap'}}>
              {Object.entries(saeCounts).sort((a,b) => b[1] - a[1]).map(([sae, count]) => (
                <div key={sae} style={{background:'var(--bg-soft)', border:'1px solid var(--line)', borderRadius:6, padding:'6px 14px', fontSize:13, cursor:'pointer'}} onClick={() => navigateTo(sae)}>
                  <strong>{sae.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</strong>: {count}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* All partners */}
        <Collapsible title="Partners" count={partners.length} defaultOpen={false}>
        {partners.sort((a,b) => a.title.localeCompare(b.title)).map(p => {
          const pEvents = events.filter(e => (e.partner || '').replace(/\[\[|\]\]/g, '').trim() === p.slug);
          return (
            <div key={p.slug} className="industry-partner" onClick={() => navigateTo(p.slug)}>
              <div className="industry-partner-name">{p.title}</div>
              <div className="industry-partner-meta">
                {p.sae && <span>SAE: {p.sae.replace(/\[\[|\]\]/g, '')}</span>}
                {p.tier && <span>Tier: {p.tier}</span>}
                {pEvents.length > 0 && <span>{pEvents.length} event{pEvents.length !== 1 ? 's' : ''}</span>}
              </div>
            </div>
          );
        })}

        </Collapsible>

        {/* Recent events timeline */}
        {events.length > 0 && (
          <Collapsible title="Event Timeline" count={events.length} defaultOpen={false}>
            {events.sort((a,b) => (b.date||'').localeCompare(a.date||'')).map(e => (
              <div key={e.slug} className="industry-event" onClick={() => navigateTo(e.slug)}>
                <span className="industry-event-date">{fmtDate(e.date)}</span>
                <span className="industry-event-title">{e.title}</span>
                {e.significance === 'high' && <span className="pill">High Impact</span>}
                {e.category && <span style={{fontSize:11, color:'var(--muted)', marginLeft:6}}>({CAT_LABELS[e.category] || e.category})</span>}
              </div>
            ))}
          </Collapsible>
        )}
      </div>
    </div>
  );
}

// ─── Trend Analysis View ─────────────────────────────────────────────────────
function TrendView() {
  const trends = useMemo(() => {
    const cats = {};
    EVENT_PAGES.forEach(e => { const c = e.category || 'other'; cats[c] = (cats[c] || 0) + 1; });

    const industryCounts = {};
    Object.entries(INDUSTRY_MAP).forEach(([key, partners]) => {
      const evts = EVENT_PAGES.filter(e => {
        const ps = (e.partner || '').replace(/\[\[|\]\]/g, '').trim();
        return partners.some(p => p.slug === ps);
      });
      industryCounts[key] = { partners: partners.length, events: evts.length, high: evts.filter(e => e.significance === 'high').length };
    });

    const highImpact = EVENT_PAGES.filter(e => e.significance === 'high');
    const expansionSignals = EVENT_PAGES.filter(e => {
      const t = (e.title || '').toLowerCase();
      return /acqui|expan|open|launch|new store|new location|partner|grow/i.test(t);
    });
    const riskSignals = EVENT_PAGES.filter(e => {
      const t = (e.title || '').toLowerCase();
      return /lawsuit|class action|investi|clos|bankrupt|regulatory|ftc|cfpb|deficiency|material weakness/i.test(t);
    });
    const maSignals = EVENT_PAGES.filter(e => {
      const t = (e.title || '').toLowerCase();
      return /acqui|ipo|merger|sale|buyout|continuation vehicle|sell/i.test(t);
    });

    const compMoves = COMPETITOR_PAGES.map(c => {
      const body = c.content.replace(/^---[\s\S]*?---/, '');
      const moveCount = (body.match(/## Recent/g) || []).length + (body.match(/\n- /g) || []).length;
      return { name: c.title, slug: c.slug, moves: moveCount };
    }).sort((a,b) => b.moves - a.moves);

    return { cats, industryCounts, highImpact, expansionSignals, riskSignals, maSignals, compMoves };
  }, []);

  return (
    <div className="main-content">
      <div className="page-header">
        <span className="page-type">Analysis</span>
        <h1>Trend Analysis</h1>
        <div className="page-meta">
          <span>{EVENT_PAGES.length} events tracked</span>
          <span>{PARTNER_PAGES.length} partners monitored</span>
          <span>{COMPETITOR_PAGES.length} competitors watched</span>
        </div>
      </div>
      <div className="md-content">

        <h2 style={{display:'inline-block'}}>Macro Signals</h2>
        <div className="trend-grid">
          <div className="trend-card trend-expansion">
            <div className="trend-number">{trends.expansionSignals.length}</div>
            <div className="trend-label">Expansion signals</div>
            <div className="trend-desc">Acquisitions, new stores, market entries, partnerships</div>
          </div>
          <div className="trend-card trend-ma">
            <div className="trend-number">{trends.maSignals.length}</div>
            <div className="trend-label">M&A activity</div>
            <div className="trend-desc">Acquisitions, IPOs, divestitures, PE transactions</div>
          </div>
          <div className="trend-card trend-risk">
            <div className="trend-number">{trends.riskSignals.length}</div>
            <div className="trend-label">Risk signals</div>
            <div className="trend-desc">Lawsuits, regulatory actions, financial issues</div>
          </div>
          <div className="trend-card trend-high">
            <div className="trend-number">{trends.highImpact.length}</div>
            <div className="trend-label">High-impact events</div>
            <div className="trend-desc">Events flagged as material for Snap</div>
          </div>
        </div>

        <hr className="section-divider" />
        <h2 style={{display:'inline-block'}}>Industry Activity</h2>
        <table>
          <thead><tr><th>Vertical</th><th>Partners</th><th>Events</th><th>High-Impact</th><th>Activity level</th></tr></thead>
          <tbody>
            {Object.entries(trends.industryCounts).sort((a,b) => b[1].events - a[1].events).map(([key, v]) => (
              <tr key={key}>
                <td style={{fontWeight:600}}>{INDUSTRY_LABELS[key] || key}</td>
                <td>{v.partners}</td>
                <td>{v.events}</td>
                <td>{v.high || '—'}</td>
                <td><span className={'activity-bar activity-' + (v.events > 3 ? 'high' : v.events > 0 ? 'med' : 'low')}>{v.events > 3 ? 'High' : v.events > 0 ? 'Moderate' : 'Quiet'}</span></td>
              </tr>
            ))}
          </tbody>
        </table>

        {trends.highImpact.length > 0 && (
          <>
            <hr className="section-divider" />
            <h2 style={{display:'inline-block'}}>High-Impact Events to Review</h2>
            {trends.highImpact.map(e => (
              <div key={e.slug} className="trend-event event-high-impact">
                <SignalChip sig={classifySignal(e)} />
                <strong>{e.title}</strong>
                <span style={{color:'var(--muted)', fontSize:12, marginLeft:8}}>{fmtDate(e.date)}</span>
              </div>
            ))}
          </>
        )}

        <hr className="section-divider" />
        <h2 style={{display:'inline-block'}}>Competitor Positioning</h2>
        {trends.compMoves.map(c => (
          <div key={c.slug} className="trend-competitor">
            <span style={{fontWeight:700, minWidth:200, display:'inline-block'}}>{c.name}</span>
            <span style={{color:'var(--muted)', fontSize:13}}>{c.moves} tracked data points</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────
// ─── Global Search ───────────────────────────────────────────────────────────
// Pure in-memory search over the inlined RAW_PAGES (title + body). No backend.
// Title matches rank above body matches; results are recency-sorted within each
// tier so the freshest events surface first.
function searchPages(query) {
  const q = query.trim().toLowerCase();
  if (q.length < 2) return [];
  const terms = q.split(/\s+/).filter(Boolean);
  const scored = [];
  for (const p of RAW_PAGES) {
    const title = (p.title || p.slug || '').toLowerCase();
    const body = (p.content || '').toLowerCase();
    let titleHits = 0, bodyHits = 0, missed = false;
    for (const t of terms) {
      if (title.includes(t)) titleHits++;
      else if (body.includes(t)) bodyHits++;
      else { missed = true; break; }
    }
    if (missed) continue;
    // tier 0 = every term in title, tier 1 = matched via body
    const tier = titleHits === terms.length ? 0 : 1;
    scored.push({ page: p, tier, date: p.date || '' });
  }
  scored.sort((a, b) => a.tier - b.tier || (b.date).localeCompare(a.date) || (a.page.title || '').localeCompare(b.page.title || ''));
  return scored.slice(0, 30).map(s => s.page);
}

function SearchBox({ openPalette }) {
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || '');
  return (
    <div className="sidebar-search" onClick={openPalette}>
      <input
        type="search"
        className="sidebar-search-input"
        placeholder="Search the wiki…"
        readOnly
        onFocus={e => { e.target.blur(); openPalette(); }}
        onKeyDown={e => { e.preventDefault(); openPalette(); }}
      />
      <span className="sidebar-search-kbd">{isMac ? '⌘K' : 'Ctrl K'}</span>
    </div>
  );
}

// ─── Competitor Watch View ───────────────────────────────────────────────────
function CompetitorView({ navigateTo }) {
  const cards = useMemo(() => COMPETITOR_PAGES.map(c => {
    const body = (c.content || '').replace(/^---[\s\S]*?---/, '');
    const moveSlugs = (body.match(/\[\[([^\]]+)\]\]/g) || [])
      .map(m => m.replace(/\[\[|\]\]/g, '').trim())
      .filter(slug => PAGE_MAP[slug] && PAGE_MAP[slug].type === 'event');
    const moves = [...new Set(moveSlugs)]
      .map(slug => PAGE_MAP[slug])
      .sort((a, b) => (b.date || '').localeCompare(a.date || ''))
      .slice(0, 4);
    const tracker = SEC_FILING_MAP[c.slug] || null;
    const news = NEWS_MAP[c.slug] || null;
    return {
      c, moves, tracker, filings: tracker ? (parseInt(tracker.count, 10) || 0) : 0,
      news, newsCount: news ? (parseInt(news.count, 10) || 0) : 0,
    };
  }), []);

  const totalFilings = cards.reduce((n, x) => n + x.filings, 0);
  const totalNews = cards.reduce((n, x) => n + x.newsCount, 0);

  return (
    <div className="main-content">
      <div className="page-header">
        <span className="page-type">Competitor Watch</span>
        <h1>Competitor Watch</h1>
        <div className="page-meta">
          <span><strong>{COMPETITOR_PAGES.length}</strong> competitors watched</span>
          <span><strong>{SEC_FILING_PAGES.filter(p => p.competitor).length}</strong> public filers</span>
          <span><strong>{totalFilings}</strong> SEC filings tracked · last 24 months</span>
          <span><strong>{totalNews}</strong> news items tracked</span>
        </div>
      </div>
      <div className="md-content">
        <p style={{ marginBottom: 18, display: 'flex', gap: 18, flexWrap: 'wrap' }}>
          {SEC_FILING_INDEX && (
            <span style={{ cursor: 'pointer', color: 'var(--accent)', fontWeight: 600 }}
                  onClick={() => navigateTo(SEC_FILING_INDEX.slug)}>
              View the full SEC filings index →
            </span>
          )}
          {NEWS_INDEX && (
            <span style={{ cursor: 'pointer', color: 'var(--accent)', fontWeight: 600 }}
                  onClick={() => navigateTo(NEWS_INDEX.slug)}>
              View the full news index →
            </span>
          )}
        </p>
        {cards.map(({ c, moves, tracker, filings, news, newsCount }) => (
          <div key={c.slug} style={{ marginBottom: 28 }}>
            <hr className="section-divider" />
            <h2 style={{ display: 'inline-block', cursor: 'pointer', color: 'var(--accent)' }}
                onClick={() => navigateTo(c.slug)}>{c.title}</h2>
            <div className="page-meta" style={{ marginBottom: 10 }}>
              {c.parent && c.parent !== c.title && <span>Parent: {c.parent}</span>}
              {c.ticker && c.ticker !== 'private' && <span>Ticker: {c.ticker}</span>}
              {c.category && <span>{c.category.toUpperCase()}</span>}
            </div>
            {moves.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 6 }}>Recent moves · latest {moves.length}</div>
                {moves.map(e => (
                  <div key={e.slug}
                       className={'industry-event' + (e.significance === 'high' ? ' event-high-impact' : '')}
                       onClick={() => navigateTo(e.slug)}>
                    <SignalChip sig={classifySignal(e)} />
                    <span className="industry-event-date">{fmtDate(e.date)}</span>
                    <span className="industry-event-title">{e.title}</span>
                  </div>
                ))}
              </div>
            )}
            <div style={{ background: 'var(--bg-soft)', border: '1px solid var(--line)',
                          borderRadius: 6, padding: '10px 14px', fontSize: 13,
                          display: 'flex', gap: 18, flexWrap: 'wrap' }}>
              {tracker ? (
                <span style={{ cursor: 'pointer', color: 'var(--accent)', fontWeight: 600 }}
                      onClick={() => navigateTo(tracker.slug)}>
                  View {filings} SEC filing{filings !== 1 ? 's' : ''} →
                </span>
              ) : (
                <span style={{ color: 'var(--muted)' }}>Private — no SEC filings tracked</span>
              )}
              {news && (
                <span style={{ cursor: 'pointer', color: 'var(--accent)', fontWeight: 600 }}
                      onClick={() => navigateTo(news.slug)}>
                  View {newsCount} news item{newsCount !== 1 ? 's' : ''} →
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Sidebar({ activeView, setActiveView, activeSlug, navigateTo, openPalette }) {
  return (
    <div className="sidebar">
      <div className="brand">
        <div className="brand-mark">Snap Finance</div>
        <div className="brand-sub">Competitor Intelligence</div>
      </div>
      <SearchBox openPalette={openPalette} />
      <SidebarSection title="Views" defaultOpen={true}>
        <div className={'sidebar-item' + (activeView === 'competitors' ? ' active' : '')} onClick={() => setActiveView('competitors')}>
          <span>Competitor Watch</span>
          <span className="count-badge">{COMPETITOR_PAGES.length}</span>
        </div>
        <div className={'sidebar-item' + (activeView === 'trends' ? ' active' : '')} onClick={() => setActiveView('trends')}>
          <span>Trend Analysis</span>
        </div>
        <div className={'sidebar-item' + (activeView === 'ask' ? ' active' : '')} onClick={() => setActiveView('ask')}>
          <span>Ask Claude</span>
        </div>
      </SidebarSection>
      <div className="sidebar-divider" />
      <SidebarSection title="Competitors" defaultOpen={true}>
        {COMPETITOR_PAGES.slice().sort((a,b) => (a.title||'').localeCompare(b.title||'')).map(p => (
          <div key={p.slug} className={'sidebar-item' + (activeView === 'page' && activeSlug === p.slug ? ' active' : '')} onClick={() => { setActiveView('page'); navigateTo(p.slug); }}>
            <span>{p.title}</span>
            {SEC_FILING_MAP[p.slug] && <span className="count-badge">{parseInt(SEC_FILING_MAP[p.slug].count,10)||0}</span>}
          </div>
        ))}
      </SidebarSection>
      {SEC_FILING_PAGES.length > 0 && (
        <>
          <div className="sidebar-divider" />
          <SidebarSection title="SEC Filings" defaultOpen={true}>
            {SEC_FILING_INDEX && (
              <div className={'sidebar-item' + (activeView === 'page' && activeSlug === SEC_FILING_INDEX.slug ? ' active' : '')} onClick={() => { setActiveView('page'); navigateTo(SEC_FILING_INDEX.slug); }}>
                <span>Filings Index</span>
                <span className="count-badge">{parseInt(SEC_FILING_INDEX.count,10)||0}</span>
              </div>
            )}
            {SEC_FILING_PAGES.filter(p => p.competitor).slice().sort((a,b)=>(a.title||'').localeCompare(b.title||'')).map(p => (
              <div key={p.slug} className={'sidebar-item' + (activeView === 'page' && activeSlug === p.slug ? ' active' : '')} onClick={() => { setActiveView('page'); navigateTo(p.slug); }}>
                <span>{p.parent || p.title}</span>
                <span className="count-badge">{parseInt(p.count,10)||0}</span>
              </div>
            ))}
          </SidebarSection>
        </>
      )}
      {NEWS_PAGES.length > 0 && (
        <>
          <div className="sidebar-divider" />
          <SidebarSection title="News" defaultOpen={false}>
            {NEWS_INDEX && (
              <div className={'sidebar-item' + (activeView === 'page' && activeSlug === NEWS_INDEX.slug ? ' active' : '')} onClick={() => { setActiveView('page'); navigateTo(NEWS_INDEX.slug); }}>
                <span>News Index</span>
                <span className="count-badge">{parseInt(NEWS_INDEX.count,10)||0}</span>
              </div>
            )}
            {NEWS_PAGES.filter(p => p.competitor).slice().sort((a,b)=>(a.title||'').localeCompare(b.title||'')).map(p => (
              <div key={p.slug} className={'sidebar-item' + (activeView === 'page' && activeSlug === p.slug ? ' active' : '')} onClick={() => { setActiveView('page'); navigateTo(p.slug); }}>
                <span>{(p.competitor || '').replace(/\[\[|\]\]/g, '').trim() || p.title}</span>
                <span className="count-badge">{parseInt(p.count,10)||0}</span>
              </div>
            ))}
          </SidebarSection>
        </>
      )}
    </div>
  );
}

// ─── Signal taxonomy (consistent event chips) ────────────────────────────
const SIGNALS = {
  growth:  { key:'growth',  label:'Expansion',   color:'var(--snap-green)',   bg:'var(--snap-green-tint)',  icon:'growth' },
  ma:      { key:'ma',      label:'M&A',         color:'var(--snap-blue)',    bg:'var(--snap-light-blue)',  icon:'link' },
  earn:    { key:'earn',    label:'Earnings',    color:'var(--snap-navy)',    bg:'#EAF0F6',                 icon:'bars' },
  partner: { key:'partner', label:'Partnership', color:'#5FA4F9',             bg:'var(--snap-light-blue)',  icon:'link' },
  leader:  { key:'leader',  label:'Leadership',  color:'#696969',             bg:'#EFEFEF',                 icon:'person' },
  risk:    { key:'risk',    label:'Risk',        color:'var(--snap-warning)', bg:'var(--snap-warning-bg)',  icon:'risk' },
  other:   { key:'other',   label:'Update',      color:'var(--muted)',        bg:'var(--bg-soft)',          icon:'dot' },
};

function classifySignal(e) {
  const t = (e.title || '').toLowerCase();
  const c = (e.category || '').toLowerCase();
  if (/lawsuit|class action|investig|bankrupt|deficien|material weakness|noncompli|delist|fraud|wind-down|closure|\bclos(e|ing|ure)|downgrad|distress|recall|probe/.test(t) || c === 'regulatory' || c === 'closure') return SIGNALS.risk;
  if (/acqui|merger|buyout|takeover|\bipo\b|sale-leaseback|divestit|recapitaliz|\bbid\b|spin-?off/.test(t) || c === 'ma') return SIGNALS.ma;
  if (/earning|revenue|q[1-4]\b|quarter|fiscal|dividend|guidance|senior notes|refinanc|buyback|repurchase/.test(t) || c === 'earnings') return SIGNALS.earn;
  if (/\bopen(s|ing|ed)?\b|expansion|expand|new store|new location|grand opening|milestone|launch|enters?\b|store count/.test(t) || c === 'store-move') return SIGNALS.growth;
  if (/partner|integration|financing|credit card|bnpl|co-?brand/.test(t) || c === 'partnership' || c === 'financing' || c === 'bnpl') return SIGNALS.partner;
  if (/\bceo\b|president|chair(man)?\b|board\b|appoint|succession|\bhire|promot|named/.test(t) || c === 'leadership') return SIGNALS.leader;
  return SIGNALS.other;
}

function entityLabel(e) {
  const p = (e.partner || '').trim();
  if (p && PAGE_MAP[p]) return PAGE_MAP[p].title;
  const c = (e.competitor || '').trim();
  if (c && PAGE_MAP[c]) return PAGE_MAP[c].title;
  return '';
}

function fmtShort(iso) {
  if (!iso) return '';
  return new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function SigIcon({ name }) {
  const a = { viewBox: '0 0 16 16', width: 13, height: 13, fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round', className: 'sig-ic' };
  let kids;
  switch (name) {
    case 'growth':  kids = <g><path d="M2.5 11 L6.5 7 L9 9.5 L13.5 4.5" /><path d="M10 4.5 H13.5 V8" /></g>; break;
    case 'risk':    kids = <g><path d="M8 2.8 L14 12.8 H2 Z" /><path d="M8 6.4 V9.2" /><circle cx="8" cy="11" r="0.7" fill="currentColor" stroke="none" /></g>; break;
    case 'bars':    kids = <g><path d="M2.5 13 H13.5" /><path d="M4.5 13 V9" /><path d="M8 13 V5.5" /><path d="M11.5 13 V7.5" /></g>; break;
    case 'link':    kids = <g><circle cx="5" cy="8" r="2.2" /><circle cx="11" cy="8" r="2.2" /><path d="M7.2 8 H8.8" /></g>; break;
    case 'person':  kids = <g><circle cx="8" cy="5.4" r="2.3" /><path d="M3.7 13 a4.3 4.3 0 0 1 8.6 0" /></g>; break;
    default:        kids = <circle cx="8" cy="8" r="2.3" fill="currentColor" stroke="none" />;
  }
  return <svg {...a}>{kids}</svg>;
}

function SignalChip({ sig }) {
  return (
    <span className="sig-chip" style={{ color: sig.color, background: sig.bg }}>
      <SigIcon name={sig.icon} /><span>{sig.label}</span>
    </span>
  );
}

// ─── Needs-attention board (triage-first landing) ─────────────────────────
function NeedsAttention({ fm, navigateTo }) {
  const start = (fm && (fm.window_start || fm.date)) || '';
  const end = (fm && (fm.window_end || fm.date)) || '';
  const inWindow = (e) => (!start || !end || !e.date) ? true : (e.date >= start && e.date <= end);
  const high = EVENT_PAGES.filter(e => e.significance === 'high' && inWindow(e))
    .sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  if (high.length === 0) return null;
  const show = high.slice(0, 6);
  return (
    <div className="needs-attn">
      <div className="needs-attn-head">
        <span className="na-eyebrow">Needs attention</span>
        <span className="na-meta">{high.length} high-impact this window</span>
      </div>
      <div className="na-grid">
        {show.map(e => {
          const sig = classifySignal(e);
          const who = entityLabel(e);
          return (
            <div key={e.slug} className="na-card" data-sig={sig.key} style={{ borderLeftColor: sig.color }} onClick={() => navigateTo(e.slug)}>
              <div className="na-card-top">
                <SignalChip sig={sig} />
                {who && <span className="na-who">{who}</span>}
                <span className="na-date">{fmtShort(e.date)}</span>
              </div>
              <div className="na-title">{e.title}</div>
              {e.significance_reason && (
                <div className="na-rt"><span className="na-rt-label">Read-through</span>{e.significance_reason}</div>
              )}
            </div>
          );
        })}
      </div>
      {high.length > show.length && <div className="na-more">+{high.length - show.length} more high-impact events in the briefing below</div>}
    </div>
  );
}

// ─── Orientation card (first-run usage guide) ───────────────────────────────
function OrientationCard() {
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem('snap_wiki_orient_dismissed') === '1'; } catch (e) { return false; }
  });
  if (dismissed) return null;
  const close = () => {
    try { localStorage.setItem('snap_wiki_orient_dismissed', '1'); } catch (e) {}
    setDismissed(true);
  };
  return (
    <div className="orient">
      <button className="orient-close" onClick={close} aria-label="Dismiss">×</button>
      <div className="orient-eyebrow">Start here</div>
      <div className="orient-title">Your weekly read on the managed-account portfolio</div>
      <div className="orient-steps">
        <div className="orient-step">
          <span className="orient-num">1</span>
          <div><strong>Read the briefing</strong><p>Competitor moves, high-impact events, and SAE activity for the current window are laid out below.</p></div>
        </div>
        <div className="orient-step">
          <span className="orient-num">2</span>
          <div><strong>Browse the portfolio</strong><p>Use the left rail to open any SAE book, industry vertical, or opportunity pipeline.</p></div>
        </div>
        <div className="orient-step">
          <span className="orient-num">3</span>
          <div><strong>Search or ask</strong><p>Find any partner, event, or source from search — or use Ask Claude for analysis across the wiki.</p></div>
        </div>
      </div>
    </div>
  );
}

// ─── Wiki Page ───────────────────────────────────────────────────────────────
function Breadcrumb({ navHistory, activeSlug, goBack, goHome }) {
  if (!navHistory || navHistory.length === 0) return null;
  const crumbs = navHistory.map(slug => {
    const p = PAGE_MAP[slug];
    return { slug, label: p ? (p.title || slug) : slug };
  });
  const current = PAGE_MAP[activeSlug];
  return (
    <nav className="breadcrumb">
      <button className="breadcrumb-item" onClick={goHome}>Briefing</button>
      {crumbs.map((c, i) => (
        <Fragment key={c.slug}>
          <span className="breadcrumb-sep">/</span>
          <button className="breadcrumb-item" onClick={() => {
            for (let j = crumbs.length - 1; j >= i; j--) goBack();
          }}>{c.label.length > 30 ? c.label.slice(0, 28) + '…' : c.label}</button>
        </Fragment>
      ))}
      <span className="breadcrumb-sep">/</span>
      <span className="breadcrumb-current">{current ? (current.title.length > 35 ? current.title.slice(0, 33) + '…' : current.title) : activeSlug}</span>
    </nav>
  );
}

// ─── Entity profile (partner · competitor · SAE) ─────────────────────────────
function cleanRef(s) { return (s || '').replace(/\[\[|\]\]/g, '').trim(); }

function eventsForEntity(page) {
  let evs = [];
  if (page.type === 'partner') evs = EVENT_PAGES.filter(e => cleanRef(e.partner) === page.slug);
  else if (page.type === 'competitor') evs = EVENT_PAGES.filter(e => cleanRef(e.competitor) === page.slug);
  else if (page.type === 'sae') evs = EVENT_PAGES.filter(e => cleanRef(e.sae) === page.slug);
  return evs.slice().sort((a, b) => (b.date || '').localeCompare(a.date || ''));
}

function fmtLong(iso) {
  if (!iso) return '—';
  return new Date(iso + 'T12:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
function relativeAge(iso) {
  if (!iso) return '';
  const days = Math.round((Date.now() - new Date(iso + 'T12:00:00')) / 86400000);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30) return days + 'd ago';
  if (days < 365) return Math.round(days / 30) + 'mo ago';
  return Math.round(days / 365) + 'y ago';
}

function StatCell({ label, children }) {
  return (
    <div className="stat-cell">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{children}</div>
    </div>
  );
}

function EntityTimeline({ events, navigateTo }) {
  const [showAll, setShowAll] = useState(false);
  const [sig, setSig] = useState('all');
  if (!events.length) return null;
  const counts = {};
  events.forEach(e => { const k = classifySignal(e).key; if (k !== 'other') counts[k] = (counts[k] || 0) + 1; });
  const sigKeys = ['growth', 'ma', 'partner', 'earn', 'risk', 'leader'].filter(k => counts[k]);
  const filtered = sig === 'all' ? events : events.filter(e => classifySignal(e).key === sig);
  const shown = showAll ? filtered : filtered.slice(0, 8);
  return (
    <div style={{ display: 'contents' }}>
      {sigKeys.length >= 2 && (
        <div className="filter-bar">
          <span className="filter-bar-label">Filter</span>
          <button className={'filter-chip fc-all' + (sig === 'all' ? ' active' : '')} onClick={() => setSig('all')}>
            <span>All</span><span className="fc-n">{events.length}</span>
          </button>
          {sigKeys.map(k => {
            const s = SIGNALS[k];
            const on = sig === k;
            return (
              <button key={k} className={'filter-chip' + (on ? ' active' : '')} style={on ? { background: s.color } : null} onClick={() => setSig(on ? 'all' : k)}>
                <span className="fc-dot" style={{ background: s.color }} /><span>{s.label}</span><span className="fc-n">{counts[k]}</span>
              </button>
            );
          })}
        </div>
      )}
      <div className="timeline">
        {shown.map(e => {
          const s = classifySignal(e);
          const d = e.date ? new Date(e.date + 'T12:00:00') : null;
          return (
            <div key={e.slug} className="tl-item">
              <div className="tl-rail">
                <span className="tl-date">{d ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}</span>
                {d && <span className="tl-year">{d.getFullYear()}</span>}
              </div>
              <div className="tl-body">
                <span className="tl-dot" style={{ borderColor: s.color }} />
                <div className="tl-card" onClick={() => navigateTo(e.slug)}>
                  <div className="tl-top">
                    <SignalChip sig={s} />
                    {e.significance === 'high' && <span className="tl-sig-high" title="High impact" />}
                  </div>
                  <div className="tl-title">{e.title}</div>
                  {e.significance_reason && <div className="tl-rt">{e.significance_reason}</div>}
                </div>
              </div>
            </div>
          );
        })}
        {filtered.length > 8 && (
          <button className="back-btn" style={{ marginLeft: 68 }} onClick={() => setShowAll(s => !s)}>
            {showAll ? 'Show fewer' : 'Show all ' + filtered.length + ' events'}
          </button>
        )}
      </div>
    </div>
  );
}

function RelatedChip({ page, navigateTo }) {
  return (
    <div className="related-chip" onClick={() => navigateTo(page.slug)}>
      <span className="rc-type">{TYPE_LABELS[page.type] || page.type}</span>
      <span className="rc-name">{page.title || page.slug}</span>
    </div>
  );
}

function EntityProfile({ page, navigateTo }) {
  if (!['partner', 'competitor', 'sae'].includes(page.type)) return null;
  const events = eventsForEntity(page);
  const highCount = events.filter(e => e.significance === 'high').length;
  const last = events[0];

  // Related items
  let related = [];
  if (page.type === 'partner') {
    const saeSlug = cleanRef(page.sae);
    const sae = saeSlug && PAGE_MAP[saeSlug] ? PAGE_MAP[saeSlug] : null;
    const seg = cleanRef(page.segment);
    const peers = PARTNER_PAGES.filter(p => p.slug !== page.slug && cleanRef(p.segment) === seg && seg).slice(0, 6);
    related = [
      sae ? { title: 'SAE owner', items: [sae] } : null,
      peers.length ? { title: 'Same segment', items: peers } : null,
    ].filter(Boolean);
  } else if (page.type === 'competitor') {
    const peers = COMPETITOR_PAGES.filter(p => p.slug !== page.slug).slice(0, 6);
    related = peers.length ? [{ title: 'Other competitors', items: peers }] : [];
  } else if (page.type === 'sae') {
    const owned = PARTNER_PAGES.filter(p => cleanRef(p.sae) === page.slug);
    const byActivity = owned.map(p => ({ p, n: EVENT_PAGES.filter(e => cleanRef(e.partner) === p.slug).length }))
      .sort((a, b) => b.n - a.n).map(x => x.p).slice(0, 8);
    related = byActivity.length ? [{ title: 'Partners in book', items: byActivity }] : [];
  }

  const ownedCount = page.type === 'sae' ? PARTNER_PAGES.filter(p => cleanRef(p.sae) === page.slug).length : 0;
  const saeSlug = cleanRef(page.sae);
  const parent = (page.parent || '').replace(/\[\[|\]\]/g, '').trim();
  const showParent = parent && parent !== 'null' && parent.toLowerCase() !== (page.title || '').toLowerCase();

  return (
    <div className="entity-profile">
      <div className="stat-block">
        {page.type === 'partner' && page.segment && <StatCell label="Segment">{cleanRef(page.segment)}</StatCell>}
        {page.type === 'partner' && saeSlug && PAGE_MAP[saeSlug] && (
          <div className="stat-cell">
            <div className="stat-label">SAE Owner</div>
            <div className="stat-value is-link" onClick={() => navigateTo(saeSlug)}>{PAGE_MAP[saeSlug].title}</div>
          </div>
        )}
        {page.type === 'partner' && page.tier && <StatCell label="Tier">{page.tier}</StatCell>}
        {page.type === 'competitor' && page.ticker && <StatCell label="Ticker">{page.ticker}</StatCell>}
        {page.type === 'competitor' && page.category && <StatCell label="Category">{page.category}</StatCell>}
        {(page.type === 'partner' || page.type === 'competitor') && showParent && <StatCell label="Parent">{parent}</StatCell>}
        {page.type === 'sae' && <StatCell label="Partners">{ownedCount}</StatCell>}
        <StatCell label="Events Tracked">{events.length}</StatCell>
        {highCount > 0 && <div className="stat-cell"><div className="stat-label">High-impact</div><div className="stat-value" style={{ color: 'var(--snap-warning)' }}>{highCount}</div></div>}
        <div className="stat-cell">
          <div className="stat-label">Last Activity</div>
          <div className="stat-value">{last ? fmtLong(last.date) : '—'}<span className="stat-sub">{last ? relativeAge(last.date) : 'no events tracked'}</span></div>
        </div>
      </div>

      {events.length > 0 && (
        <div style={{ display: 'contents' }}>
          <div className="entity-section-label">Activity timeline <span className="esl-count">{events.length} events</span></div>
          <EntityTimeline events={events} navigateTo={navigateTo} />
        </div>
      )}

      {related.length > 0 && (
        <div className="related-panel">
          <div className="entity-section-label">Related</div>
          <div className="related-grid">
            {related.map((col, i) => (
              <div key={i}>
                <div className="related-col-title">{col.title}</div>
                <div className="related-chips">
                  {col.items.map(it => <RelatedChip key={it.slug} page={it} navigateTo={navigateTo} />)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {events.length > 0 && <hr className="entity-divider" />}
    </div>
  );
}

function WikiPage({ page, navigateTo, onBack, isEdition, navHistory, goHome }) {
  const rendered = useMemo(() => renderMarkdown(page.content), [page.slug]);
  const onContentRef = useCallback((el) => {
    if (!el) return;
    fixHeadingIds(el);
    el.addEventListener('click', (e) => {
      const wl = e.target.closest('.wikilink');
      if (wl) { const slug = wl.getAttribute('data-slug') || wl.textContent.trim(); if (slug && PAGE_MAP[slug]) { e.preventDefault(); navigateTo(slug); } return; }
      const anchor = e.target.closest('a[href^="#"]');
      if (anchor) {
        const href = anchor.getAttribute('href') || ''; if (href.length < 2) return;
        const id = href.slice(1);
        let target = document.getElementById(id);
        if (!target) { for (const h of el.querySelectorAll('h1,h2,h3,h4,h5,h6')) { if (slugifyHeading(h.textContent) === id) { target = h; break; } } }
        if (!target) { for (const node of el.querySelectorAll('[id]')) { if (node.id.includes(id) || id.includes(node.id)) { target = node; break; } } }
        if (target) { e.preventDefault(); target.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
      }
    });
  }, [navigateTo]);

  const isEntity = ['partner', 'competitor', 'sae'].includes(page.type);
  const bodyHtml = useMemo(() => {
    let html = rendered.bodyHtml;
    if (isEntity) { html = html.replace(/<h1[^>]*>.*?<\/h1>/, ''); return html; }
    if (!isEdition) return html;
    html = html.replace(/<h1[^>]*>.*?<\/h1>/, '');
    const emMatch = html.match(/^(\s*<p><em>Prepared for.*?<\/em><\/p>)/);
    if (emMatch) html = html.replace(emMatch[0], '');
    const countsMatch = html.match(/^(\s*<p><strong>\d+<\/strong>.*?<\/p>)/);
    if (countsMatch) html = html.replace(countsMatch[0], '');
    return html;
  }, [rendered.bodyHtml, isEdition, isEntity]);

  return (
    <div className="main-content">
      {navHistory && navHistory.length > 0 ? (
        <Breadcrumb navHistory={navHistory} activeSlug={page.slug} goBack={onBack} goHome={goHome} />
      ) : onBack ? (
        <nav className="page-nav"><button className="back-btn" onClick={onBack}>{'←'} Back to briefing</button></nav>
      ) : null}
      {isEdition ? <EditionHeader fm={rendered.fm} /> : <PageHeader page={page} />}
      {isEntity && <EntityProfile page={page} navigateTo={navigateTo} />}
      {isEdition && <ExecSummary fm={rendered.fm} />}
      {isEdition && <NeedsAttention fm={rendered.fm} navigateTo={navigateTo} />}
      {isEdition && <OrientationCard />}
      <SafeHTML className="md-content" html={bodyHtml} onRef={onContentRef} />
      <div className="footer-note">Competitor Intelligence · Snap Finance</div>
    </div>
  );
}

// ─── Command palette (Cmd / Ctrl-K) ──────────────────────────────────────────
const PALETTE_GROUP_ORDER = ['partner', 'competitor', 'sae', 'edition', 'event', 'source', 'opportunity-list'];
function CmdIcon({ type }) {
  const a = { viewBox: '0 0 16 16', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round' };
  switch (type) {
    case 'partner': return <svg {...a}><path d="M3 13V6l5-3 5 3v7" /><path d="M6.5 13v-3h3v3" /></svg>;
    case 'competitor': return <svg {...a}><circle cx="8" cy="8" r="5.5" /><path d="M8 5v3l2 1.5" /></svg>;
    case 'sae': return <svg {...a}><circle cx="8" cy="5.4" r="2.3" /><path d="M3.7 13a4.3 4.3 0 0 1 8.6 0" /></svg>;
    case 'edition': return <svg {...a}><rect x="3" y="2.5" width="10" height="11" rx="1.5" /><path d="M5.5 6h5M5.5 8.5h5M5.5 11h3" /></svg>;
    case 'event': return <svg {...a}><rect x="2.5" y="3.5" width="11" height="10" rx="1.5" /><path d="M2.5 6.5h11M5.5 2v3M10.5 2v3" /></svg>;
    default: return <svg {...a}><path d="M8 2.5v11M2.5 8h11" /></svg>;
  }
}

function loadRecents() {
  try { return JSON.parse(localStorage.getItem('snap_wiki_recent') || '[]'); } catch (e) { return []; }
}
function pushRecent(slug) {
  try {
    const r = loadRecents().filter(s => s !== slug);
    r.unshift(slug);
    localStorage.setItem('snap_wiki_recent', JSON.stringify(r.slice(0, 6)));
  } catch (e) {}
}

function CommandPalette({ open, onClose, navigateTo, setActiveView }) {
  const [q, setQ] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  useEffect(() => { if (open) { setQ(''); setActive(0); setTimeout(() => inputRef.current?.focus(), 30); } }, [open]);

  const flat = useMemo(() => {
    const items = [];
    const query = q.trim();
    if (!query) {
      const recents = loadRecents().map(s => PAGE_MAP[s]).filter(Boolean);
      if (recents.length) { items.push({ header: 'Recent' }); recents.forEach(p => items.push({ page: p })); }
      items.push({ header: 'Go to' });
      items.push({ action: 'competitors', title: 'Competitor Watch', icon: 'event' });
      items.push({ action: 'trends', title: 'Trend Analysis', icon: 'event' });
      items.push({ action: 'ask', title: 'Ask Claude', icon: 'sae' });
      return items;
    }
    const results = searchPages(query);
    const groups = {};
    results.forEach(p => { (groups[p.type] = groups[p.type] || []).push(p); });
    const order = PALETTE_GROUP_ORDER.filter(t => groups[t]).concat(Object.keys(groups).filter(t => !PALETTE_GROUP_ORDER.includes(t)));
    order.forEach(t => {
      items.push({ header: pluralLabel(t) });
      groups[t].slice(0, 6).forEach(p => items.push({ page: p }));
    });
    return items;
  }, [q, open]);

  const selectable = flat.map((it, i) => (it.header ? -1 : i)).filter(i => i >= 0);
  const clampActive = (idx) => { const pos = selectable.indexOf(idx); return pos >= 0 ? idx : (selectable[0] ?? 0); };

  useEffect(() => { if (selectable.length && !selectable.includes(active)) setActive(selectable[0]); }, [flat]);

  const choose = (it) => {
    if (it.page) { pushRecent(it.page.slug); setActiveView('page'); navigateTo(it.page.slug); }
    else if (it.action === 'edition') { setActiveView('page'); navigateTo(LATEST_EDITION_SLUG); }
    else if (it.action) { setActiveView(it.action); }
    onClose();
  };

  const onKey = (e) => {
    if (e.key === 'Escape') { onClose(); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); const pos = selectable.indexOf(active); setActive(selectable[Math.min(selectable.length - 1, pos + 1)] ?? active); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); const pos = selectable.indexOf(active); setActive(selectable[Math.max(0, pos - 1)] ?? active); }
    else if (e.key === 'Enter') { e.preventDefault(); const it = flat[active]; if (it) choose(it); }
  };

  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector('.cmdk-item.active');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [active]);

  if (!open) return null;
  return (
    <div className="cmdk-overlay" onMouseDown={onClose}>
      <div className="cmdk" onMouseDown={e => e.stopPropagation()}>
        <div className="cmdk-input-row">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5 14 14" /></svg>
          <input ref={inputRef} className="cmdk-input" placeholder="Search partners, competitors, SAEs, events…" value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKey} />
          <span className="cmdk-kbd">ESC</span>
        </div>
        <div className="cmdk-results" ref={listRef}>
          {flat.length === 0 ? (
            <div className="cmdk-empty">No matches for “{q}”</div>
          ) : flat.map((it, i) => it.header ? (
            <div key={'h' + i} className="cmdk-group-label">{it.header}</div>
          ) : (
            <div key={(it.page && it.page.slug) || it.action || i} className={'cmdk-item' + (i === active ? ' active' : '')}
                 onMouseEnter={() => setActive(i)} onClick={() => choose(it)}>
              <span className="cmdk-ic"><CmdIcon type={it.page ? it.page.type : it.icon} /></span>
              <span className="cmdk-texts">
                <span className="cmdk-title">{it.page ? (it.page.title || it.page.slug) : it.title}</span>
                {it.page && <span className="cmdk-sub">{TYPE_LABELS[it.page.type] || it.page.type}{it.page.segment ? ' · ' + cleanRef(it.page.segment) : ''}{it.page.ticker ? ' · ' + it.page.ticker : ''}</span>}
              </span>
              {it.page && it.page.date && <span className="cmdk-date">{it.page.date}</span>}
            </div>
          ))}
        </div>
        <div className="cmdk-foot">
          <span><span className="cf-k">↑↓</span> navigate</span>
          <span><span className="cf-k">↵</span> open</span>
          <span><span className="cf-k">esc</span> close</span>
        </div>
      </div>
    </div>
  );
}

function MobileBar({ onMenu, openPalette }) {
  return (
    <div className="mobile-bar">
      <button className="mb-burger" onClick={onMenu} aria-label="Menu"><span /><span /><span /></button>
      <div className="mb-brand">Snap Finance<small>MANAGED ACCOUNTS</small></div>
      <button className="mb-search" onClick={openPalette} aria-label="Search">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5 14 14" /></svg>
      </button>
    </div>
  );
}

// ─── App ─────────────────────────────────────────────────────────────────────
function App() {
  const [activeView, setActiveView] = useState('competitors');
  const [activeSlug, setActiveSlug] = useState(LATEST_EDITION_SLUG);
  const [navHistory, setNavHistory] = useState([]);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); setPaletteOpen(o => !o); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const navigateTo = useCallback((slug) => {
    if (activeView === 'industry') { setActiveSlug(slug); return; }
    if (!PAGE_MAP[slug]) return;
    pushRecent(slug);
    setNavOpen(false);
    setNavHistory(h => activeSlug ? [...h, activeSlug] : h);
    setActiveSlug(slug);
    setActiveView('page');
    const main = document.querySelector('.main-content');
    if (main) main.scrollTo({ top: 0, behavior: 'smooth' });
  }, [activeSlug, activeView]);

  const goBack = useCallback(() => {
    if (navHistory.length > 0) {
      setActiveSlug(navHistory[navHistory.length - 1]);
      setNavHistory(h => h.slice(0, -1));
      setActiveView('page');
    } else if (LATEST_EDITION_SLUG) {
      setActiveSlug(LATEST_EDITION_SLUG);
      setActiveView('page');
    } else {
      setActiveView('competitors');
    }
    const main = document.querySelector('.main-content');
    if (main) main.scrollTo({ top: 0, behavior: 'smooth' });
  }, [navHistory]);

  let content;
  if (activeView === 'ask') {
    content = <AskClaudePanel />;
  } else if (activeView === 'trends') {
    content = <TrendView />;
  } else if (activeView === 'competitors') {
    content = <CompetitorView navigateTo={(slug) => { setActiveView('page'); navigateTo(slug); }} />;
  } else if (activeView === 'industry') {
    content = <IndustryView industryKey={activeSlug} navigateTo={(slug) => { setActiveView('page'); navigateTo(slug); }} />;
  } else {
    const page = PAGE_MAP[activeSlug];
    if (!page) {
      content = <div className="main-content"><div className="empty-state"><h2>No pages found</h2><p>Run the weekly refresh to populate the wiki.</p></div></div>;
    } else {
      const isEdition = page.type === 'edition';
      const showBack = navHistory.length > 0;
      const goHome = () => { setNavHistory([]); setActiveView('competitors'); };
      content = <WikiPage page={page} navigateTo={navigateTo} onBack={showBack ? goBack : null} isEdition={isEdition} navHistory={navHistory} goHome={goHome} />;
    }
  }

  return (
    <div style={{ display: 'contents' }}>
      <MobileBar onMenu={() => setNavOpen(o => !o)} openPalette={() => setPaletteOpen(true)} />
      <div className={'app-layout' + (navOpen ? ' nav-open' : '')}>
        <div className="scrim" onClick={() => setNavOpen(false)} />
        <Sidebar activeView={activeView} setActiveView={(v) => { setActiveView(v); setNavOpen(false); }} activeSlug={activeSlug} navigateTo={navigateTo} openPalette={() => setPaletteOpen(true)} />
        {content}
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} navigateTo={navigateTo} setActiveView={setActiveView} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
