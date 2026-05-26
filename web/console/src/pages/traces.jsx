/* global React, MOCK, fmt, t */
// ============================================================
// Traces — list page + detail page (timeline / graph / data)
// ============================================================

const { useState: uS, useEffect: uE, useRef: uR, useMemo: uM } = React;

function TracesPage({ runId, onNav }) {
  if (runId) return <TraceDetail runId={runId} onNav={onNav} />;
  return <TraceList onNav={onNav} />;
}

function TraceList({ onNav }) {
  const [filter, setFilter] = uS('all');
  const [apiTraces, setApiTraces] = uS(null);

  uE(() => {
    window.API.getTraces().then(data => {
      if (data && Array.isArray(data)) setApiTraces(data);
    });
  }, []);

  const sourceTraces = apiTraces || MOCK.TRACES;
  const runs = sourceTraces.filter(r => filter === 'all' || r.status === filter);
  const filterKeys = ['all', 'running', 'success', 'failed', 'stopped'];
  return (
    <div className="page">
      <div className="page-h">
        <div>
          <div className="t">{t('tr.t')}</div>
          <div className="sub">{t('tr.sub')}</div>
        </div>
        <div className="row">
          <button className="btn ghost"><span className="muted">{t('c.last24h')}</span> ▾</button>
          <button className="btn ghost"><span className="muted">{t('c.allTargets')}</span> ▾</button>
          <button className="btn">⬇ {t('c.export')}</button>
        </div>
      </div>

      <Panel>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-1)', display: 'flex', gap: 6 }}>
          {filterKeys.map(f => (
            <span key={f} className={`filter-pill ${filter === f ? 'on' : ''}`} onClick={() => setFilter(f)}>{t('flt.' + f)}</span>
          ))}
          <input className="input" placeholder={t('tr.filterPh')} style={{ marginLeft: 'auto', maxWidth: 280 }} />
        </div>
        <table className="k-table">
          <thead>
            <tr>
              <th>{t('c.runId')}</th>
              <th>{t('c.task')}</th>
              <th>{t('c.target')}</th>
              <th>{t('c.status')}</th>
              <th style={{ textAlign: 'right' }}>{t('c.started')}</th>
              <th style={{ textAlign: 'right' }}>{t('c.duration')}</th>
              <th style={{ textAlign: 'right' }}>{t('c.steps')}</th>
              <th style={{ textAlign: 'right' }}>{t('c.tools')}</th>
              <th style={{ textAlign: 'right' }}>{t('c.tokens')}</th>
              <th>{t('c.flag')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {runs.map(r => (
              <tr key={r.id} onClick={() => onNav(`traces/${r.id}`)} style={{ cursor: 'pointer' }}>
                <td className="mono"><span className="bright">{r.id}</span></td>
                <td className="muted mono">{r.taskId}</td>
                <td className="muted ellipsis" style={{ maxWidth: 300 }}>{r.target}</td>
                <td><StatusBadge status={r.status} /></td>
                <td style={{ textAlign: 'right' }} className="muted mono">{fmt.since(r.startedAt)}</td>
                <td style={{ textAlign: 'right' }} className="mono">{r.durationMs ? (r.durationMs/1000).toFixed(1) + 's' : '—'}</td>
                <td style={{ textAlign: 'right' }} className="mono">{r.totalSteps}</td>
                <td style={{ textAlign: 'right' }} className="mono">{r.totalToolCalls}</td>
                <td style={{ textAlign: 'right' }} className="mono">{(r.totalTokens/1000).toFixed(1)}k</td>
                <td>
                  {r.finalFlag
                    ? <span className="green ellipsis mono" style={{ maxWidth: 220, display: 'inline-block', fontSize: 11 }}>{r.finalFlag}</span>
                    : <span className="dim">—</span>}
                </td>
                <td className="dim" style={{ textAlign: 'right' }}>›</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

// ----------------------------------------------------------------
// TraceDetail
// ----------------------------------------------------------------
function TraceDetail({ runId, onNav }) {
  const [apiTraces, setApiTraces] = uS(null);

  uE(() => {
    window.API.getTraces().then(data => {
      if (data && Array.isArray(data)) setApiTraces(data);
    });
  }, []);

  const sourceTraces = apiTraces || MOCK.TRACES;
  const run = sourceTraces.find(r => r.id === runId) || sourceTraces[0];
  const [tab, setTab] = uS('timeline');
  const [drawer, setDrawer] = uS(null);
  const isActive = run.status === 'running';
  const timeline = run.timeline || synthTimeline(run);

  return (
    <div className="page" style={{ minHeight: 0 }}>
      <div className="page-h">
        <div>
          <div className="t row gap-12" style={{ alignItems: 'center' }}>
            <span className="dim" style={{ cursor: 'pointer', fontSize: 13 }} onClick={() => onNav('traces')}>{t('tr.back')}</span>
            <span>{run.id}</span>
            <StatusBadge status={run.status} />
          </div>
          <div className="sub">{t('c.task')} <b className="bright">{run.taskId}</b> · {t('c.target')} <b className="bright">{run.target}</b></div>
        </div>
        <div className="row">
          <button className="btn ghost">⬇ {t('c.json')}</button>
          <button className="btn ghost">{t('c.openTask')}</button>
          <button className="btn">⟲ {t('c.replay')}</button>
        </div>
      </div>

      <Panel>
        <div className="trace-detail-head">
          <Kv k={t('c.started')}   v={fmt.hh(run.startedAt) + ' · ' + fmt.since(run.startedAt)} />
          <Kv k={t('c.duration')}  v={run.durationMs ? (run.durationMs/1000).toFixed(1) + 's' : t('tr.stillRunning')} />
          <Kv k={t('c.steps')}     v={run.totalSteps} />
          <Kv k={t('c.toolCalls')} v={run.totalToolCalls} />
          <Kv k={t('c.tokens')}    v={`${run.totalTokens.toLocaleString()} · ${(run.inputTokens/1000).toFixed(1)}k in / ${(run.outputTokens/1000).toFixed(1)}k out`} />
          {run.finalFlag && <Kv k={t('c.flag')} v={<span className="green">{run.finalFlag}</span>} />}
        </div>

        <div className="tabs">
          <div className={`tab ${tab === 'timeline' ? 'active' : ''}`} onClick={() => setTab('timeline')}>
            {t('tr.tab.timeline')} <span className="count">{timeline.length}</span>
          </div>
          <div className={`tab ${tab === 'graph' ? 'active' : ''}`} onClick={() => setTab('graph')}>
            {t('tr.tab.graph')}
          </div>
          <div className={`tab ${tab === 'data' ? 'active' : ''}`} onClick={() => setTab('data')}>
            {t('tr.tab.data')}
          </div>
        </div>

        {tab === 'timeline' && <TimelineView events={timeline} onPick={setDrawer} isActive={isActive} />}
        {tab === 'graph' && run.id === 'run_002' && <GraphView onPick={(g) => setDrawer({
          id: g.id, kind: g.k.toLowerCase() + '.node', title: g.t, summary: '', t: run.startedAt,
        })} />}
        {tab === 'graph' && run.id !== 'run_002' && <Empty>{t('tr.graph.notReady', run.id)}</Empty>}
        {tab === 'data' && <DataTables run={run} events={timeline} />}
      </Panel>

      {drawer && <EventDrawer event={drawer} run={run} onClose={() => setDrawer(null)} />}
    </div>
  );
}

function Kv({ k, v }) { return (
  <div className="kv">
    <span className="k">{k}</span>
    <span className="v">{v}</span>
  </div>
);}

// ----------------------------------------------------------------
// Timeline
// ----------------------------------------------------------------
function typeLabel(type) {
  return t('tr.type.' + type);
}

function TimelineView({ events, onPick, isActive }) {
  const [hover, setHover] = uS(null);

  return (
    <div className="timeline">
      {events.map((e) => (
        <div
          key={e.id}
          className={`tl-event type-${e.type} ${e.status === 'running' ? 'running' : ''}`}
          onClick={() => onPick(e)}
          onMouseEnter={(ev) => setHover({ e, x: ev.clientX, y: ev.clientY })}
          onMouseMove={(ev) => setHover(h => h ? { ...h, x: ev.clientX, y: ev.clientY } : null)}
          onMouseLeave={() => setHover(null)}
        >
          <span className="when">{fmt.hh(e.t).slice(0, 8)}</span>
          <span className="node"></span>
          <div className="body">
            <div className="title">
              <span className="kind">{typeLabel(e.type)}</span>
              <span>{e.title}</span>
              {e.status === 'running' && <span className="amber" style={{ fontSize: 10.5 }}>· {t('tr.running')}</span>}
            </div>
            <div className="summary">{e.summary}</div>
          </div>
          <div className="right">
            {e.tool && <span className="cyan">⚒ {e.tool}</span>}
            {e.durationMs != null && <span>{(e.durationMs/1000).toFixed(1)}s</span>}
            {e.tokens != null && e.tokens > 0 && <span className="muted">·</span>}
            {e.tokens != null && e.tokens > 0 && <span>{e.tokens > 1000 ? (e.tokens/1000).toFixed(1) + 'k' : e.tokens} tk</span>}
            <span className="dim">›</span>
          </div>
        </div>
      ))}
      {isActive && (
        <div className="tl-event type-system" style={{ opacity: 0.6 }}>
          <span className="when">—</span>
          <span className="node" style={{ borderStyle: 'dashed' }}></span>
          <div className="body">
            <div className="title"><span className="kind">{t('tr.type.pending')}</span> <span className="dim">{t('tr.awaiting')}</span></div>
          </div>
          <div className="right"><Dots /></div>
        </div>
      )}

      {hover && <HoverCard data={hover.e} x={hover.x} y={hover.y} />}
    </div>
  );
}

function HoverCard({ data, x, y }) {
  return (
    <div className="hover-card" style={{ left: x + 14, top: y + 14 }}>
      <div className="hk" style={{ marginBottom: 6 }}>{typeLabel(data.type)}</div>
      <div className="bright" style={{ fontSize: 12, marginBottom: 6 }}>{data.title}</div>
      <div className="row"><span className="dim">{t('tr.dr.when')}</span><span className="v">{fmt.hh(data.t).slice(0, 8)}</span></div>
      {data.tool && <div className="row"><span className="dim">{t('tr.dr.tool')}</span><span className="v cyan">{data.tool}</span></div>}
      {data.durationMs != null && <div className="row"><span className="dim">{t('tr.dr.dur')}</span><span className="v">{(data.durationMs/1000).toFixed(2)}s</span></div>}
      {data.tokens != null && <div className="row"><span className="dim">{t('tr.dr.tokens')}</span><span className="v">{data.tokens.toLocaleString()}</span></div>}
      {data.status === 'running' && (
        <div className="row" style={{ marginTop: 4 }}><span className="amber">● {t('tr.running')}</span></div>
      )}
      <div className="dim" style={{ marginTop: 6, fontSize: 10 }}>{t('tr.click')}</div>
    </div>
  );
}

// ----------------------------------------------------------------
// Graph DAG view
// ----------------------------------------------------------------
function GraphView({ onPick }) {
  const g = MOCK.GRAPH_002;
  const nodeById = Object.fromEntries(g.nodes.map(n => [n.id, n]));
  const activeSet = new Set(g.active.map(([a,b]) => `${a}-${b}`));

  return (
    <div className="graph-shell" style={{ height: 480 }}>
      <div style={{ position: 'absolute', top: 10, left: 14, fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.16em', textTransform: 'uppercase' }}>
        {t('tr.graph.title', g.nodes.length, g.edges.length)}
      </div>
      <div style={{ position: 'absolute', top: 10, right: 14, display: 'flex', gap: 10, fontSize: 10, color: 'var(--fg-2)' }}>
        <LegendDot c="var(--accent)" t={t('tr.graph.taskVerify')} />
        <LegendDot c="var(--cyan)" t={t('tr.graph.tool')} />
        <LegendDot c="var(--magenta)" t={t('tr.graph.stratHypo')} />
        <LegendDot c="var(--blue)" t={t('tr.graph.knowledge')} />
        <LegendDot c="var(--amber)" t={t('tr.graph.note')} />
      </div>
      <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--line-3)" />
          </marker>
          <marker id="arrowA" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L10,5 L0,10 z" fill="var(--accent)" />
          </marker>
        </defs>
        {g.edges.map(([a, b], i) => {
          const A = nodeById[a], B = nodeById[b];
          if (!A || !B) return null;
          const x1 = A.x + 70, y1 = A.y + 24;
          const x2 = B.x, y2 = B.y + 24;
          const isAct = activeSet.has(`${a}-${b}`);
          const cx = (x1 + x2) / 2;
          return (
            <path key={i}
              d={`M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}`}
              className={`gedge ${isAct ? 'active' : ''}`}
              markerEnd={isAct ? 'url(#arrowA)' : 'url(#arrow)'}
            />
          );
        })}
      </svg>
      {g.nodes.map(n => (
        <div
          key={n.id}
          className={`gnode ${n.kind || ''}`}
          style={{ left: n.x, top: n.y, cursor: 'pointer' }}
          onClick={() => onPick(n)}
        >
          <div className="gk">{n.k}</div>
          <div className="gt">{n.t}</div>
          {n.k === 'TOOL' && n.t.includes('running') && (
            <div style={{ position: 'absolute', top: 6, right: 8, width: 6, height: 6, borderRadius: '50%', background: 'var(--amber)', boxShadow: '0 0 4px var(--amber)', animation: 'pulse 1.4s ease-in-out infinite' }}></div>
          )}
        </div>
      ))}
    </div>
  );
}
function LegendDot({ c, t: tx }) {
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
    <span style={{ width: 8, height: 8, borderRadius: 2, background: c }}></span>{tx}
  </span>;
}

// ----------------------------------------------------------------
// Data tables tab
// ----------------------------------------------------------------
function DataTables({ run, events }) {
  const [tab, setTab] = uS('steps');
  const tools = events.filter(e => e.tool);
  const knowledge = events.filter(e => e.type === 'knowledge');
  const notes = events.filter(e => e.type === 'note');
  return (
    <>
      <div className="tabs" style={{ padding: '0 14px' }}>
        {[
          ['steps',     t('tr.data.steps', events.length)],
          ['tools',     t('tr.data.tools', tools.length)],
          ['knowledge', t('tr.data.knowledge', knowledge.length)],
          ['notes',     t('tr.data.notes', notes.length)],
          ['artifacts', t('tr.data.artifacts')],
          ['files',     t('tr.data.files')],
        ].map(([k, l]) => (
          <div key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{l}</div>
        ))}
      </div>
      <div style={{ maxHeight: 480, overflow: 'auto' }}>
        {tab === 'steps' && <StepsTable events={events} />}
        {tab === 'tools' && <ToolsTable events={tools} />}
        {tab === 'knowledge' && <KnowledgeTbl events={knowledge} />}
        {tab === 'notes' && <NotesTbl events={notes} />}
        {tab === 'artifacts' && <Empty>{t('tr.data.noArtifacts')}</Empty>}
        {tab === 'files' && <Empty>{t('tr.data.noFiles')}</Empty>}
      </div>
    </>
  );
}

function StepsTable({ events }) {
  return (
    <table className="k-table">
      <thead><tr>
        <th>{t('c.time')}</th><th>{t('c.kind')}</th><th>{t('c.title')}</th><th>{t('c.tools')}</th>
        <th style={{ textAlign: 'right' }}>{t('c.duration')}</th>
        <th style={{ textAlign: 'right' }}>{t('c.tokens')}</th>
        <th>{t('c.status')}</th>
      </tr></thead>
      <tbody>
        {events.map(e => (
          <tr key={e.id}>
            <td className="muted mono">{fmt.hh(e.t).slice(0, 8)}</td>
            <td><span className={`chip ${e.type === 'tool' ? 'cyan' : e.type === 'verify' ? 'green' : e.type === 'knowledge' ? 'blue' : ''}`}>{typeLabel(e.type)}</span></td>
            <td className="ellipsis" style={{ maxWidth: 380 }}>{e.title}</td>
            <td className="cyan">{e.tool || '—'}</td>
            <td style={{ textAlign: 'right' }} className="mono">{e.durationMs != null ? (e.durationMs/1000).toFixed(2) + 's' : '—'}</td>
            <td style={{ textAlign: 'right' }} className="mono">{e.tokens || 0}</td>
            <td><StatusBadge status={e.status === 'running' ? 'running' : 'done'} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
function ToolsTable({ events }) {
  return (
    <table className="k-table">
      <thead><tr><th>{t('c.time')}</th><th>{t('c.tools')}</th><th>{t('c.summary')}</th><th style={{ textAlign: 'right' }}>{t('c.duration')}</th><th>{t('c.status')}</th></tr></thead>
      <tbody>
        {events.map(e => (
          <tr key={e.id}>
            <td className="muted mono">{fmt.hh(e.t).slice(0, 8)}</td>
            <td className="cyan mono">{e.tool}</td>
            <td className="ellipsis" style={{ maxWidth: 460 }}>{e.summary}</td>
            <td style={{ textAlign: 'right' }} className="mono">{e.durationMs != null ? (e.durationMs/1000).toFixed(2) + 's' : '—'}</td>
            <td><StatusBadge status={e.status === 'running' ? 'running' : 'done'} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
function KnowledgeTbl({ events }) {
  return (
    <table className="k-table">
      <thead><tr><th>{t('c.time')}</th><th>{t('c.title')}</th><th>{t('c.summary')}</th></tr></thead>
      <tbody>
        {events.map(e => (
          <tr key={e.id}>
            <td className="muted mono">{fmt.hh(e.t).slice(0, 8)}</td>
            <td className="blue">{e.title}</td>
            <td className="muted">{e.summary}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
function NotesTbl({ events }) {
  return (
    <table className="k-table">
      <thead><tr><th>{t('c.time')}</th><th>{t('c.title')}</th><th>{t('c.summary')}</th></tr></thead>
      <tbody>
        {events.map(e => (
          <tr key={e.id}>
            <td className="muted mono">{fmt.hh(e.t).slice(0, 8)}</td>
            <td className="amber">{e.title}</td>
            <td className="muted">{e.summary}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ----------------------------------------------------------------
// Event drawer
// ----------------------------------------------------------------
function EventDrawer({ event, run, onClose }) {
  const e = event;
  return (
    <div className="drawer">
      <div className="head">
        <div className="flex1">
          <div className="kind">{typeLabel(e.type)} · {e.kind}</div>
          <div className="ttl">{e.title}</div>
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
            {fmt.hh(e.t)} · {t('tr.dr.run')} <span className="bright">{run.id}</span> · {t('tr.dr.event')} <span className="bright">{e.id}</span>
          </div>
        </div>
        <button className="btn icon ghost" onClick={onClose}>✕</button>
      </div>
      <div className="body">
        <div className="section">
          <div className="h">{t('tr.dr.summary')}</div>
          <div style={{ color: 'var(--fg-0)', fontSize: 12.5 }}>{e.summary || '—'}</div>
        </div>

        <div className="section">
          <div className="h">{t('tr.dr.metrics')}</div>
          <div className="kv-list">
            {e.tool && <div className="kv-row"><span className="k">{t('tr.dr.tool')}</span><span className="v cyan">{e.tool}</span></div>}
            {e.durationMs != null && <div className="kv-row"><span className="k">{t('tr.dr.dur')}</span><span className="v">{(e.durationMs/1000).toFixed(3)} s</span></div>}
            {e.tokens != null && <div className="kv-row"><span className="k">{t('tr.dr.tokens')}</span><span className="v">{e.tokens.toLocaleString()}</span></div>}
            <div className="kv-row"><span className="k">{t('tr.dr.status')}</span><span className="v"><StatusBadge status={e.status === 'running' ? 'running' : 'done'} /></span></div>
            <div className="kv-row"><span className="k">{t('tr.dr.stepId')}</span><span className="v mono">{e.id}</span></div>
          </div>
        </div>

        {e.type === 'tool' && (
          <div className="section">
            <div className="h">{t('tr.dr.toolIO')}</div>
            <div className="muted" style={{ fontSize: 10, marginBottom: 4 }}>{t('tr.dr.input')}</div>
            <pre className="code-block">{getToolInput(e)}</pre>
            <div className="muted" style={{ fontSize: 10, margin: '8px 0 4px' }}>{t('tr.dr.output')}</div>
            <pre className="code-block">{getToolOutput(e)}</pre>
          </div>
        )}

        {e.type === 'knowledge' && (
          <div className="section">
            <div className="h">{t('tr.dr.chunks')}</div>
            <pre className="code-block">{'doc_002 · chunk_002 (score 0.79)\nDetect backend dialect via timing: pg_sleep, SLEEP, WAITFOR DELAY differ.\nPostgres returns the same response shape for both authenticated and\nunauthenticated probes, so size deltas are the strongest signal.'}</pre>
          </div>
        )}

        <div className="section">
          <div className="h">{t('tr.dr.raw')}</div>
          <pre className="code-block">{JSON.stringify({
            id: e.id, type: e.type, kind: e.kind, t: e.t,
            title: e.title, summary: e.summary,
            tool: e.tool, durationMs: e.durationMs, tokens: e.tokens,
            status: e.status,
          }, null, 2)}</pre>
        </div>
      </div>
    </div>
  );
}

function getToolInput(e) {
  if (e.tool === 'terminal' && e.title.includes('curl')) return '$ curl -sI http://10.10.20.45:8080/admin/login';
  if (e.tool === 'terminal' && e.title.includes('nmap')) return '$ nmap -sV -p 8080 10.10.20.45';
  if (e.tool === 'terminal' && e.title.includes('sqlmap')) return [
    '$ sqlmap -u "http://10.10.20.45:8080/admin/login" \\',
    '    --data \'{"username":"*","password":"x"}\' \\',
    '    --headers "Content-Type: application/json" \\',
    '    --dbms=postgresql --technique=T --level=2 --risk=2'
  ].join('\n');
  if (e.tool === 'http_request') return 'POST /admin/login HTTP/1.1\nHost: 10.10.20.45:8080\nContent-Type: application/json\n\n{"username":"admin\' OR 1=1 --","password":"x"}';
  return JSON.stringify({ tool: e.tool, args: e.title }, null, 2);
}
function getToolOutput(e) {
  if (e.tool === 'terminal' && e.title.includes('curl')) return 'HTTP/1.1 200 OK\nserver: nginx/1.25.3\ncontent-type: application/json\nx-powered-by: Express\ncontent-length: 142';
  if (e.tool === 'terminal' && e.title.includes('nmap')) return 'PORT     STATE SERVICE VERSION\n8080/tcp open  http    nginx 1.25.3\nService Info: OS: Linux';
  if (e.tool === 'terminal' && e.title.includes('sqlmap')) return [
    '[INFO] testing connection to the target URL',
    '[INFO] checking if the target is protected by a WAF/IPS',
    '[INFO] testing if the target URL content is stable',
    '[INFO] target URL content is stable',
    '[INFO] heuristic (basic) test shows that POST parameter username might be injectable',
    '[INFO] testing for SQL injection on POST parameter username',
    '[INFO] confirmed pg_sleep response',
    '[INFO] enumerating tables in database "appdb"',
    '... still running ...'
  ].join('\n');
  if (e.tool === 'http_request') return 'HTTP/1.1 200 OK\ncontent-length: 318\n\n{"error":"login_failed","detail":"<truncated>"}';
  return t('tr.dr.noOutput');
}

function synthTimeline(run) {
  const base = Date.parse(run.startedAt);
  const dur = run.durationMs || 60000;
  const steps = [
    ['task',      'task.started',         'task.started',     `target = ${run.target}`,                 0],
    ['tool',      'tool.called',          'recon · curl',     'fetch headers',                           0.05],
    ['plan',      'agent.plan.created',   'plan created',     `${run.totalSteps} steps planned`,         0.12],
    ['knowledge', 'knowledge.retrieved',  'knowledge retrieved', 'cached recipes for this surface',     0.22],
    ['strategy',  'agent.strategy.selected', 'strategy picked', 'chain matched',                        0.30],
    ['tool',      'tool.called',          'exploit · primary',  '',                                     0.45],
  ];
  if (run.status === 'success') steps.push(
    ['note',      'note.created',         'progress noted',     'candidate identified',                 0.70],
    ['verify',    'verifier.flag.verified', 'flag verified ✓', run.finalFlag,                            0.95],
  );
  if (run.status === 'failed' || run.status === 'stopped') steps.push(
    ['err',       'tool.failed',          'tool failed',        'no_progress / runtime stop',           0.85],
    ['system',    'recovery.stopped',     'recovery stopped',   'stop_reason recorded',                 0.95],
  );
  return steps.map(([type, kind, title, summary, frac], i) => ({
    id: `synth_${run.id}_${i}`,
    t: new Date(base + dur * frac).toISOString(),
    type, kind, title, summary,
    status: 'done',
    durationMs: Math.round(dur * (i === steps.length - 1 ? 0.05 : 0.08)),
    tokens: 200 + Math.round(Math.random() * 400),
    tool: kind.startsWith('tool') ? (i % 2 === 0 ? 'terminal' : 'http_request') : null,
  }));
}

window.TracesPage = TracesPage;
