/* global React, MOCK, fmt, t, NewTaskModal */
// ============================================================
// Tasks — list (left) + detail (conversation + side panel)
// ============================================================

const { useState: useStateT, useEffect: useEffectT, useRef: useRefT, useMemo: useMemoT } = React;

function TasksPage({ onNav }) {
  const [activeId, setActive] = useStateT('task_002');
  const [filter, setFilter] = useStateT('all');
  const [q, setQ] = useStateT('');
  const [showModal, setShowModal] = useStateT(false);
  const [tasks, setTasks] = useStateT(MOCK.TASKS);

  // ⌘K "新建任务" command opens this modal from anywhere
  useEffectT(() => {
    const handler = () => setShowModal(true);
    window.addEventListener('fh:open-new-task', handler);
    return () => window.removeEventListener('fh:open-new-task', handler);
  }, []);

  // Load tasks from API on mount if live
  useEffectT(() => {
    if (!window.IS_LIVE) return;
    window.API.getTasks().then(data => {
      if (data && Array.isArray(data)) setTasks(data);
    });
  }, []);

  // Subscribe to SSE task status updates
  useEffectT(() => {
    if (!window.API) return;
    return window.API.subscribeEvents(ev => {
      if (ev.type === 'task_status') {
        setTasks(prev => prev.map(tk =>
          tk.id === ev.task_id ? { ...tk, ...ev.updates } : tk
        ));
      }
    });
  }, []);

  const filtered = useMemoT(() => {
    return tasks.filter(tk => {
      if (filter !== 'all' && tk.status !== filter) return false;
      if (q && !(tk.title.toLowerCase().includes(q.toLowerCase()) || tk.id.includes(q))) return false;
      return true;
    });
  }, [filter, q, tasks]);

  const active = tasks.find(tk => tk.id === activeId);
  const filterKeys = ['all', 'running', 'queued', 'success', 'failed', 'stopped'];

  function handleCreated(task) {
    setTasks(prev => [task, ...prev]);
    setActive(task.id);
  }

  return (
    <div className="page" style={{ height: '100%', minHeight: 0 }}>
      <div className="page-h">
        <div>
          <div className="t">{t('tasks.t')}</div>
          <div className="sub">{t('tasks.sub')}</div>
        </div>
        <div className="row">
          <button className="btn ghost"><span className="muted">{t('c.export')}</span></button>
          <button className="btn primary" onClick={() => setShowModal(true)}>{t('c.newTask')}</button>
        </div>
      </div>

      <div className="tasks-layout">
        <Panel className="task-list">
          <div className="toolbar">
            <div className="row">
              <input
                className="input"
                placeholder={t('tasks.filterPh')}
                value={q}
                onChange={e => setQ(e.target.value)}
              />
            </div>
            <div className="filters">
              {filterKeys.map(f => (
                <span
                  key={f}
                  className={`filter-pill ${filter === f ? 'on' : ''}`}
                  onClick={() => setFilter(f)}
                >
                  {t('flt.' + f)}
                </span>
              ))}
            </div>
          </div>
          <div className="items">
            {filtered.map(tk => (
              <TaskItem key={tk.id} task={tk} active={tk.id === activeId} onClick={() => setActive(tk.id)} />
            ))}
            {filtered.length === 0 && <Empty>{t('tasks.noMatch')}</Empty>}
          </div>
        </Panel>

        {active && <TaskDetail task={active} key={active.id} />}
      </div>

      {showModal && (
        <NewTaskModal
          onClose={() => setShowModal(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  );
}

function TaskItem({ task, active, onClick }) {
  const tk = task;
  return (
    <div className={`task-item ${active ? 'active' : ''}`} onClick={onClick}>
      <div className="top">
        <StatusBadge status={tk.status} />
        <TypeBadge type={tk.detectedType} />
        <span className="id">{tk.id}</span>
      </div>
      <div className="title">{tk.title}</div>
      <div className="bottom">
        <span className="dim">{tk.startedAt ? fmt.since(tk.startedAt) : '—'}</span>
        <span className="dim">·</span>
        <span><span className="muted">{t('tasks.tk')}</span> {((tk.tokensUsed||0)/1000).toFixed(1)}k</span>
        <span className="dim">·</span>
        <span><span className="muted">{t('tasks.toolsAbbr')}</span> {tk.toolCalls || 0}</span>
        <div className="spark-mini">
          <Sparkline
            data={tk.sparkSeed || [1,1,1,1]}
            w={48} h={16}
            color={tk.status === 'failed' ? 'var(--red)' : tk.status === 'running' ? 'var(--amber)' : 'var(--accent)'}
          />
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------
// Task detail
// ----------------------------------------------------------------
function TaskDetail({ task }) {
  const isActive = task.status === 'running';
  const isMockActive = task.id === 'task_002';
  const initialMessages = isMockActive ? MOCK.MESSAGES_002 : buildSyntheticMessages(task);

  const [messages, setMessages] = useStateT(initialMessages);
  const [hintMode, setHintMode] = useStateT(false);
  const [draft, setDraft] = useStateT('');
  const [obsFresh, setObsFresh] = useStateT(null);
  const msgEnd = useRefT(null);

  const panel = isMockActive ? MOCK.TASK_002_PANEL : null;
  const [obs, setObs] = useStateT(panel?.observations || []);
  const obsExtras = [
    'sqlmap · enumerating column password_hash',
    'sqlmap · row 13 retrieved · 4.18s',
    'sqlmap · row 14 retrieved · 4.21s',
    'sqlmap · CHAR-based payload heuristic match',
    'sqlmap · fetching row 15',
  ];

  useEffectT(() => {
    if (!isMockActive) return;
    let i = 0;
    const id = setInterval(() => {
      const text = obsExtras[i % obsExtras.length];
      i++;
      const ent = { id: `auto_${Date.now()}`, t: new Date().toISOString(), text };
      setObs(o => [...o, ent].slice(-8));
      setObsFresh(ent.id);
      setTimeout(() => setObsFresh(null), 900);
    }, 4500);
    return () => clearInterval(id);
  }, [isMockActive]);

  useEffectT(() => {
    msgEnd.current?.scrollTo({ top: msgEnd.current.scrollHeight, behavior: 'smooth' });
  }, [messages.length]);

  const send = async () => {
    if (!draft.trim()) return;
    const newMsg = {
      id: `m_${Date.now()}`,
      role: 'user',
      t: new Date().toISOString(),
      content: draft,
      isHint: hintMode,
    };
    setMessages(m => [...m, newMsg]);

    if (window.IS_LIVE && hintMode) {
      await window.API.hintTask(task.id, draft);
    }

    setTimeout(() => {
      setMessages(m => [...m, {
        id: `m_${Date.now()}_ack`,
        role: hintMode ? 'system' : 'agent',
        t: new Date().toISOString(),
        content: hintMode ? t('td.hintAck') : t('td.continueAck'),
      }]);
    }, 600);
    setDraft('');
  };

  async function handleStop() {
    if (window.IS_LIVE) await window.API.stopTask(task.id);
    setMessages(m => [...m, {
      id: `m_stop_${Date.now()}`,
      role: 'system',
      t: new Date().toISOString(),
      content: 'stop signal sent',
    }]);
  }

  return (
    <div className="task-detail">
      <div className="task-detail-head">
        <div className="left">
          <div className="row gap-8" style={{ marginBottom: 6 }}>
            <StatusBadge status={task.status} size="lg" />
            <TypeBadge type={task.detectedType} />
            <span className="dim mono" style={{ fontSize: 11 }}>{task.id}</span>
            {task.currentRunId && (
              <span className="dim mono" style={{ fontSize: 11 }}>· {t('td.run')} <span className="bright">{task.currentRunId}</span></span>
            )}
          </div>
          <div className="title">{task.title}</div>
          <div className="meta">
            <span>{t('c.target')} <b>{task.target}</b></span>
            <span>{t('c.goal')} <b>{task.goal}</b></span>
            <span>{t('c.started')} <b>{task.startedAt ? fmt.since(task.startedAt) : '—'}</b></span>
            <span>{t('c.tokens')} <b>{((task.tokensUsed||0)/1000).toFixed(1)}k</b></span>
            <span>{t('c.tools')} <b>{task.toolCalls || 0}</b></span>
            {task.finalFlag && <span>{t('c.flag')} <b className="green">{task.finalFlag}</b></span>}
            {task.stopReason && <span>{t('c.stopReason')} <b className="red">{task.stopReason}</b></span>}
          </div>
        </div>
        <div className="actions">
          {isActive && <button className="btn danger" onClick={handleStop}>■ {t('c.stop')}</button>}
          {isActive && <button className="btn">⟲ {t('c.retry')}</button>}
          {task.status === 'failed' && <button className="btn primary">⟲ {t('c.retry')}</button>}
          <button className="btn ghost">⤓ {t('c.export')}</button>
          <button className="btn ghost">⧉ {t('c.trace')}</button>
        </div>
      </div>

      <div className="task-detail-body">
        {/* convo */}
        <div className="task-convo">
          <div className="msg-list" ref={msgEnd}>
            {messages.map(m => <Message key={m.id} m={m} />)}
            {isActive && (
              <div className="msg agent">
                <div className="avatar">FH</div>
                <div className="body">
                  <div className="who">{t('td.agentRunning')}</div>
                  <div className="content">
                    <span className="amber">▸</span> {t('td.runningTail')} <Dots />
                    <span className="code">{t('td.runningTailCode')}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="composer">
            <div className="tabs-mini">
              <span className={`tab-mini ${!hintMode ? 'on' : ''}`} style={!hintMode ? { color: 'var(--accent)', background: 'rgba(107,230,117,0.08)', borderColor: 'var(--accent-dim)' } : {}} onClick={() => setHintMode(false)}>
                {t('td.continue')}
              </span>
              <span className={`tab-mini ${hintMode ? 'on' : ''}`} onClick={() => setHintMode(true)}>
                {t('td.injectHint')}
              </span>
              <span style={{ marginLeft: 'auto', color: 'var(--fg-3)', fontSize: 10.5, alignSelf: 'center' }}>
                {hintMode ? t('td.hintDesc') : t('td.continueDesc')}
              </span>
            </div>
            <div className="row">
              <textarea
                className="input"
                placeholder={hintMode ? t('td.composer.hint') : t('td.composer.continue')}
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }}}
                rows={2}
              />
              <button className={`btn ${hintMode ? '' : 'primary'}`} onClick={send}>
                {hintMode ? t('td.inject') : t('td.sendBtn')} <span className="kbd">⌘↵</span>
              </button>
            </div>
          </div>
        </div>

        {/* side panel */}
        <div className="side-panel">
          {panel && <PlanCard plan={panel.plan} />}
          {panel && <StrategyCard panel={panel} />}
          {panel && <ToolCard tool={panel.tool} />}
          {panel && <ObsCard obs={obs} fresh={obsFresh} />}
          {panel && <KnowledgeCard hits={panel.knowledgeHits} />}
          {panel && <NotesCard notes={panel.notes} />}
          {panel && <ArtifactsCard artifacts={panel.artifacts} />}
          {!panel && <SyntheticSidePanel task={task} />}
        </div>
      </div>
    </div>
  );
}

function Message({ m }) {
  const cls = m.role === 'user' ? 'user' : m.role === 'agent' ? 'agent' : 'system';
  const avatar = m.role === 'user' ? 'me' : m.role === 'agent' ? 'FH' : '∎';
  const whoKey = m.role === 'user' ? (m.isHint ? 'td.who.youHint' : 'td.who.you')
    : m.role === 'agent' ? 'td.who.agent' : 'td.who.system';
  return (
    <div className={`msg ${cls}`}>
      <div className="avatar">{avatar}</div>
      <div className="body">
        <div className="who" style={m.isHint ? { color: 'var(--amber)' } : {}}>
          {t(whoKey)} <span className="dim" style={{ marginLeft: 8, letterSpacing: 0 }}>{fmt.hh(m.t)}</span>
        </div>
        <div className="content">
          {m.content}
          {m.tools && (
            <div style={{ marginTop: 4 }}>
              {m.tools.map((tl, i) => (
                <span key={i} className="tool-pill"><span className="cyan">⚒</span> {tl}</span>
              ))}
            </div>
          )}
          {m.code && <code className="code">{m.code}</code>}
        </div>
      </div>
    </div>
  );
}

// ---------- side panel cards ----------
function PlanCard({ plan }) {
  return (
    <div className="side-card">
      <div className="h"><span className="accent">▸ {t('side.plan')}</span><span className="dim right">{plan.filter(p => p.state==='done').length}/{plan.length}</span></div>
      <div className="plan-list">
        {plan.map((p, i) => {
          const labelKey = `plan.${p.id}`;
          return (
            <div key={p.id} className={`plan-step ${p.state}`}>
              <span className="marker">{p.state === 'done' ? '✓' : i + 1}</span>
              <span>{t(labelKey)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function StrategyCard({ panel }) {
  return (
    <div className="side-card">
      <div className="h">◈ {t('side.strategy')} <span className="magenta right" style={{ letterSpacing: 0 }}>{panel.strategy}</span></div>
      <div className="kv-list">
        <div className="kv-row"><span className="k">{t('side.hypothesis')}</span><span className="v">{panel.hypothesis}</span></div>
      </div>
    </div>
  );
}

function ToolCard({ tool }) {
  return (
    <div className="side-card">
      <div className="h">⚒ {t('side.tool')} <span className="amber right" style={{ letterSpacing: 0 }}>{tool.name} <Dots /></span></div>
      <div className="code-block" style={{ marginTop: 4 }}>{tool.args}</div>
      <div className="row gap-12" style={{ marginTop: 6, fontSize: 10.5, color: 'var(--fg-2)' }}>
        <span><span className="muted">{t('c.started')}</span> {fmt.since(tool.startedAt)}</span>
        <span><span className="muted">{t('side.pid')}</span> 18472</span>
        <span><span className="muted">{t('side.elapsed')}</span> 00:01:18</span>
      </div>
    </div>
  );
}

function ObsCard({ obs, fresh }) {
  return (
    <div className="side-card">
      <div className="h">◇ {t('side.obs')} <span className="dim right">{t('c.live')}</span></div>
      <div className="obs-feed">
        {obs.map(o => (
          <div key={o.id} className={`obs-row ${o.id === fresh ? 'fresh' : ''}`}>
            <span className="when">{fmt.hh(o.t).slice(0, 8)}</span>{o.text}
          </div>
        ))}
      </div>
    </div>
  );
}

function KnowledgeCard({ hits }) {
  return (
    <div className="side-card">
      <div className="h">◉ {t('side.knowledge')} <span className="dim right">{hits.length}</span></div>
      <div className="col gap-4">
        {hits.map(h => (
          <div key={h.id} style={{ fontSize: 11.5, lineHeight: 1.4, padding: '4px 0' }}>
            <div className="row gap-6">
              <span className="blue" style={{ fontSize: 10 }}>{h.source}</span>
              <span className="bright ellipsis flex1">{h.title}</span>
              <span className="dim mono" style={{ fontSize: 10 }}>{h.score.toFixed(2)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function NotesCard({ notes }) {
  return (
    <div className="side-card">
      <div className="h">✎ {t('side.notes')} <span className="dim right">{notes.length}</span></div>
      <div className="col gap-4">
        {notes.map(n => (
          <div key={n.id} style={{ fontSize: 11.5 }}>
            <span className="muted">{n.key}</span>
            <span className="dim"> = </span>
            <span className="bright">{n.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ArtifactsCard({ artifacts }) {
  return (
    <div className="side-card">
      <div className="h">◫ {t('side.artifacts')} <span className="dim right">{artifacts.length}</span></div>
      <div className="col gap-4">
        {artifacts.map(a => (
          <div key={a.id} className="row gap-8" style={{ fontSize: 11.5 }}>
            <span className="magenta" style={{ fontSize: 10 }}>{a.kind}</span>
            <span className="bright ellipsis flex1">{a.name}</span>
            <span className="dim" style={{ fontSize: 10 }}>{a.size}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SyntheticSidePanel({ task }) {
  const isFlagged = task.finalFlag;
  let summaryKey;
  if (task.status === 'success') summaryKey = 'side.summary.success';
  else if (task.status === 'failed') summaryKey = 'side.summary.failed';
  else if (task.status === 'queued') summaryKey = 'side.summary.queued';
  else summaryKey = 'side.summary.stopped';
  return (
    <>
      <div className="side-card">
        <div className="h">▸ {t('side.status')}</div>
        <div className="kv-list">
          <div className="kv-row"><span className="k">{t('c.status')}</span><span className="v"><StatusBadge status={task.status} /></span></div>
          <div className="kv-row"><span className="k">{t('c.duration')}</span><span className="v">{task.durationMs ? (task.durationMs/1000).toFixed(1) + 's' : '—'}</span></div>
          <div className="kv-row"><span className="k">{t('c.tokens')}</span><span className="v">{(task.tokensUsed||0).toLocaleString()}</span></div>
          <div className="kv-row"><span className="k">{t('c.tools')}</span><span className="v">{task.toolCalls||0}</span></div>
          {task.stopReason && <div className="kv-row"><span className="k">{t('c.stopReason')}</span><span className="v red">{task.stopReason}</span></div>}
          {isFlagged && <div className="kv-row"><span className="k">{t('c.flag')}</span><span className="v green">{task.finalFlag}</span></div>}
        </div>
      </div>
      <div className="side-card">
        <div className="h">◈ {t('side.summary')}</div>
        <div style={{ fontSize: 11.5, color: 'var(--fg-1)', lineHeight: 1.55 }}>
          {t(summaryKey, task.stopReason || '')}
        </div>
      </div>
    </>
  );
}

function buildSyntheticMessages(tk) {
  if (tk.status === 'queued') {
    return [{ id: 'sm1', role: 'user', t: new Date().toISOString(), content: `${tk.goal || ''}\n${t('c.target')}: ${tk.target}` }];
  }
  return [
    { id: 'sm1', role: 'user',   t: tk.startedAt || new Date().toISOString(), content: `${tk.goal || ''}\n${t('c.target')}: ${tk.target}` },
    { id: 'sm2', role: 'agent',  t: tk.startedAt || new Date().toISOString(), content: window.LANG === 'zh' ? '收到，开始 recon。' : 'Acknowledged. Starting recon.' },
    { id: 'sm3', role: 'system', t: tk.finishedAt || tk.startedAt || new Date().toISOString(),
      content: tk.finalFlag ? `flag verified ✓  ${tk.finalFlag}` :
        tk.stopReason ? `task ended · stop_reason=${tk.stopReason}` : 'task ended' },
  ];
}

window.TasksPage = TasksPage;
