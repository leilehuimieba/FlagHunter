/* global React, fmt, t */
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
    { id: 'memory',    tk: 'nav.memory',    icon: '◎' },
    { id: 'logs',      tk: 'nav.logs',      icon: '▤' },
  ]},
  { groupKey: 'nav.system', items: [
    { id: 'settings',  tk: 'nav.settings',  icon: '⛭' },
  ]},
];

function Sidebar({ route, onNav }) {
  const [connection, setConnection] = useStateS(() => (
    window.API?.getConnectionState
      ? window.API.getConnectionState()
      : { status: 'connecting', isLive: false, via: 'boot' }
  ));
  const [statusMeta, setStatusMeta] = useStateS({ runtime: '—', version: '—' });

  useEffectS(() => {
    let cancelled = false;

    async function loadStatus() {
      if (!window.API?.getStatus) return;
      const data = await window.API.getStatus();
      if (!cancelled && data) {
        setStatusMeta({
          runtime: data.runtime || '—',
          version: data.version || '—',
        });
      }
    }

    loadStatus();
    return () => { cancelled = true; };
  }, []);

  useEffectS(() => {
    const handler = async (e) => {
      const nextConnection = (
        e.detail?.connection
        || (window.API?.getConnectionState
          ? window.API.getConnectionState()
          : {
              status: e.detail?.type === 'connected' ? 'connected' : 'disconnected',
              isLive: e.detail?.type === 'connected',
            })
      );
      setConnection(nextConnection);
      if (nextConnection.status === 'connected' && window.API?.getStatus) {
        const data = await window.API.getStatus();
        if (data) {
          setStatusMeta({
            runtime: data.runtime || '—',
            version: data.version || '—',
          });
        }
      }
    };
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
            <span className="val">{statusMeta.runtime || '—'}</span>
          </div>
          <span className={`conn-badge ${connectionTone(connection)}`}>
            {connectionLabel(connection)}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--fg-3)', padding: '0 4px' }}>
          <span>{t('sidebar.build')} · {statusMeta.version || '—'}</span>
          <span style={{ color: connection?.status === 'connected' ? 'var(--accent)' : 'var(--fg-3)' }}>
            {connection?.status === 'connected' ? '●' : '○'} {connectionMetaLabel(connection)}
          </span>
        </div>
      </div>
    </aside>
  );
}

function connectionLabel(connection) {
  return t(`conn.${connection?.status || 'connecting'}`);
}

function connectionMetaLabel(connection) {
  return connection?.status === 'connected' ? t('sidebar.healthy') : connectionLabel(connection);
}

function connectionTone(connection) {
  const status = connection?.status || 'connecting';
  if (['connected', 'degraded', 'reconnecting', 'connecting', 'disconnected'].includes(status)) {
    return status;
  }
  return 'connecting';
}

const CRUMBS_KEYS = {
  dashboard:        ['brand.tag', 'nav.dashboard'],
  tasks:            ['brand.tag', 'nav.tasks'],
  'tasks/detail':   ['brand.tag', 'nav.tasks', '_task'],
  traces:           ['brand.tag', 'nav.traces'],
  'traces/detail':  ['brand.tag', 'nav.traces', '_run_002'],
  knowledge:        ['brand.tag', 'nav.knowledge'],
  'knowledge/detail':['brand.tag', 'nav.knowledge', '_doc_002'],
  memory:           ['brand.tag', 'nav.memory'],
  logs:             ['brand.tag', 'nav.logs'],
  settings:         ['brand.tag', 'nav.settings'],
};

function shortText(text, limit = 96) {
  const raw = String(text || '').trim();
  if (!raw) return '—';
  const compact = raw.replace(/\s+/g, ' ');
  return compact.length > limit ? compact.slice(0, limit - 3).trimEnd() + '...' : compact;
}

function shellLevel(level, source) {
  if (level === 'error') return 'err';
  if (level === 'warn' || (source || '').startsWith('verifier')) return 'warn';
  if ((source || '').startsWith('tool')) return 'info';
  return 'info';
}

function notifFromLog(entry) {
  if (!entry) return null;
  const message = entry.msg || entry.message || '';
  return {
    id: `log_${entry.id || `${entry.source}_${entry.t}`}`,
    t: entry.t || new Date().toISOString(),
    level: shellLevel(entry.level, entry.source),
    ttl: shortText(message, 92),
    sub: shortText([
      entry.source || 'log',
      entry.taskId && entry.taskId !== '—' ? entry.taskId : '',
      entry.runId && entry.runId !== '—' ? entry.runId : '',
    ].filter(Boolean).join(' · '), 80),
  };
}

function notifFromEvent(ev) {
  if (!ev) return null;
  if (ev.type === 'ping' || ev.type === 'heartbeat') return null;
  if (ev.type === 'log_line') {
    return notifFromLog({
      id: ev.id || `${ev.source || 'live'}_${ev.t || Date.now()}`,
      t: ev.t || new Date().toISOString(),
      level: ev.level || 'info',
      source: ev.source || 'live',
      msg: ev.message || ev.summary || ev.type,
      runId: ev.run_id || '—',
      taskId: ev.task_id || '—',
    });
  }
  const title = ev.title || ev.type || 'event';
  const summary = ev.summary || ev.message || ev.output || '';
  return {
    id: ev.id || `event_${ev.type || 'live'}_${ev.t || Date.now()}`,
    t: ev.t || new Date().toISOString(),
    level: shellLevel(ev.level, ev.source || ev.tool || ev.type),
    ttl: shortText(title, 92),
    sub: shortText(summary || [ev.tool, ev.task_id, ev.run_id].filter(Boolean).join(' · '), 96),
  };
}

function tickFromLog(entry) {
  if (!entry) return null;
  return {
    id: `tick_log_${entry.id || `${entry.source}_${entry.t}`}`,
    t: entry.t || new Date().toISOString(),
    who: entry.source || 'log',
    what: shortText(entry.msg || entry.message || '', 110),
    kind: entry.level === 'warn' || entry.level === 'error' ? 'warn' : 'tool',
  };
}

function tickFromEvent(ev) {
  if (!ev) return null;
  if (ev.type === 'ping' || ev.type === 'heartbeat') return null;
  if (ev.type === 'log_line') {
    return tickFromLog({
      id: ev.id || `${ev.source || 'live'}_${ev.t || Date.now()}`,
      t: ev.t || new Date().toISOString(),
      level: ev.level || 'info',
      source: ev.source || 'live',
      msg: ev.message || ev.summary || ev.type,
    });
  }
  return {
    id: `tick_event_${ev.id || `${ev.type || 'live'}_${ev.t || Date.now()}`}`,
    t: ev.t || new Date().toISOString(),
    who: ev.tool || ev.source || ev.task_id || 'live',
    what: shortText(ev.summary || ev.title || ev.message || ev.type || 'event', 110),
    kind: ev.type === 'task_status' || ev.level === 'warn' ? 'warn' : 'tool',
  };
}

function Topbar({ route, leaf, taskViewMode, onTaskViewModeChange }) {
  const [ticks, setTicks] = useStateS([]);
  const [notifs, setNotifs] = useStateS([]);
  const [showNotif, setShowNotif] = useStateS(false);
  const [hasNew, setHasNew] = useStateS(false);
  const bellRef = useRefS(null);
  const [lang, setLangState] = useStateS(window.LANG);
  const [connection, setConnection] = useStateS(() => (
    window.API?.getConnectionState
      ? window.API.getConnectionState()
      : { status: 'connecting', isLive: false, via: 'boot' }
  ));

  useEffectS(() => {
    if (!window.API?.getLogs) return undefined;
    let cancelled = false;
    window.API.getLogs().then(data => {
      if (cancelled || !Array.isArray(data)) return;
      const sorted = data.slice().sort((a, b) => Date.parse(b.t || 0) - Date.parse(a.t || 0));
      setTicks(sorted.map(tickFromLog).filter(Boolean).slice(0, 8));
      setNotifs(sorted.map(notifFromLog).filter(Boolean).slice(0, 5));
    });
    return () => { cancelled = true; };
  }, []);

  useEffectS(() => {
    if (!window.API?.subscribeEvents) return undefined;
    return window.API.subscribeEvents(ev => {
      const tick = tickFromEvent(ev);
      if (tick) {
        setTicks(prev => [tick, ...prev.filter(item => item.id !== tick.id)].slice(0, 8));
      }
      const notif = notifFromEvent(ev);
      if (notif) {
        setNotifs(prev => [notif, ...prev.filter(item => item.id !== notif.id)].slice(0, 5));
        if (!showNotif) setHasNew(true);
      }
    });
  }, [showNotif]);

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

  useEffectS(() => {
    const handler = (e) => setConnection(
      e.detail?.connection
      || (window.API?.getConnectionState
        ? window.API.getConnectionState()
        : { status: e.detail?.type || 'connecting', isLive: e.detail?.type === 'connected' })
    );
    window.addEventListener('fh:connection', handler);
    return () => window.removeEventListener('fh:connection', handler);
  }, []);

  const crumbs = (CRUMBS_KEYS[route] || CRUMBS_KEYS.dashboard).map(k => {
    if (k.startsWith('_')) return leaf || k.slice(1);
    return t(k);
  });
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

      <button
        type="button"
        className="global-search"
        onClick={() => window.dispatchEvent(new CustomEvent('fh:toggle-cp'))}
        title="open command palette"
      >
        <span style={{ color: 'var(--fg-3)' }}>⌕</span>
        <span style={{ flex: 1 }}>{t('top.search')}</span>
        <span className="kbd">⌘ K</span>
      </button>

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

      {(route === 'tasks/detail' || route === 'tasks') && (
        <div className="task-view-toggle" aria-label="task detail view mode">
          <button
            type="button"
            className={`mode-btn ${taskViewMode !== 'analysis' ? 'active' : ''}`}
            onClick={() => onTaskViewModeChange && onTaskViewModeChange('conversation')}
          >
            {t('td.modeConversation')}
          </button>
          <button
            type="button"
            className={`mode-btn ${taskViewMode === 'analysis' ? 'active' : ''}`}
            onClick={() => onTaskViewModeChange && onTaskViewModeChange('analysis')}
          >
            {t('td.modeAnalysis')}
          </button>
        </div>
      )}

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
              <span>{t('top.notif')} · {notifs.length}</span>
              <span style={{ color: 'var(--fg-3)' }}>{connection?.status === 'connected' ? t('top.notifLive') : connectionLabel(connection)}</span>
            </div>
            <div className="list">
              {notifs.length === 0 && (
                <div className="row">
                  <span className="ico blue">◇</span>
                  <div className="body">
                    <div className="ttl">{t('top.notifEmpty')}</div>
                    <div className="sub">{connection?.status === 'connected' ? t('top.notifLive') : connectionLabel(connection)}</div>
                  </div>
                </div>
              )}
              {notifs.map(n => {
                const cls = { success: 'green', warn: 'amber', err: 'red', info: 'blue' }[n.level] || 'blue';
                const sym = { success: '✓', warn: '⚠', err: '✗', info: '◇' }[n.level] || '◇';
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
