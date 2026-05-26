/* global React, MOCK, fmt, t */
// ============================================================
// Dashboard — KPIs x7 + 4 charts + recent activity + flag board
// ============================================================

const { useState: uD, useEffect: uDE } = React;

// Flags captured from all tasks
function useFlagBoard() {
  const [flags, setFlags] = uD(() =>
    MOCK.TASKS.filter(tk => tk.finalFlag).map(tk => ({
      id: tk.id,
      flag: tk.finalFlag,
      target: tk.target,
      t: tk.finishedAt || tk.startedAt,
      type: tk.detectedType,
    }))
  );
  const [copiedId, setCopiedId] = uD(null);

  function copyFlag(id, text) {
    navigator.clipboard?.writeText(text).catch(() => {});
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  }

  return { flags, copyFlag, copiedId };
}

function DashboardPage({ onNav }) {
  const d = MOCK.DASHBOARD;
  const [liveData, setLiveData] = uD(null);
  const { flags, copyFlag, copiedId } = useFlagBoard();

  uDE(() => {
    if (!window.IS_LIVE) return;
    window.API.getDashboard().then(data => { if (data) setLiveData(data); });
  }, []);

  const kpis = liveData?.kpis || d.kpis;
  const flagsToday = flags.filter(f => {
    const diff = (Date.now() - Date.parse(f.t)) / 1000;
    return diff < 86400;
  }).length;

  return (
    <div className="page">
      <div className="page-h">
        <div>
          <div className="t">{t('dash.t')}</div>
          <div className="sub">{t('dash.sub')}</div>
        </div>
        <div className="row">
          <button className="btn"><span className="muted">{t('c.last24h')}</span> <span className="kbd">▾</span></button>
          <button className="btn"><span className="muted">{t('c.allRuntimes')}</span> <span className="kbd">▾</span></button>
          <button className="btn primary" onClick={() => onNav('tasks')}>{t('c.newTask')}</button>
        </div>
      </div>

      {/* ── KPI grid ── */}
      <div className="kpi-grid">
        <KpiCard
          label={t('kpi.activeRuns')}
          value={kpis.running}
          unit={t('kpi.queuedSuffix', kpis.queued)}
          delta={<span><span className="amber">●</span> {t('kpi.inExploit')}</span>}
          spark={<Sparkline data={[2,1,2,1,1,1,1,1]} color="var(--amber)" w={56} h={20} />}
        />
        <KpiCard
          label={t('kpi.tasksToday')}
          value={kpis.tasksToday}
          delta={<span className="pos">{t('kpi.vsYesterday')}</span>}
          spark={<Sparkline data={[8,10,11,9,13,14,12,14]} w={56} h={20} />}
        />
        <KpiCard
          label={t('kpi.successRate')}
          value={`${Math.round(kpis.successRate * 100)}`}
          unit="%"
          delta={<span className="pos">{t('kpi.successRateDelta')}</span>}
          spark={<Sparkline data={[55,62,58,71,68,72,71,71]} w={56} h={20} />}
        />
        <KpiCard
          label={t('kpi.tokensToday')}
          value={(kpis.dailyTokens / 1000).toFixed(1)}
          unit="k"
          delta={<span className="muted">{t('kpi.ofCap')}</span>}
          spark={<Sparkline data={d.tokenSeries.map(s => s.v)} w={56} h={20} />}
        />
        <KpiCard
          label={t('kpi.estCost')}
          value={`$${kpis.estimatedCost.toFixed(2)}`}
          delta={<span className="muted">{t('kpi.costDelta')}</span>}
          spark={<Sparkline data={[0.2,1.1,2.4,3.8,4.5,6.1,7.2,8.4]} color="var(--blue)" w={56} h={20} />}
        />
        <KpiCard
          label={t('kpi.toolCalls')}
          value={kpis.toolCalls}
          delta={<span className="cyan">{t('kpi.toolMix')}</span>}
          spark={<Sparkline data={[12,18,15,22,28,24,31,28,24]} color="var(--cyan)" w={56} h={20} />}
        />
        {/* Flags captured KPI */}
        <KpiCard
          label={t('kpi.flagsCaptured')}
          value={flags.length}
          unit=""
          delta={<span className="green">
            <span className="muted">{t('kpi.flagsToday')}: </span>{flagsToday}
          </span>}
          spark={<Sparkline data={[0,0,1,0,2,0,1,flags.length]} color="var(--accent)" w={56} h={20} />}
          accent="green"
          onClick={() => {}}
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
            <AreaChart series={d.tokenSeries} height={180} color="var(--accent)" />
          </div>
        </Panel>

        <Panel title={t('dash.failure')} accent={t('dash.today')} className="chart-card">
          <div className="chart-body" style={{ display: 'grid', placeItems: 'center' }}>
            <Donut data={d.failureDistribution} size={150} label={t('dash.donutLabel')} />
          </div>
        </Panel>

        <Panel title={t('dash.khits')} accent={t('dash.hourly')} className="chart-card">
          <div className="chart-body">
            <BarTrend series={d.knowledgeHitTrend} height={160} color="var(--magenta)" />
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
            <MiniBarChart data={d.toolDistribution} color="var(--cyan)" height={140} />
          </div>
        </Panel>

        <Panel title={t('dash.alerts')} accent={`${d.alerts.length + 2}`}>
          <div>
            <div className="act-row warn">
              <span className="time">{fmt.hh(d.alerts[0].t).slice(0,5)}</span>
              <span className="ico">⚠</span>
              <span className="ttl">{t('dash.alertA')}</span>
              <span className="meta">{fmt.since(d.alerts[0].t)}</span>
            </div>
            <div className="act-row info">
              <span className="time">{fmt.hh(d.alerts[1].t).slice(0,5)}</span>
              <span className="ico">◇</span>
              <span className="ttl">{t('dash.alertB')}</span>
              <span className="meta">{fmt.since(d.alerts[1].t)}</span>
            </div>
            <div className="act-row info">
              <span className="time">{fmt.hh(d.alerts[2].t).slice(0,5)}</span>
              <span className="ico">◇</span>
              <span className="ttl">{t('dash.alertC')}</span>
              <span className="meta">{fmt.since(d.alerts[2].t)}</span>
            </div>
            <div className="act-row info">
              <span className="time">10:30</span>
              <span className="ico">◇</span>
              <span className="ttl">{t('dash.alertD')}</span>
              <span className="meta">{t('c.healthy')}</span>
            </div>
            <div className="act-row">
              <span className="time">10:00</span>
              <span className="ico" style={{ color: 'var(--accent)' }}>✓</span>
              <span className="ttl">{t('dash.alertE')}</span>
              <span className="meta">{t('c.ok')}</span>
            </div>
          </div>
        </Panel>
      </div>

      {/* ── activity row ── */}
      <div className="dash-row r3">
        <Panel
          title={t('dash.recentTasks')}
          accent={`${d.recentTasks.length}`}
          actions={<button className="btn sm ghost muted" onClick={() => onNav('tasks')}>{t('c.viewAll')}</button>}
        >
          <div>
            {d.recentTasks.map(tk => (
              <div key={tk.id} className="act-row" onClick={() => onNav('tasks')} style={{ cursor: 'pointer' }}>
                <span className="time">{tk.startedAt ? fmt.hh(tk.startedAt).slice(0,5) : '—'}</span>
                <span className="ico" style={{ color: { running: 'var(--amber)', success: 'var(--accent)', failed: 'var(--red)', queued: 'var(--blue)', stopped: 'var(--fg-2)' }[tk.status] }}>●</span>
                <span className="ttl ellipsis"><span className="dim" style={{ marginRight: 6 }}>{tk.id}</span>{tk.title}</span>
                <span className="meta"><StatusBadge status={tk.status} /></span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title={t('dash.recentTools')}
          actions={<button className="btn sm ghost muted" onClick={() => onNav('traces')}>{t('c.tracesArrow')}</button>}
        >
          <div>
            {d.recentToolCalls.map(c => (
              <div key={c.id} className="act-row">
                <span className="time">{fmt.hh(c.time).slice(0,5)}</span>
                <span className="ico" style={{ color: c.status === 'running' ? 'var(--amber)' : c.status === 'failed' ? 'var(--red)' : 'var(--accent)' }}>
                  {c.status === 'running' ? '◌' : c.status === 'failed' ? '✗' : '▸'}
                </span>
                <span className="ttl ellipsis"><span className="cyan" style={{ marginRight: 6 }}>{c.tool}</span>{c.summary}</span>
                <span className="meta dim">{c.runId}</span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title={t('dash.notesArtifacts')}
          actions={<button className="btn sm ghost muted">{t('c.browse')}</button>}
        >
          <div>
            {d.recentNotes.map(n => (
              <div key={n.id} className="act-row">
                <span className="time">{fmt.hh(n.t).slice(0,5)}</span>
                <span className="ico" style={{ color: 'var(--amber)' }}>✎</span>
                <span className="ttl ellipsis">{n.text}</span>
                <span className="meta dim">{n.tag}</span>
              </div>
            ))}
            {d.recentArtifacts.map(a => (
              <div key={a.id} className="act-row">
                <span className="time">{fmt.hh(a.t).slice(0,5)}</span>
                <span className="ico" style={{ color: 'var(--magenta)' }}>◫</span>
                <span className="ttl ellipsis"><span className="bright">{a.name}</span></span>
                <span className="meta dim">{a.kind}</span>
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
