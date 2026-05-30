/* global React, fmt, t, downloadJson, ModeBadge, SubtypeBadge */
// ============================================================
// Traces — list page + detail page (timeline / graph / data)
// ============================================================

const { useState: uS, useEffect: uE, useRef: uR, useMemo: uM } = React;

function currentConnectionState() {
  if (window.API?.getConnectionState) return window.API.getConnectionState();
  return {
    status: window.IS_LIVE ? 'connected' : 'disconnected',
    isLive: Boolean(window.IS_LIVE),
  };
}

function TracesPage({ runId, onNav }) {
  if (runId) return <TraceDetail runId={runId} onNav={onNav} />;
  return <TraceList onNav={onNav} />;
}

function TraceList({ onNav }) {
  const [filter, setFilter] = uS('all');
  const [windowFilter, setWindowFilter] = uS('24h');
  const [targetFilter, setTargetFilter] = uS('all');
  const [targetOptions, setTargetOptions] = uS(['all']);
  const [q, setQ] = uS('');
  const [apiTraces, setApiTraces] = uS(null);
  const [connection, setConnection] = uS(() => currentConnectionState());
  const getTraces = window.API?.getTraces;
  const subscribeEvents = window.API?.subscribeEvents;
  const tracesAvailable = ['connected', 'degraded'].includes(connection.status)
    && typeof getTraces === 'function';
  const tracesUnavailableReason = connection?.status !== 'connected' && connection?.status !== 'degraded'
    ? t('c.notConnected')
    : typeof getTraces === 'function'
      ? ''
      : t('c.notWired');

  uE(() => {
    const handler = (e) => {
      setConnection(
        e.detail?.connection
        || currentConnectionState()
      );
    };
    window.addEventListener('fh:connection', handler);
    return () => window.removeEventListener('fh:connection', handler);
  }, []);

  uE(() => {
    if (!tracesAvailable || typeof getTraces !== 'function') {
      setApiTraces(null);
      setTargetOptions(['all']);
      return;
    }

    getTraces({ window: windowFilter, target: targetFilter }).then(data => {
      setApiTraces(Array.isArray(data?.items) ? data.items : []);
      setTargetOptions(Array.isArray(data?.filters?.targets) ? data.filters.targets : ['all']);
      if (data?.filters?.target && data.filters.target !== targetFilter) setTargetFilter(data.filters.target);
    });
  }, [getTraces, targetFilter, tracesAvailable, windowFilter]);

  uE(() => {
    if (!tracesAvailable || typeof subscribeEvents !== 'function' || typeof getTraces !== 'function') return;
    return subscribeEvents(ev => {
      if (ev.type === 'task_created' || ev.type === 'task_status') {
        getTraces({ window: windowFilter, target: targetFilter }).then(data => {
          setApiTraces(Array.isArray(data?.items) ? data.items : []);
          setTargetOptions(Array.isArray(data?.filters?.targets) ? data.filters.targets : ['all']);
          if (data?.filters?.target && data.filters.target !== targetFilter) setTargetFilter(data.filters.target);
        });
      }
    });
  }, [getTraces, subscribeEvents, targetFilter, tracesAvailable, windowFilter]);

  const sourceTraces = Array.isArray(apiTraces) ? apiTraces : [];
  const runs = sourceTraces.filter(r => {
    if (filter !== 'all' && r.status !== filter) return false;
    if (q) {
      const haystack = `${r.id || ''} ${r.taskId || ''} ${r.target || ''} ${r.finalFlag || ''}`.toLowerCase();
      if (!haystack.includes(q.toLowerCase())) return false;
    }
    return true;
  });
  const filterKeys = ['all', 'running', 'success', 'failed', 'stopped'];
  const tracesEmptyState = tracesAvailable ? t('tasks.noMatch') : (tracesUnavailableReason || t('c.unavailable'));
  return (
    <div className="page">
      <div className="page-h">
        <div>
          <div className="t">{t('tr.t')}</div>
          <div className="sub">{t('tr.sub')}</div>
        </div>
        <div className="row">
          <select className="input" value={windowFilter} onChange={e => setWindowFilter(e.target.value)} style={{ width: 120 }}>
            <option value="24h">{t('c.last24h')}</option>
            <option value="all">all time</option>
          </select>
          <select className="input" value={targetFilter} onChange={e => setTargetFilter(e.target.value)} style={{ width: 220 }}>
            {targetOptions.map(target => (
              <option key={target} value={target}>{target === 'all' ? t('c.allTargets') : target}</option>
            ))}
          </select>
          <button className="btn" onClick={() => downloadJson(`traces_${new Date().toISOString().replace(/[:.]/g, '-')}.json`, runs)}>⬇ {t('c.export')}</button>
        </div>
      </div>

      <Panel>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-1)', display: 'flex', gap: 6 }}>
          {filterKeys.map(f => (
            <span key={f} className={`filter-pill ${filter === f ? 'on' : ''}`} onClick={() => setFilter(f)}>{t('flt.' + f)}</span>
          ))}
          <input
            className="input"
            placeholder={t('tr.filterPh')}
            style={{ marginLeft: 'auto', maxWidth: 280 }}
            value={q}
            onChange={e => setQ(e.target.value)}
          />
        </div>
        {runs.length === 0 ? (
          <Empty>{tracesEmptyState}</Empty>
        ) : (
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
                  <td>
                    <div className="muted mono">{r.taskId}</div>
                    <div className="row gap-8" style={{ marginTop: 4, flexWrap: 'wrap' }}>
                      <ModeBadge mode={r.mode} />
                      <SubtypeBadge value={r.modeSubtype} />
                    </div>
                  </td>
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
        )}
      </Panel>
    </div>
  );
}

// ----------------------------------------------------------------
// TraceDetail
// ----------------------------------------------------------------
function TraceDetail({ runId, onNav }) {
  const [run, setRun] = uS(null);
  const [connection, setConnection] = uS(() => currentConnectionState());
  const getTrace = window.API?.getTrace;
  const traceDetailAvailable = ['connected', 'degraded'].includes(connection.status)
    && typeof getTrace === 'function';
  const traceDetailUnavailableReason = connection?.status !== 'connected' && connection?.status !== 'degraded'
    ? t('c.notConnected')
    : typeof getTrace === 'function'
      ? ''
      : t('c.notWired');

  uE(() => {
    const handler = (e) => {
      setConnection(
        e.detail?.connection
        || currentConnectionState()
      );
    };
    window.addEventListener('fh:connection', handler);
    return () => window.removeEventListener('fh:connection', handler);
  }, []);

  uE(() => {
    let done = false;
    setRun(null);
    if (!traceDetailAvailable || typeof getTrace !== 'function') {
      return () => { done = true; };
    }

    getTrace(runId).then(data => {
      if (!done && data && data.id) setRun(data);
    });

    return () => { done = true; };
  }, [getTrace, runId, traceDetailAvailable]);

  const liveFallbackRun = {
    id: runId || 'trace',
    taskId: '—',
    target: '—',
    status: 'stopped',
    startedAt: null,
    finishedAt: null,
    durationMs: null,
    totalSteps: 0,
    totalToolCalls: 0,
    totalTokens: 0,
    inputTokens: 0,
    outputTokens: 0,
    finalFlag: null,
    timeline: [],
    toolEvents: [],
  };
  const resolvedRun = run || liveFallbackRun;
  const [tab, setTab] = uS('timeline');
  const [drawer, setDrawer] = uS(null);
  const isActive = resolvedRun.status === 'running';
  const replayAvailable = typeof window.API?.replayTrace === 'function';
  const timeline = Array.isArray(resolvedRun.timeline) && resolvedRun.timeline.length
    ? resolvedRun.timeline
    : resolveTraceTimeline(resolvedRun);
  const toolAuditEvents = Array.isArray(resolvedRun.toolEvents)
    ? resolvedRun.toolEvents.map((event, index) => normalizeToolAuditEvent(event, index))
    : [];
  const outcomeEvents = Array.isArray(resolvedRun.outcomeEvents)
    ? resolvedRun.outcomeEvents.map((event, index) => normalizeTraceEvent(event, index, 'outcome'))
    : [];
  const sessionArtifacts = Array.isArray(resolvedRun.sessionArtifacts) ? resolvedRun.sessionArtifacts : [];
  const latestCheckpoint = resolvedRun.latestCheckpoint && typeof resolvedRun.latestCheckpoint === 'object'
    ? resolvedRun.latestCheckpoint
    : null;
  const hasObservedToolIO = Array.isArray(resolvedRun.toolEvents) && resolvedRun.toolEvents.length > 0;
  const graph = uM(() => buildTraceGraph(timeline, resolvedRun), [timeline, resolvedRun.id, resolvedRun.status, resolvedRun.startedAt]);
  const traceEmptyState = traceDetailAvailable ? t('tr.empty.timeline') : (traceDetailUnavailableReason || t('c.unavailable'));

  async function handleReplay() {
    if (!replayAvailable) return;
    const replayResult = await window.API.replayTrace(resolvedRun.id);
    if (replayResult?.id && onNav) onNav(`tasks/${replayResult.id}`);
  }

  uE(() => {
    window.dispatchEvent(new CustomEvent('fh:route-label', {
      detail: { label: resolvedRun.id || runId || 'trace' }
    }));
  }, [resolvedRun.id, runId]);

  uE(() => {
    if (!window.IS_LIVE) return;
    const handler = (event) => {
      const ev = event?.detail || {};
      if (ev.run_id !== resolvedRun.id && ev.task_id !== resolvedRun.taskId) return;
      const at = ev.t || ev.timestamp || new Date().toISOString();

      if (ev.type === 'task_status') {
        const updates = ev.updates || {};
        setRun(prev => {
          const base = prev || liveFallbackRun;
          const next = {
            ...base,
            ...updates,
            totalTokens: updates.tokensUsed != null ? updates.tokensUsed : base.totalTokens,
            totalToolCalls: updates.toolCalls != null ? updates.toolCalls : base.totalToolCalls,
            totalSteps: updates.toolCalls != null
              ? Math.max(base.totalSteps || 0, updates.toolCalls)
              : base.totalSteps,
          };
          if (updates.status && updates.status !== 'running') {
            const finishEventId = `evt_finish_${updates.status}_${updates.finishedAt || at}`;
            const existing = Array.isArray(base.timeline) ? base.timeline : [];
            const already = existing.some(item => item.id === finishEventId);
            if (!already) {
              next.timeline = [...existing, {
                id: finishEventId,
                t: updates.finishedAt || at,
                type: updates.finalFlag ? 'verify' : 'system',
                kind: updates.finalFlag ? 'verifier.flag.verified' : `task.${updates.status}`,
                title: updates.finalFlag ? 'flag verified' : `task ${updates.status}`,
                summary: updates.finalFlag || updates.stopReason || updates.status,
                status: 'done',
                tokens: updates.tokensUsed || base.totalTokens || 0,
              }];
            }
          }
          return next;
        });
        return;
      }

      if (ev.type === 'tool_call') {
        setRun(prev => {
          const base = prev || liveFallbackRun;
          const existing = Array.isArray(base.timeline) ? base.timeline : [];
          const eventId = `evt_tool_${ev.tool || 'tool'}_${at}`;
          if (existing.some(item => item.id === eventId)) return base;
          return {
            ...base,
            timeline: [...existing, {
              id: eventId,
              t: at,
              type: 'tool',
              kind: ev.kind || 'tool.called',
              title: ev.tool ? `${ev.tool} called` : 'tool called',
              summary: ev.summary || 'live tool event',
              status: 'running',
              tool: ev.tool || null,
              tokens: 0,
            }],
          };
        });
        return;
      }

      if (ev.type === 'tool.finished') {
        setRun(prev => {
          const base = prev || liveFallbackRun;
          const existing = Array.isArray(base.timeline) ? base.timeline : [];
          const eventId = `evt_tool_finished_${ev.tool || 'tool'}_${at}`;
          if (existing.some(item => item.id === eventId)) return base;
          return {
            ...base,
            timeline: [...existing, {
              id: eventId,
              t: at,
              type: 'tool',
              kind: ev.kind || 'tool.finished',
              title: ev.tool ? `${ev.tool} finished` : 'tool finished',
              summary: ev.summary || (ev.success === false ? 'tool failed' : 'tool completed'),
              status: 'done',
              tool: ev.tool || null,
              durationMs: typeof ev.duration_ms === 'number' ? ev.duration_ms : null,
              output: ev.output || '',
              tokens: 0,
            }],
          };
        });
        return;
      }

      if (ev.type === 'knowledge.retrieved') {
        setRun(prev => {
          const base = prev || liveFallbackRun;
          const existing = Array.isArray(base.timeline) ? base.timeline : [];
          const eventId = `evt_knowledge_${ev.source || 'knowledge'}_${at}`;
          if (existing.some(item => item.id === eventId)) return base;
          return {
            ...base,
            timeline: [...existing, {
              id: eventId,
              t: at,
              type: 'knowledge',
              kind: ev.kind || 'knowledge.retrieved',
              title: 'knowledge retrieved',
              summary: ev.summary || ev.source || 'knowledge hit observed',
              status: 'done',
              tool: ev.source || null,
              output: ev.output || '',
              tokens: 0,
            }],
          };
        });
        return;
      }

      if (ev.type === 'note.created') {
        setRun(prev => {
          const base = prev || liveFallbackRun;
          const existing = Array.isArray(base.timeline) ? base.timeline : [];
          const eventId = `evt_note_${at}`;
          if (existing.some(item => item.id === eventId)) return base;
          return {
            ...base,
            timeline: [...existing, {
              id: eventId,
              t: at,
              type: 'note',
              kind: ev.kind || 'note.created',
              title: 'note created',
              summary: ev.summary || 'note saved',
              status: 'done',
              output: ev.output || '',
              tokens: 0,
            }],
          };
        });
        return;
      }

      if (ev.type === 'hint') {
        setRun(prev => {
          const base = prev || liveFallbackRun;
          const existing = Array.isArray(base.timeline) ? base.timeline : [];
          const eventId = `evt_hint_${at}`;
          if (existing.some(item => item.id === eventId)) return base;
          return {
            ...base,
            timeline: [...existing, {
              id: eventId,
              t: at,
              type: 'system',
              kind: 'task.hint',
              title: 'hint accepted',
              summary: ev.text || 'hint injected',
              status: 'done',
              tokens: 0,
            }],
          };
        });
      }
    };

    window.addEventListener('fh:event', handler);
    return () => window.removeEventListener('fh:event', handler);
  }, [resolvedRun.id, resolvedRun.taskId, runId]);

  return (
    <div className="page" style={{ minHeight: 0 }}>
      <div className="page-h">
        <div>
          <div className="t row gap-12" style={{ alignItems: 'center' }}>
            <span className="dim" style={{ cursor: 'pointer', fontSize: 13 }} onClick={() => onNav('traces')}>{t('tr.back')}</span>
            <span>{resolvedRun.id}</span>
            <ModeBadge mode={resolvedRun.mode} />
            <SubtypeBadge value={resolvedRun.modeSubtype} />
            <StatusBadge status={resolvedRun.status} />
          </div>
          <div className="sub">{t('c.task')} <b className="bright">{resolvedRun.taskId}</b> · {t('c.target')} <b className="bright">{resolvedRun.target}</b></div>
        </div>
        <div className="row">
          <button className="btn ghost" onClick={() => downloadJson(`${resolvedRun.id}.json`, resolvedRun)}>⬇ {t('c.json')}</button>
          <button className="btn ghost" onClick={() => onNav && onNav(`tasks/${resolvedRun.taskId}`)}>{t('c.openTask')}</button>
          <button className="btn" disabled={!replayAvailable} title={!replayAvailable ? t('tr.replayUnavailable') : ''} onClick={handleReplay}>⟲ {t('c.replay')}</button>
        </div>
      </div>

      <Panel>
        {resolvedRun.detailSource && (
          <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-1)', fontSize: 11, color: 'var(--fg-2)', display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <span>session: <span className="mono">{resolvedRun.detailSource.session || '—'}</span></span>
            <span>metrics: <span className="mono">{resolvedRun.detailSource.metrics || '—'}</span></span>
            <span>tool I/O: <span className={hasObservedToolIO ? 'green' : 'muted'}>{hasObservedToolIO ? 'observed' : 'not captured'}</span></span>
          </div>
        )}
        <div className="trace-detail-head">
          <Kv k={t('c.started')}   v={resolvedRun.startedAt ? (fmt.hh(resolvedRun.startedAt) + ' · ' + fmt.since(resolvedRun.startedAt)) : '—'} />
          <Kv
            k={t('c.duration')}
            v={resolvedRun.durationMs != null
              ? (resolvedRun.durationMs/1000).toFixed(1) + 's'
              : (resolvedRun.status === 'running' ? t('tr.stillRunning') : '—')}
          />
          <Kv k={t('c.steps')}     v={resolvedRun.totalSteps} />
          <Kv k={t('c.toolCalls')} v={resolvedRun.totalToolCalls} />
          <Kv k={t('c.tokens')}    v={`${(resolvedRun.totalTokens || 0).toLocaleString()} · ${((resolvedRun.inputTokens || 0)/1000).toFixed(1)}k in / ${((resolvedRun.outputTokens || 0)/1000).toFixed(1)}k out`} />
          {resolvedRun.finalFlag && <Kv k={t('c.flag')} v={<span className="green">{resolvedRun.finalFlag}</span>} />}
        </div>

        {toolAuditEvents.length > 0 && (
          <div style={{ padding: '12px 14px', borderTop: '1px solid var(--line-1)', borderBottom: '1px solid var(--line-1)' }}>
            <div className="hk" style={{ marginBottom: 8 }}>Tool audit</div>
            <div className="tool-audit-list" style={{ display: 'grid', gap: 8 }}>
              {toolAuditEvents.map(event => (
                <button
                  key={event.id}
                  type="button"
                  className="card"
                  onClick={() => setDrawer(event)}
                  style={{ width: '100%', textAlign: 'left', padding: '10px 12px', background: 'transparent', cursor: 'pointer' }}
                >
                  <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                    <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
                      <span className="cyan mono">{event.tool || 'tool'}</span>
                      <span className="dim">{event.title}</span>
                    </div>
                    <div className="row gap-8">
                      <span className={`mono ${event.status === 'failed' ? 'red' : event.status === 'running' ? 'amber' : 'green'}`}>
                        {event.status || 'done'}
                      </span>
                      <span className="dim">{fmt.hh(event.t).slice(0, 8)}</span>
                    </div>
                  </div>
                  <div className="muted" style={{ marginTop: 6 }}>{event.summary || 'tool event observed'}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {(latestCheckpoint || outcomeEvents.length > 0) && (
          <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--line-1)', display: 'grid', gap: 12 }}>
            {latestCheckpoint && (
              <div className="card" style={{ padding: '12px 14px' }}>
                <div className="hk" style={{ marginBottom: 8 }}>Latest checkpoint</div>
                <div className="row gap-12" style={{ flexWrap: 'wrap', fontSize: 12 }}>
                  <span className="mono bright">{latestCheckpoint.label || latestCheckpoint.checkpointId || 'checkpoint'}</span>
                  <span className="muted">stop: {latestCheckpoint.stopReason || '—'}</span>
                  <span className="muted">artifacts: {latestCheckpoint.artifactCount ?? 0}</span>
                  <span className="muted">observations: {latestCheckpoint.observationCount ?? 0}</span>
                  <span className="dim">{latestCheckpoint.t ? fmt.hh(latestCheckpoint.t).slice(0, 8) : '—'}</span>
                </div>
                {(Array.isArray(latestCheckpoint.runtimeFlags) && latestCheckpoint.runtimeFlags.length > 0) && (
                  <div className="muted" style={{ marginTop: 6 }}>
                    runtime flags: {latestCheckpoint.runtimeFlags.join(', ')}
                  </div>
                )}
              </div>
            )}

            {outcomeEvents.length > 0 && (
              <div>
                <div className="hk" style={{ marginBottom: 8 }}>Run outcomes</div>
                <div className="tool-audit-list" style={{ display: 'grid', gap: 8 }}>
                  {resolvedRun.outcomeEvents.map((rawEvent, index) => {
                    const event = normalizeTraceEvent(rawEvent, index, 'outcome');
                    return (
                      <button
                        key={event.id}
                        type="button"
                        className="card"
                        onClick={() => setDrawer(event)}
                        style={{ width: '100%', textAlign: 'left', padding: '10px 12px', background: 'transparent', cursor: 'pointer' }}
                      >
                        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                          <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
                            <span className="bright">{event.title}</span>
                            <span className="dim mono">{event.kind}</span>
                          </div>
                          <div className="row gap-8">
                            <span className={`mono ${event.status === 'failed' ? 'red' : event.status === 'running' ? 'amber' : 'green'}`}>
                              {event.status || 'done'}
                            </span>
                            <span className="dim">{fmt.hh(event.t).slice(0, 8)}</span>
                          </div>
                        </div>
                        <div className="muted" style={{ marginTop: 6 }}>{event.summary || 'outcome observed'}</div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

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

        {tab === 'timeline' && <TimelineView events={timeline} onPick={setDrawer} isActive={isActive} emptyState={traceEmptyState} />}
        {tab === 'graph' && (
          graph.nodes.length > 0
            ? <GraphView graph={graph} run={resolvedRun} onPick={setDrawer} />
            : <Empty>{isActive ? t('tr.empty.awaitingFirstEvent') : t('tr.empty.graph')}</Empty>
        )}
        {tab === 'data' && <DataTables run={resolvedRun} events={timeline} />}
      </Panel>

      {drawer && <EventDrawer event={drawer} run={resolvedRun} onClose={() => setDrawer(null)} />}
    </div>
  );
}

function Kv({ k, v }) { return (
  <div className="kv">
    <span className="k">{k}</span>
    <span className="v">{v}</span>
  </div>
);}

function normalizeToolAuditEvent(event, index) {
  const tool = event?.tool || 'tool';
  return {
    ...normalizeTraceEvent({
      ...event,
      id: event?.id || `tool_audit_${tool}_${index}`,
      type: event?.type || 'tool',
      kind: event?.kind || 'tool_observed',
      title: event?.title
        || `${tool} ${event?.kind === 'tool_called' ? 'called' : event?.kind === 'tool_finished' ? 'finished' : 'observed'}`,
      summary: event?.summary
        || (typeof event?.output === 'string' && event.output.trim())
        || (typeof event?.input === 'string' && event.input.trim())
        || 'tool event observed',
      status: event?.status
        || (event?.kind === 'tool_called' ? 'running' : event?.success === false ? 'failed' : 'done'),
    }, index, 'tool_audit'),
    tool,
  };
}

function normalizeTraceEvent(event, index, prefix = 'event') {
  return {
    id: event?.id || `${prefix}_${index}`,
    type: event?.type || 'system',
    kind: event?.kind || `${prefix}_observed`,
    title: event?.title || 'event observed',
    summary: event?.summary || '',
    status: event?.status || 'done',
    t: event?.t || new Date().toISOString(),
    input: event?.input || '',
    output: event?.output || '',
    durationMs: typeof event?.durationMs === 'number' ? event.durationMs : null,
    success: event?.success,
    tokens: typeof event?.tokens === 'number' ? event.tokens : 0,
    tool: event?.tool || null,
  };
}

// ----------------------------------------------------------------
// Timeline
// ----------------------------------------------------------------
function typeLabel(type) {
  return t('tr.type.' + type);
}

function TimelineView({ events, onPick, isActive, emptyState }) {
  const [hover, setHover] = uS(null);

  if (!events.length && !isActive) {
    return <Empty>{emptyState || t('tr.empty.timeline')}</Empty>;
  }

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
function graphNodeMeta(event, isTerminal) {
  switch (event.type) {
    case 'task': return { color: 'green', tag: 'TASK', label: event.title || 'task started' };
    case 'verify': return { color: 'green', tag: 'VERIFY', label: event.title || 'flag verified' };
    case 'tool': return { color: event.status === 'failed' ? 'red' : 'cyan', tag: 'TOOL', label: event.tool || event.title || 'tool' };
    case 'knowledge': return { color: 'blue', tag: 'KNOWLEDGE', label: event.summary || event.title || 'knowledge' };
    case 'note': return { color: 'amber', tag: 'NOTE', label: event.summary || event.title || 'note' };
    case 'plan': return { color: 'magenta', tag: 'PLAN', label: event.title || 'plan' };
    case 'err': return { color: 'red', tag: 'ERROR', label: event.summary || event.title || 'error' };
    default:
      return { color: isTerminal ? 'green' : 'magenta', tag: (event.type || 'system').toUpperCase(), label: event.summary || event.title || event.type || 'system' };
  }
}

function buildTraceGraph(events, run) {
  const ordered = (events || [])
    .filter(e => e && e.id)
    .slice()
    .sort((a, b) => {
      const ta = Date.parse(a.t || 0) || 0;
      const tb = Date.parse(b.t || 0) || 0;
      if (ta !== tb) return ta - tb;
      return String(a.id).localeCompare(String(b.id));
    });

  const nodes = ordered.map((event, idx) => {
    const meta = graphNodeMeta(event, idx === ordered.length - 1 && run.status !== 'running');
    const col = idx % 4;
    const row = Math.floor(idx / 4);
    return {
      id: `graph_${event.id}`,
      event,
      x: 30 + col * 190,
      y: 46 + row * 92,
      kind: meta.color,
      k: meta.tag,
      t: meta.label,
      isRunning: event.status === 'running',
    };
  });

  const edges = [];
  const active = [];
  for (let i = 0; i < nodes.length - 1; i++) {
    const pair = [nodes[i].id, nodes[i + 1].id];
    edges.push(pair);
    if (nodes[i + 1].isRunning || (run.status === 'running' && i === nodes.length - 2)) {
      active.push(pair);
    }
  }

  return {
    nodes,
    edges,
    active,
    height: Math.max(480, 110 + Math.ceil(Math.max(nodes.length, 1) / 4) * 92),
  };
}

function GraphView({ graph, run, onPick }) {
  const g = graph;
  const nodeById = Object.fromEntries(g.nodes.map(n => [n.id, n]));
  const activeSet = new Set(g.active.map(([a,b]) => `${a}-${b}`));

  return (
    <div className="graph-shell" style={{ height: g.height }}>
      <div style={{ position: 'absolute', top: 10, left: 14, fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.16em', textTransform: 'uppercase' }}>
        {`${run.id} · graph · ${g.nodes.length} nodes / ${g.edges.length} edges`}
      </div>
      <div style={{ position: 'absolute', top: 10, right: 14, display: 'flex', gap: 10, fontSize: 10, color: 'var(--fg-2)' }}>
        <LegendDot c="var(--accent)" t={t('tr.graph.taskVerify')} />
        <LegendDot c="var(--cyan)" t={t('tr.graph.tool')} />
        <LegendDot c="var(--magenta)" t="plan / system" />
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
          onClick={() => onPick(n.event)}
        >
          <div className="gk">{n.k}</div>
          <div className="gt">{n.t}</div>
          {n.isRunning && (
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
  const artifacts = Array.isArray(run.sessionArtifacts) ? run.sessionArtifacts : [];
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
        {tab === 'artifacts' && (
          artifacts.length > 0
            ? <ArtifactsTable artifacts={artifacts} />
            : <Empty>{t('tr.data.noArtifacts')}</Empty>
        )}
        {tab === 'files' && <Empty>{t('tr.data.noFiles')}</Empty>}
      </div>
    </>
  );
}

function ArtifactsTable({ artifacts }) {
  return (
    <table className="k-table">
      <thead><tr><th>{t('c.time')}</th><th>{t('c.kind')}</th><th>{t('c.title')}</th><th>{t('c.target')}</th><th>{t('c.summary')}</th></tr></thead>
      <tbody>
        {artifacts.map(item => (
          <tr key={item.artifactId || `${item.kind}_${item.title}`}>
            <td className="muted mono">{item.t ? fmt.hh(item.t).slice(0, 8) : '—'}</td>
            <td><span className="chip cyan">{item.kind || 'artifact'}</span></td>
            <td className="bright">{item.title || 'artifact'}</td>
            <td className="ellipsis" style={{ maxWidth: 360 }}>{item.location || item.path || '—'}</td>
            <td className="muted">{item.producer || item.metadata?.category || 'observed'}</td>
          </tr>
        ))}
      </tbody>
    </table>
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
  const hasObservedInput = typeof e.input === 'string' && e.input.length > 0;
  const hasObservedOutput = typeof e.output === 'string' && e.output.length > 0;
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
            <pre className="code-block">{hasObservedInput ? e.input : getToolInput(e)}</pre>
            <div className="muted" style={{ fontSize: 10, margin: '8px 0 4px' }}>{t('tr.dr.output')}</div>
            <pre className="code-block">{hasObservedOutput ? e.output : getToolOutput(e)}</pre>
            {!hasObservedInput && !hasObservedOutput && (
              <div className="muted" style={{ fontSize: 10, marginTop: 6 }}>{t('tr.empty.toolIo')}</div>
            )}
          </div>
        )}

        {e.type === 'knowledge' && (
          <div className="section">
            <div className="h">{t('tr.dr.chunks')}</div>
            <pre className="code-block">{e.output || e.summary || t('tr.empty.chunkExcerpt')}</pre>
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
  return t('tr.dr.noOutput');
}
function getToolOutput(e) {
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

function resolveTraceTimeline(run) {
  if (Array.isArray(run?.timeline) && run.timeline.length) return run.timeline;
  if (!run?.startedAt || run?.target === '—') return [];
  return synthTimeline(run);
}

window.TracesPage = TracesPage;
