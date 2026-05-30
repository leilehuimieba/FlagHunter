/* global React, fmt, t, ModeBadge, SubtypeBadge */
// ============================================================
// Dashboard — KPIs x7 + 4 charts + recent activity + flag board
// ============================================================

const { useState: uD, useEffect: uDE } = React;

function currentConnectionState() {
  if (window.API?.getConnectionState) return window.API.getConnectionState();
  return {
    status: window.IS_LIVE ? 'connected' : 'disconnected',
    isLive: Boolean(window.IS_LIVE),
  };
}

const LIVE_EMPTY_DASHBOARD = {
  kpis: {
    running: 0,
    queued: 0,
    tasksToday: 0,
    successToday: 0,
    failedToday: 0,
    stoppedToday: 0,
    successRate: 0,
    dailyTokens: 0,
    estimatedCost: 0,
    toolCalls: 0,
    knowledgeHits: 0,
  },
  tokenSeries: [],
  toolDistribution: [],
  failureDistribution: [],
  knowledgeHitTrend: [],
  alerts: [],
  recentTasks: [],
  recentToolCalls: [],
  recentArtifacts: [],
  flags: [],
};

function normalizeDashboardData(data) {
  if (!data || typeof data !== 'object') return null;
  return {
    ...LIVE_EMPTY_DASHBOARD,
    ...data,
    kpis: {
      ...LIVE_EMPTY_DASHBOARD.kpis,
      ...(data.kpis || {}),
    },
    tokenSeries: Array.isArray(data.tokenSeries) ? data.tokenSeries : [],
    toolDistribution: Array.isArray(data.toolDistribution) ? data.toolDistribution : [],
    failureDistribution: Array.isArray(data.failureDistribution) ? data.failureDistribution : [],
    knowledgeHitTrend: Array.isArray(data.knowledgeHitTrend) ? data.knowledgeHitTrend : [],
    alerts: Array.isArray(data.alerts) ? data.alerts : [],
    recentTasks: Array.isArray(data.recentTasks) ? data.recentTasks : [],
    recentToolCalls: Array.isArray(data.recentToolCalls) ? data.recentToolCalls : [],
    recentArtifacts: Array.isArray(data.recentArtifacts) ? data.recentArtifacts : [],
    flags: Array.isArray(data.flags) ? data.flags : [],
  };
}

// Flags captured from all tasks
function useFlagBoard(initialFlags) {
  const [flags, setFlags] = uD(() => initialFlags || []);
  const [copiedId, setCopiedId] = uD(null);

  uDE(() => {
    setFlags(initialFlags || []);
  }, [JSON.stringify(initialFlags)]);

  function copyFlag(id, text) {
    navigator.clipboard?.writeText(text).catch(() => {});
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  }

  return { flags, copyFlag, copiedId };
}

function DashboardPage({ onNav }) {
  const [liveData, setLiveData] = uD(null);
  const [connection, setConnection] = uD(() => currentConnectionState());
  const [windowFilter, setWindowFilter] = uD('24h');
  const [runtimeFilter, setRuntimeFilter] = uD('all');
  const getDashboard = window.API?.getDashboard;
  const subscribeEvents = window.API?.subscribeEvents;
  const dashboardAvailable = ['connected', 'degraded'].includes(connection.status)
    && typeof getDashboard === 'function';
  const dashboardUnavailableReason = connection?.status !== 'connected' && connection?.status !== 'degraded'
    ? t('c.notConnected')
    : typeof getDashboard === 'function'
      ? ''
      : t('c.notWired');

  uDE(() => {
    const handler = (e) => {
      setConnection(
        e.detail?.connection
        || currentConnectionState()
      );
    };
    window.addEventListener('fh:connection', handler);
    return () => window.removeEventListener('fh:connection', handler);
  }, []);

  uDE(() => {
    let cancelled = false;
    if (!dashboardAvailable || typeof getDashboard !== 'function') {
      setLiveData(null);
      return () => { cancelled = true; };
    }

    getDashboard({ window: windowFilter, runtime: runtimeFilter }).then(data => {
      const normalized = normalizeDashboardData(data);
      if (!cancelled && normalized) setLiveData(normalized);
    });

    return () => {
      cancelled = true;
    };
  }, [dashboardAvailable, getDashboard, windowFilter, runtimeFilter]);

  // Subscribe to SSE for real-time KPI updates — re-fetch dashboard on task events
  uDE(() => {
    if (!dashboardAvailable || typeof subscribeEvents !== 'function' || typeof getDashboard !== 'function') return;
    return subscribeEvents(ev => {
      if (ev.type === 'task_status' || ev.type === 'task_created') {
        getDashboard({ window: windowFilter, runtime: runtimeFilter }).then(data => {
          const normalized = normalizeDashboardData(data);
          if (normalized) setLiveData(normalized);
        });
      }
    });
  }, [dashboardAvailable, getDashboard, subscribeEvents, windowFilter, runtimeFilter]);

  const hasDashboardData = !!liveData;
  const canReadLiveState = connection.status !== 'disconnected';
  const dashboardData = liveData || LIVE_EMPTY_DASHBOARD;
  const { flags, copyFlag, copiedId } = useFlagBoard(dashboardData.flags);
  const kpis = dashboardData.kpis || LIVE_EMPTY_DASHBOARD.kpis;
  const tokenSeries = dashboardData.tokenSeries || [];
  const toolDistribution = dashboardData.toolDistribution || [];
  const failureDistribution = dashboardData.failureDistribution || [];
  const knowledgeHitTrend = dashboardData.knowledgeHitTrend || [];
  const alerts = dashboardData.alerts || [];
  const recentTasks = dashboardData.recentTasks || [];
  const recentToolCalls = dashboardData.recentToolCalls || [];
  const recentArtifacts = dashboardData.recentArtifacts || [];
  const dashboardEmptyState = dashboardAvailable ? t('dash.noData') : dashboardUnavailableReason || t('c.unavailable');
  const tasksEmptyState = dashboardAvailable ? t('tasks.noMatch') : dashboardUnavailableReason || t('c.unavailable');
  const notesArtifactsEmptyState = dashboardAvailable ? t('dash.noData') : dashboardUnavailableReason || t('c.unavailable');
  const dashboardSub = canReadLiveState
    ? t('dash.liveSub', kpis.tasksToday || 0, kpis.successToday || 0, kpis.failedToday || 0, kpis.stoppedToday || 0)
    : t('dash.sub');
  const flagsToday = flags.filter(f => {
    const diff = (Date.now() - Date.parse(f.t)) / 1000;
    return diff < 86400;
  }).length;
  const kpiEmptyState = <span className="muted">{t('c.unavailable')}</span>;

  return (
    <div className="page">
      <div className="page-h">
        <div>
          <div className="t">{t('dash.t')}</div>
          <div className="sub">{dashboardSub}</div>
        </div>
        <div className="row">
          <select className="input" value={windowFilter} onChange={e => setWindowFilter(e.target.value)} style={{ width: 120 }}>
            <option value="24h">{t('c.last24h')}</option>
            <option value="all">all time</option>
          </select>
          <select className="input" value={runtimeFilter} onChange={e => setRuntimeFilter(e.target.value)} style={{ width: 140 }}>
            <option value="all">{t('c.allRuntimes')}</option>
            <option value="local">local</option>
            <option value="docker">docker</option>
            <option value="ssh">ssh</option>
          </select>
          <button className="btn primary" onClick={() => onNav('tasks')}>{t('c.newTask')}</button>
        </div>
      </div>

      {/* ── KPI grid ── */}
      <div className="kpi-grid">
        <KpiCard
          label={t('kpi.activeRuns')}
          value={kpis.running}
          unit={t('kpi.queuedSuffix', kpis.queued)}
          delta={canReadLiveState ? <span className="muted">{t('dash.liveRunning', kpis.running || 0)}</span> : kpiEmptyState}
        />
        <KpiCard
          label={t('kpi.tasksToday')}
          value={kpis.tasksToday}
          delta={canReadLiveState ? <span className="muted">{t('dash.liveTaskMix', kpis.successToday || 0, kpis.failedToday || 0, kpis.stoppedToday || 0)}</span> : kpiEmptyState}
        />
        <KpiCard
          label={t('kpi.successRate')}
          value={`${Math.round(kpis.successRate * 100)}`}
          unit="%"
          delta={canReadLiveState ? <span className="muted">{t('dash.liveSuccessRate', kpis.successToday || 0, kpis.tasksToday || 0)}</span> : kpiEmptyState}
        />
        <KpiCard
          label={t('kpi.tokensToday')}
          value={(kpis.dailyTokens / 1000).toFixed(1)}
          unit="k"
          delta={canReadLiveState ? <span className="muted">{t('kpi.ofCap')}</span> : kpiEmptyState}
          spark={tokenSeries.length ? <Sparkline data={tokenSeries.map(s => s.v)} w={56} h={20} /> : null}
        />
        <KpiCard
          label={t('kpi.estCost')}
          value={`$${kpis.estimatedCost.toFixed(2)}`}
          delta={canReadLiveState ? <span className="muted">{t('dash.liveCost')}</span> : kpiEmptyState}
        />
        <KpiCard
          label={t('kpi.toolCalls')}
          value={kpis.toolCalls}
          delta={canReadLiveState ? <span className="muted">{t('dash.liveKnowledgeHits', kpis.knowledgeHits || 0)}</span> : kpiEmptyState}
        />
        {/* Flags captured KPI */}
        <KpiCard
          label={t('kpi.flagsCaptured')}
          value={flags.length}
          unit=""
          delta={canReadLiveState ? <span className="green">
            <span className="muted">{t('kpi.flagsToday')}: </span>{flagsToday}
          </span> : kpiEmptyState}
          accent="green"
        />
      </div>

      {/* ── chart row 1 ── */}
      <div className="dash-row r3">
        <Panel
          title={t('dash.tokens')}
          accent={t('dash.tokensSub')}
          actions={<span className="muted" style={{ fontSize: 10.5 }}><span className="green">●</span> {t('dash.tokensLegend')}</span>}
          className="chart-card"
        >
          <div className="chart-body">
            {tokenSeries.length ? <AreaChart series={tokenSeries} height={180} color="var(--accent)" /> : <Empty>{dashboardEmptyState}</Empty>}
          </div>
        </Panel>

        <Panel title={t('dash.failure')} accent={t('dash.today')} className="chart-card">
          <div className="chart-body" style={{ display: 'grid', placeItems: 'center' }}>
            {failureDistribution.length ? <Donut data={failureDistribution} size={150} label={t('dash.donutLabel')} /> : <Empty>{dashboardEmptyState}</Empty>}
          </div>
        </Panel>

        <Panel title={t('dash.khits')} accent={t('dash.hourly')} className="chart-card">
          <div className="chart-body">
            {knowledgeHitTrend.length ? <BarTrend series={knowledgeHitTrend} height={160} color="var(--magenta)" /> : <Empty>{dashboardEmptyState}</Empty>}
          </div>
        </Panel>
      </div>

      {/* ── Flag board ── */}
      {flags.length > 0 && (
        <Panel
          title={t('dash.flagBoard')}
          accent={`${flags.length} ${t('dash.flagBoardSub')}`}
          style={{ marginBottom: 0 }}
        >
          <div style={{ padding: '4px 0' }}>
            {flags.map(f => (
              <div key={f.id} className="act-row" style={{ cursor: 'default' }}>
                <span className="time">{fmt.hhmm ? fmt.hhmm(f.t) : fmt.hh(f.t).slice(0,5)}</span>
                <span className="ico" style={{ color: 'var(--accent)' }}>⚑</span>
                <span className="ttl ellipsis">
                  <span className="dim mono" style={{ marginRight: 6 }}>{f.id}</span>
                  <span className="green mono" style={{ letterSpacing: 0 }}>{f.flag}</span>
                </span>
                <TypeBadge type={f.type} />
                <button
                  className="btn sm ghost"
                  style={{ marginLeft: 8, minWidth: 54 }}
                  onClick={() => copyFlag(f.id, f.flag)}
                >
                  {copiedId === f.id ? <span className="green">{t('c.copied')}</span> : t('c.copy')}
                </button>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* ── chart row 2 ── */}
      <div className="dash-row r2">
        <Panel title={t('dash.toolDist')} accent={t('c.last24h')}>
          <div className="chart-body" style={{ padding: 14 }}>
            {toolDistribution.length ? <MiniBarChart data={toolDistribution} color="var(--cyan)" height={140} /> : <Empty>{dashboardEmptyState}</Empty>}
          </div>
        </Panel>

        <Panel title={t('dash.alerts')} accent={`${alerts.length}`}>
          <div>
            {alerts.length ? alerts.map((a, idx) => (
              <div key={a.id || idx} className={`act-row ${a.level || ''}`}>
                <span className="time">{a.t ? fmt.hh(a.t).slice(0,5) : '—'}</span>
                <span className="ico">{a.level === 'warn' ? '⚠' : a.level === 'error' ? '✗' : '◇'}</span>
                <span className="ttl">{a.message || '—'}</span>
                <span className="meta">{a.t ? fmt.since(a.t) : t('c.ok')}</span>
              </div>
            )) : <Empty>{dashboardEmptyState}</Empty>}
          </div>
        </Panel>
      </div>

      {/* ── activity row ── */}
      <div className="dash-row r3">
        <Panel
          title={t('dash.recentTasks')}
          accent={`${recentTasks.length}`}
          actions={<button className="btn sm ghost muted" onClick={() => onNav('tasks')}>{t('c.viewAll')}</button>}
        >
          <div>
            {recentTasks.length ? recentTasks.map(tk => (
              <div key={tk.id} className="act-row" onClick={() => onNav(`tasks/${tk.id}`)} style={{ cursor: 'pointer' }}>
                <span className="time">{tk.startedAt ? fmt.hh(tk.startedAt).slice(0,5) : '—'}</span>
                <span className="ico" style={{ color: { running: 'var(--amber)', success: 'var(--accent)', failed: 'var(--red)', queued: 'var(--blue)', stopped: 'var(--fg-2)' }[tk.status] }}>●</span>
                <span className="ttl ellipsis">
                  <span className="dim" style={{ marginRight: 6 }}>{tk.id}</span>
                  {tk.title}
                </span>
                <ModeBadge mode={tk.mode} />
                <SubtypeBadge value={tk.modeSubtype} />
                <span className="meta"><StatusBadge status={tk.status} /></span>
              </div>
            )) : <Empty>{tasksEmptyState}</Empty>}
          </div>
        </Panel>

        <Panel
          title={t('dash.recentTools')}
          actions={<button className="btn sm ghost muted" onClick={() => onNav('traces')}>{t('c.tracesArrow')}</button>}
        >
          <div>
            {recentToolCalls.length ? recentToolCalls.map(c => (
              <div key={c.id} className="act-row" onClick={() => c.runId && onNav(`traces/${c.runId}`)} style={{ cursor: c.runId ? 'pointer' : 'default' }}>
                <span className="time">{c.time ? fmt.hh(c.time).slice(0,5) : '—'}</span>
                <span className="ico" style={{ color: c.status === 'running' ? 'var(--amber)' : c.status === 'failed' ? 'var(--red)' : 'var(--accent)' }}>
                  {c.status === 'running' ? '◌' : c.status === 'failed' ? '✗' : '▸'}
                </span>
                <span className="ttl ellipsis"><span className="cyan" style={{ marginRight: 6 }}>{c.tool}</span>{c.summary}</span>
                <span className="meta dim">{c.runId}</span>
              </div>
            )) : <Empty>{dashboardEmptyState}</Empty>}
          </div>
        </Panel>

        <Panel
          title={t('dash.notesArtifacts')}
          actions={<button className="btn sm ghost muted" onClick={() => onNav('knowledge')}>{t('c.browse')}</button>}
        >
          <div>
            {recentArtifacts.length === 0 && (
              <Empty>{notesArtifactsEmptyState}</Empty>
            )}
            {recentArtifacts.map(n => (
              <div key={n.id} className="act-row" onClick={() => n.runId && onNav(`traces/${n.runId}`)} style={{ cursor: n.runId ? 'pointer' : 'default' }}>
                <span className="time">{n.t ? fmt.hh(n.t).slice(0,5) : '—'}</span>
                <span className="ico" style={{ color: 'var(--accent)' }}>
                  ◌
                </span>
                <span className="ttl ellipsis">
                  <span className="dim" style={{ marginRight: 6 }}>{n.kind || 'artifact'}</span>
                  {n.title || n.location || n.path || 'artifact observed'}
                </span>
                <span className="meta dim">{n.modeSubtype || n.producer || 'observed'}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

    </div>
  );
}

function KpiCard({ label, value, unit, delta, spark, accent, onClick }) {
  return (
    <div className={`kpi ${accent ? 'kpi-accent-' + accent : ''}`} onClick={onClick} style={onClick ? { cursor: 'pointer' } : {}}>
      <div className="lbl">{label}</div>
      <div className="val">
        {value}{unit && <span className="u">{unit}</span>}
      </div>
      <div className="delta">{delta}</div>
      {spark && <div className="spark">{spark}</div>}
    </div>
  );
}

window.DashboardPage = DashboardPage;
