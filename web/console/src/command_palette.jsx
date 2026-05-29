/* global React, t, ModeBadge, SubtypeBadge */
// ============================================================
// CommandPalette — ⌘K global command palette
// Triggered by Ctrl+K / ⌘K or the topbar ⌘ button.
// Dispatches fh:open-new-task / fh:settings-tab events.
// ============================================================

const { useState: uCP, useEffect: uCPE, useRef: uCPR } = React;

function currentConnectionState() {
  if (window.API?.getConnectionState) return window.API.getConnectionState();
  return {
    status: window.IS_LIVE ? 'connected' : 'disconnected',
    isLive: Boolean(window.IS_LIVE),
  };
}

function CommandPalette({ onClose, onNav }) {
  const [query, setQuery] = uCP('');
  const [sel, setSel] = uCP(0);
  const [recentTasks, setRecentTasks] = uCP([]);
  const [connection, setConnection] = uCP(() => currentConnectionState());
  const inputRef = uCPR(null);
  const getTasks = window.API?.getTasks;
  const tasksAvailable = ['connected', 'degraded'].includes(connection.status)
    && typeof getTasks === 'function';

  uCPE(() => { inputRef.current?.focus(); }, []);
  uCPE(() => { setSel(0); }, [query]);

  uCPE(() => {
    const handler = (e) => {
      setConnection(
        e.detail?.connection
        || currentConnectionState()
      );
    };
    window.addEventListener('fh:connection', handler);
    return () => window.removeEventListener('fh:connection', handler);
  }, []);

  uCPE(() => {
    let cancelled = false;

    async function loadRecentTasks() {
      if (tasksAvailable && typeof getTasks === 'function') {
        const data = await getTasks();
        if (!cancelled && Array.isArray(data)) {
          setRecentTasks(data.slice(0, 8));
          return;
        }
      }
      if (!cancelled) setRecentTasks([]);
    }

    loadRecentTasks();
    return () => { cancelled = true; };
  }, [getTasks, tasksAvailable]);

  // ── command definitions ──────────────────────────────────────
  const navCmds = [
    { id: 'go-dashboard', icon: '◇', label: () => t('nav.dashboard'), action: () => { onNav('dashboard'); onClose(); } },
    { id: 'go-tasks',     icon: '▸', label: () => t('nav.tasks'),     action: () => { onNav('tasks');     onClose(); } },
    { id: 'go-traces',    icon: '◈', label: () => t('nav.traces'),    action: () => { onNav('traces');    onClose(); } },
    { id: 'go-knowledge', icon: '◉', label: () => t('nav.knowledge'), action: () => { onNav('knowledge'); onClose(); } },
    { id: 'go-memory',    icon: '◎', label: () => t('nav.memory'),    action: () => { onNav('memory');    onClose(); } },
    { id: 'go-logs',      icon: '▤', label: () => t('nav.logs'),      action: () => { onNav('logs');      onClose(); } },
    { id: 'go-settings',  icon: '⛭', label: () => t('nav.settings'), action: () => { onNav('settings');  onClose(); } },
  ];

  const actionCmds = [
    {
      id: 'new-task', icon: '＋', iconCls: 'green',
      label: () => t('cp.newTask'),
      action: () => {
        onNav('tasks'); onClose();
        setTimeout(() => window.dispatchEvent(new CustomEvent('fh:open-new-task')), 80);
      },
    },
    {
      id: 'ctf-settings', icon: '⚑',
      label: () => t('cp.ctfSettings'),
      action: () => {
        onNav('settings'); onClose();
        setTimeout(() => window.dispatchEvent(new CustomEvent('fh:settings-tab', { detail: 'ctf' })), 80);
      },
    },
    {
      id: 'toggle-theme', icon: '◐',
      label: () => t('cp.toggleTheme'),
      action: () => { document.documentElement.classList.toggle('theme-light'); onClose(); },
    },
    {
      id: 'toggle-lang', icon: '⇄',
      label: () => t('cp.toggleLang'),
      action: () => { window.setLang(window.LANG === 'en' ? 'zh' : 'en'); onClose(); },
    },
  ];

  const recentCmds = (recentTasks || []).slice(0, 5).map(tk => ({
    id:      'task-' + tk.id,
    icon:    { running: '●', done: '✓', success: '✓', failed: '✗', stopped: '■', queued: '○' }[tk.status] || '·',
    iconCls: { running: 'amber', done: 'green', success: 'green', failed: 'red' }[tk.status] || '',
    task: tk,
    label:   () => tk.title || tk.id,
    keywords: () => `${tk.id || ''} ${tk.title || ''} ${tk.target || ''}`.toLowerCase(),
    sub:     [tk.id, tk.target].filter(Boolean).join(' · '),
    action:  () => { onNav(`tasks/${tk.id}`); onClose(); },
  }));

  const allCmds = [...navCmds, ...actionCmds, ...recentCmds];
  const q = query.trim().toLowerCase();
  const filtered = q ? allCmds.filter(c => {
    const text = [c.label?.() || '', c.sub || '', c.keywords?.() || ''].join(' ').toLowerCase();
    return text.includes(q);
  }) : allCmds;

  function exec(cmd) { if (cmd) cmd.action(); }

  function handleKey(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, filtered.length - 1)); }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setSel(s => Math.max(s - 1, 0)); }
    if (e.key === 'Enter')     { e.preventDefault(); exec(filtered[sel]); }
    if (e.key === 'Escape')    { onClose(); }
  }

  // ── item renderer ────────────────────────────────────────────
  function renderItem(cmd, idx) {
    return (
      <div
        key={cmd.id}
        className={'cp-item' + (idx === sel ? ' sel' : '')}
        onClick={() => exec(cmd)}
        onMouseEnter={() => setSel(idx)}
      >
        <span className={'cp-item-icon' + (cmd.iconCls ? ' ' + cmd.iconCls : '')}>{cmd.icon}</span>
        <span className="cp-item-label">{cmd.label()}</span>
        {cmd.task && (
          <span style={{ display: 'inline-flex', gap: 6, marginLeft: 8, alignItems: 'center' }}>
            <ModeBadge mode={cmd.task.mode} />
            <SubtypeBadge value={cmd.task.modeSubtype} />
          </span>
        )}
        {cmd.sub && <span className="cp-item-sub">{cmd.sub}</span>}
      </div>
    );
  }

  function renderList() {
    if (filtered.length === 0) {
      return React.createElement('div', { className: 'cp-empty' }, t('cp.empty'));
    }
    if (q) {
      return filtered.map((cmd, i) => renderItem(cmd, i));
    }
    const sections = [
      { key: 'nav',    label: t('cp.sec.nav'),    cmds: navCmds    },
      { key: 'action', label: t('cp.sec.action'), cmds: actionCmds },
      { key: 'recent', label: t('cp.sec.recent'), cmds: recentCmds },
    ].filter(s => s.cmds.length > 0);

    let idx = 0;
    return sections.map(sec =>
      React.createElement('div', { key: sec.key, className: 'cp-section' },
        React.createElement('div', { className: 'cp-sec-hd' }, sec.label),
        ...sec.cmds.map(cmd => renderItem(cmd, idx++))
      )
    );
  }

  return (
    <div className="cp-backdrop" onMouseDown={onClose}>
      <div className="cp" onMouseDown={e => e.stopPropagation()}>
        <div className="cp-head">
          <span className="cp-search-icon">⌕</span>
          <input
            ref={inputRef}
            className="cp-input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder={t('cp.placeholder')}
            autoComplete="off"
            spellCheck={false}
          />
          {query && (
            <button className="cp-clear" onClick={() => setQuery('')}>✕</button>
          )}
        </div>
        <div className="cp-list">{renderList()}</div>
        <div className="cp-footer">
          <span><kbd className="cp-kbd">↑↓</kbd>{t('cp.hint.nav')}</span>
          <span><kbd className="cp-kbd">↵</kbd>{t('cp.hint.confirm')}</span>
          <span><kbd className="cp-kbd">Esc</kbd>{t('cp.hint.close')}</span>
        </div>
      </div>
    </div>
  );
}

window.CommandPalette = CommandPalette;
