/* global React, MOCK, fmt, t */
// ============================================================
// Logs — table view + terminal tail view + detail drawer
// ============================================================

const { useState: uL, useEffect: uLE, useRef: uLR, useMemo: uLM } = React;

function LogsPage() {
  const [mode, setMode]   = uL('table');
  const [level, setLevel] = uL('all');
  const [src, setSrc]     = uL('all');
  const [run, setRun]     = uL('all');
  const [q, setQ]         = uL('');
  const [live, setLive]   = uL(true);
  const [picked, setPicked] = uL(null);
  const [appended, setAppended] = uL([]);
  const termRef = uLR(null);

  const LIVE_POOL = [
    ['info',  'tool.terminal', '[INFO] retrieved tuple via pg_sleep timing (Δ4.21s)'],
    ['debug', 'token_tracker', 'cumulative tokens=18,840 / 500,000'],
    ['info',  'tool.terminal', 'sqlmap: fetched column password_hash'],
    ['info',  'agent.observer','observation feed +1 · CHAR-based payload heuristic'],
    ['info',  'tool.terminal', 'sqlmap: row 15 retrieved · 4.17s'],
    ['warn',  'tool.terminal', 'sqlmap: timing variance Δ=±0.3s within tolerance'],
    ['info',  'rag', 'cache hit · postgres timing primitives (score 0.74)'],
    ['debug', 'runtime', 'pid=18472 alive · rss=42M'],
  ];
  uLE(() => {
    if (!live) return;
    let i = 0;
    const id = setInterval(() => {
      const [lv, source, msg] = LIVE_POOL[i % LIVE_POOL.length];
      i++;
      setAppended(prev => [{
        id: `live_${Date.now()}_${i}`,
        t: new Date().toISOString(),
        level: lv, source, msg, runId: 'run_002', taskId: 'task_002',
      }, ...prev].slice(0, 80));
    }, 2400);
    return () => clearInterval(id);
  }, [live]);

  uLE(() => {
    if (mode === 'terminal' && termRef.current) {
      termRef.current.scrollTop = termRef.current.scrollHeight;
    }
  }, [appended.length, mode]);

  const all = uLM(() => [...appended, ...MOCK.LOGS], [appended]);
  const filtered = uLM(() => all.filter(l => {
    if (level !== 'all' && l.level !== level) return false;
    if (src !== 'all' && !l.source.startsWith(src)) return false;
    if (run !== 'all' && l.runId !== run) return false;
    if (q && !(l.msg.toLowerCase().includes(q.toLowerCase()) || l.source.includes(q))) return false;
    return true;
  }), [all, level, src, run, q]);

  return (
    <div className="page" style={{ minHeight: 0 }}>
      <div className="page-h">
        <div>
          <div className="t">{t('lg.t')}</div>
          <div className="sub">{t('lg.sub', all.length, live ? t('lg.on') : t('lg.off'))}</div>
        </div>
        <div className="row">
          <span className="row gap-6" style={{ cursor: 'pointer', fontSize: 12 }} onClick={() => setLive(!live)}>
            <span className="muted">{t('lg.liveTail')}</span>
            <span className={`toggle ${live ? 'on' : ''}`}></span>
          </span>
          <button className="btn ghost">⬇ {t('c.export')}</button>
          <button className="btn ghost">{t('c.clearFilters')}</button>
        </div>
      </div>

      <Panel style={{ flex: 1 }}>
        <div className="log-toolbar">
          <div className="row gap-6">
            {[['table', t('lg.table')], ['terminal', t('lg.terminal')]].map(([m, lab]) => (
              <span key={m}
                className="filter-pill"
                style={mode === m ? { color: 'var(--accent)', borderColor: 'var(--accent-dim)', background: 'rgba(107,230,117,0.06)' } : {}}
                onClick={() => setMode(m)}>{lab}</span>
            ))}
          </div>
          <div style={{ width: 1, height: 16, background: 'var(--line-2)' }}></div>
          <div className="row gap-6">
            <span className="dim" style={{ fontSize: 10 }}>{t('lg.level')}</span>
            {['all', 'error', 'warn', 'info', 'debug'].map(l => (
              <span key={l} className={`filter-pill ${level === l ? 'on' : ''}`} onClick={() => setLevel(l)}>{t('flt.' + l)}</span>
            ))}
          </div>
          <div style={{ width: 1, height: 16, background: 'var(--line-2)' }}></div>
          <div className="row gap-6">
            <span className="dim" style={{ fontSize: 10 }}>{t('lg.source')}</span>
            {['all', 'agent', 'tool', 'rag', 'runtime', 'verifier', 'token_tracker'].map(s => (
              <span key={s} className={`filter-pill ${src === s ? 'on' : ''}`} onClick={() => setSrc(s)}>{s === 'all' ? t('flt.all') : s}</span>
            ))}
          </div>
          <input className="input" style={{ maxWidth: 220, marginLeft: 'auto' }} placeholder={t('lg.searchPh')} value={q} onChange={e => setQ(e.target.value)} />
          <select className="input" style={{ maxWidth: 130 }} value={run} onChange={e => setRun(e.target.value)}>
            <option value="all">{t('lg.allRuns')}</option>
            {[...new Set(all.map(l => l.runId))].map(r => <option key={r}>{r}</option>)}
          </select>
        </div>

        {mode === 'table' && (
          <div style={{ maxHeight: 'calc(100vh - 280px)', overflow: 'auto' }}>
            <table className="log-table">
              <thead>
                <tr>
                  <th style={{ width: 78 }}>{t('c.time')}</th>
                  <th style={{ width: 56 }}>{t('c.level')}</th>
                  <th style={{ width: 140 }}>{t('c.source')}</th>
                  <th style={{ width: 86 }}>{t('c.runId')}</th>
                  <th>{t('c.message')}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(l => (
                  <tr key={l.id} onClick={() => setPicked(l)}>
                    <td className="ts">{fmt.hh(l.t).slice(0, 8)}</td>
                    <td><span className={`lv ${l.level === 'error' ? 'err' : l.level === 'warn' ? 'warn' : l.level === 'info' ? 'info' : 'debug'}`}>{l.level}</span></td>
                    <td className="src">{l.source}</td>
                    <td className="rid">{l.runId}</td>
                    <td className="msg">{l.msg}</td>
                  </tr>
                ))}
                {filtered.length === 0 && <tr><td colSpan="5"><Empty>{t('lg.noMatch')}</Empty></td></tr>}
              </tbody>
            </table>
          </div>
        )}

        {mode === 'terminal' && (
          <div ref={termRef} className="term-view" style={{ height: 'calc(100vh - 280px)', background: '#04050a' }}>
            {filtered.slice().reverse().map(l => {
              const lvCls = l.level === 'error' ? 'lv-err' : l.level === 'warn' ? 'lv-warn' : l.level === 'info' ? 'lv-info' : 'lv-debug';
              return (
                <div key={l.id} className="ln">
                  <span className="ts">[{fmt.hh(l.t).slice(0, 8)}]</span>
                  <span className={lvCls}>{l.level.toUpperCase().padEnd(5)}</span>
                  <span className="src">{l.source.padEnd(15)}</span>
                  <span style={{ color: 'var(--fg-0)' }}>{l.msg}</span>
                </div>
              );
            })}
            {live && <div><span className="ts">[—]</span> <span className="lv-info">LIVE </span> <span className="src">tail            </span> <span className="cursor"></span></div>}
          </div>
        )}
      </Panel>

      {picked && <LogDrawer log={picked} onClose={() => setPicked(null)} />}
    </div>
  );
}

function LogDrawer({ log, onClose }) {
  return (
    <div className="drawer">
      <div className="head">
        <div className="flex1">
          <div className="kind">{log.source}</div>
          <div className="ttl">{log.msg}</div>
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
            {fmt.hh(log.t)} · {t('tr.dr.run')} <span className="bright">{log.runId}</span> · {t('c.level')} <span className={log.level === 'error' ? 'red' : log.level === 'warn' ? 'amber' : 'blue'}>{log.level}</span>
          </div>
        </div>
        <button className="btn icon ghost" onClick={onClose}>✕</button>
      </div>
      <div className="body">
        <div className="section">
          <div className="h">{t('lg.dr.payload')}</div>
          <pre className="code-block">{JSON.stringify({
            id: log.id,
            timestamp: log.t,
            level: log.level,
            source: log.source,
            taskId: log.taskId,
            runId: log.runId,
            message: log.msg,
            payload: {
              cwd: '/work/runs/' + log.runId,
              pid: log.source.startsWith('tool.terminal') ? 18472 : null,
            },
          }, null, 2)}</pre>
        </div>
        <div className="section">
          <div className="h">{t('lg.dr.ctx')}</div>
          <div className="kv-list" style={{ fontSize: 11.5 }}>
            <div className="kv-row"><span className="k">{t('lg.dr.prev')}</span><span className="v muted">orchestrator · plan saved</span></div>
            <div className="kv-row"><span className="k">{t('lg.dr.prev')}</span><span className="v muted">rag · 2 hits (top 0.79)</span></div>
            <div className="kv-row"><span className="k bright">{t('lg.dr.this')}</span><span className="v bright">{log.msg}</span></div>
            <div className="kv-row"><span className="k">{t('lg.dr.next')}</span><span className="v muted">runtime · pid=18472 alive</span></div>
            <div className="kv-row"><span className="k">{t('lg.dr.next')}</span><span className="v muted">tool.terminal · sqlmap heuristic match</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.LogsPage = LogsPage;
