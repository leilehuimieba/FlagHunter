/* global React, MOCK, fmt, t */
// ============================================================
// Console Shell — sidebar + topbar + ticker + notif panel + language toggle
// ============================================================

const { useState: useStateS, useEffect: useEffectS, useRef: useRefS } = React;

const NAV = [
  { groupKey: 'nav.ops', items: [
    { id: 'dashboard', tk: 'nav.dashboard', icon: '◇' },
    { id: 'tasks',     tk: 'nav.tasks',     icon: '▸', badge: null },
    { id: 'traces',    tk: 'nav.traces',    icon: '◈' },
  ]},
  { groupKey: 'nav.data', items: [
    { id: 'knowledge', tk: 'nav.knowledge', icon: '◉' },
    { id: 'logs',      tk: 'nav.logs',      icon: '▤' },
  ]},
  { groupKey: 'nav.system', items: [
    { id: 'settings',  tk: 'nav.settings',  icon: '⛭' },
  ]},
];

function Sidebar({ route, onNav }) {
  const [isLive, setIsLive] = useStateS(window.IS_LIVE || false);

  useEffectS(() => {
    const handler = (e) => setIsLive(e.detail.type === 'connected');
    window.addEventListener('fh:connection', handler);
    return () => window.removeEventListener('fh:connection', handler);
  }, []);

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="logo">F<span style={{opacity:0.6}}>H</span></div>
        <div className="wordmark">
          <span className="name">FlagHunter</span>
          <span className="tag">{t('brand.tag')}</span>
        </div>
      </div>

      {NAV.map(group => (
        <div key={group.groupKey} className="nav-group">
          <div className="nav-label">{t(group.groupKey)}</div>
          {group.items.map(item => (
            <div
              key={item.id}
              className={`nav-item ${route.startsWith(item.id) ? 'active' : ''}`}
              onClick={() => onNav(item.id)}
            >
              <span className="icon">{item.icon}</span>
              <span>{t(item.tk)}</span>
              {item.badge && <span className="badge">{item.badge}</span>}
            </div>
          ))}
        </div>
      ))}

      <div className="sidebar-footer">
        <div className="runtime-badge">
          <span className="dot"></span>
          <div className="meta">
            <span className="lbl">{t('sidebar.runtime')}</span>
            <span className="val">LocalRuntime</span>
          </div>
          <span className={`conn-badge ${isLive ? 'live' : 'mock'}`}>
            {isLive ? t('sidebar.live') : t('sidebar.mock')}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--fg-3)', padding: '0 4px' }}>
          <span>{t('sidebar.build')} · 5f3a2c1</span>
          <span style={{ color: isLive ? 'var(--accent)' : 'var(--fg-3)' }}>
            {isLive ? '●' : '○'} {isLive ? t('sidebar.healthy') : 'offline'}
          </span>
        </div>
      </div>
    </aside>
  );
}

const CRUMBS_KEYS = {
  dashboard:        ['brand.tag', 'nav.dashboard'],
  tasks:            ['brand.tag', 'nav.tasks'],
  'tasks/detail':   ['brand.tag', 'nav.tasks', '_task_002'],
  traces:           ['brand.tag', 'nav.traces'],
  'traces/detail':  ['brand.tag', 'nav.traces', '_run_002'],
  knowledge:        ['brand.tag', 'nav.knowledge'],
  'knowledge/detail':['brand.tag', 'nav.knowledge', '_doc_002'],
  logs:             ['brand.tag', 'nav.logs'],
  settings:         ['brand.tag', 'nav.settings'],
};

function Topbar({ route }) {
  const [ticks, setTicks] = useStateS([]);
  const [showNotif, setShowNotif] = useStateS(false);
  const [hasNew, setHasNew] = useStateS(true);
  const bellRef = useRefS(null);
  const [lang, setLangState] = useStateS(window.LANG);

  useEffectS(() => {
    return window.LiveTicker.subscribe((t) => setTicks(t));
  }, []);

  useEffectS(() => {
    function onDoc(e) {
      if (bellRef.current && !bellRef.current.contains(e.target)) setShowNotif(false);
    }
    if (showNotif) document.addEventListener('click', onDoc);
    return () => document.removeEventListener('click', onDoc);
  }, [showNotif]);

  // Also refresh on lang change
  useEffectS(() => {
    const handler = () => setLangState(window.LANG);
    window.addEventListener('fh:lang', handler);
    return () => window.removeEventListener('fh:lang', handler);
  }, []);

  const crumbs = (CRUMBS_KEYS[route] || CRUMBS_KEYS.dashboard).map(k =>
    k.startsWith('_') ? k.slice(1) : t(k)
  );
  const showTicks = ticks.slice(0, 2);

  function toggleLang() {
    const next = window.LANG === 'en' ? 'zh' : 'en';
    window.setLang(next);
    setLangState(next);
  }

  return (
    <header className="topbar">
      <div className="crumbs">
        {crumbs.map((c, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span className="sep">/</span>}
            <span className={i === crumbs.length - 1 ? 'leaf' : ''}>{c}</span>
          </React.Fragment>
        ))}
      </div>

      <div className="global-search">
        <span style={{ color: 'var(--fg-3)' }}>⌕</span>
        <span style={{ flex: 1 }}>{t('top.search')}</span>
        <span className="kbd">⌘ K</span>
      </div>

      <div className="ticker">
        {showTicks.map(tk => (
          <div key={tk.id} className={`tick ${tk.kind === 'system' ? '' : tk.kind === 'tool' ? '' : 'warn'}`}>
            <span className="when">{fmt.hh(tk.t).slice(0,8)}</span>
            <span className="dot">▸</span>
            <span className="who">{tk.who}</span>
            <span className="what">{tk.what}</span>
          </div>
        ))}
      </div>

      <div className="top-actions" ref={bellRef}>
        <button
          className="lang-toggle"
          onClick={toggleLang}
          title="switch language / 切换语言"
        >
          <span className={lang === 'en' ? 'on' : ''}>EN</span>
          <span className="sep">|</span>
          <span className={lang === 'zh' ? 'on' : ''}>中</span>
        </button>
        <button className="icon-btn" title="command palette (Ctrl+K)" onClick={() => window.dispatchEvent(new CustomEvent('fh:toggle-cp'))}>⌘</button>
        <button className="icon-btn" title="theme" onClick={() => {
          const el = document.documentElement;
          el.classList.toggle('theme-light');
        }}>◐</button>
        <button
          className="icon-btn"
          onClick={(e) => { e.stopPropagation(); setShowNotif(s => !s); setHasNew(false); }}
          title="notifications"
        >
          <span style={{ fontSize: 14 }}>♪</span>
          {hasNew && <span className="bell-dot has-new"></span>}
        </button>
        <div style={{ width: 1, height: 18, background: 'var(--line-2)', margin: '0 4px' }}></div>
        <div style={{
          width: 28, height: 28, borderRadius: 4,
          background: 'linear-gradient(135deg, var(--bg-3), var(--bg-2))',
          border: '1px solid var(--line-2)',
          display: 'grid', placeItems: 'center', fontSize: 11, color: 'var(--fg-1)',
        }}>op</div>

        {showNotif && (
          <div className="notif-panel" onClick={(e)=>e.stopPropagation()}>
            <div className="head">
              <span>{t('top.notif')} · {MOCK.NOTIFICATIONS.length}</span>
              <span style={{ color: 'var(--fg-3)' }}>{t('top.markRead')}</span>
            </div>
            <div className="list">
              {MOCK.NOTIFICATIONS.map(n => {
                const cls = { success: 'green', warn: 'amber', err: 'red', info: 'blue' }[n.level] || '';
                const sym = { success: '✓', warn: '⚠', err: '✗', info: '◇' }[n.level] || '·';
                return (
                  <div key={n.id} className="row">
                    <span className={`ico ${cls}`}>{sym}</span>
                    <div className="body">
                      <div className="ttl">{n.ttl}</div>
                      <div className="sub">{n.sub}</div>
                    </div>
                    <span className="when">{fmt.since(n.t)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}

Object.assign(window, { Sidebar, Topbar });
