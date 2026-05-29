/* global React, fmt, t, NewTaskModal, ModeBadge, SubtypeBadge, fileIcon, downloadJson */
// ============================================================
// Tasks — list (left) + detail (conversation + side panel)
// ============================================================

const { useState: useStateT, useEffect: useEffectT, useRef: useRefT, useMemo: useMemoT } = React;

function currentConnectionState() {
  if (window.API?.getConnectionState) return window.API.getConnectionState();
  return {
    status: window.IS_LIVE ? 'connected' : 'disconnected',
    isLive: Boolean(window.IS_LIVE),
  };
}

function taskSummaryLabel(tasks) {
  const items = Array.isArray(tasks) ? tasks : [];
  const counts = items.reduce((acc, task) => {
    const key = String(task?.status || '').toLowerCase();
    if (Object.prototype.hasOwnProperty.call(acc, key)) acc[key] += 1;
    return acc;
  }, {
    running: 0,
    queued: 0,
    success: 0,
    failed: 0,
    stopped: 0,
  });

  return t(
    'tasks.sub',
    items.length,
    counts.running,
    counts.queued,
    counts.success,
    counts.failed,
    counts.stopped,
  );
}

function TasksPage({ taskId, onNav, taskViewMode }) {
  const initialActiveId = taskId || '';
  const [activeId, setActive] = useStateT(initialActiveId);
  const [filter, setFilter] = useStateT('all');
  const [q, setQ] = useStateT('');
  const [showModal, setShowModal] = useStateT(false);
  const [tasks, setTasks] = useStateT([]);
  const [connection, setConnection] = useStateT(() => currentConnectionState());
  const getTasks = window.API?.getTasks;
  const subscribeEvents = window.API?.subscribeEvents;
  const tasksAvailable = ['connected', 'degraded'].includes(connection.status)
    && typeof getTasks === 'function';
  const tasksUnavailableReason = connection?.status !== 'connected' && connection?.status !== 'degraded'
    ? t('c.notConnected')
    : typeof getTasks === 'function'
      ? ''
      : t('c.notWired');

  // ⌘K "新建任务" command opens this modal from anywhere
  useEffectT(() => {
    const handler = () => setShowModal(true);
    window.addEventListener('fh:open-new-task', handler);
    return () => window.removeEventListener('fh:open-new-task', handler);
  }, []);

  useEffectT(() => {
    const handler = (e) => {
      setConnection(
        e.detail?.connection
        || currentConnectionState()
      );
    };
    window.addEventListener('fh:connection', handler);
    return () => window.removeEventListener('fh:connection', handler);
  }, []);

  useEffectT(() => {
    if (!tasksAvailable || typeof getTasks !== 'function') {
      setTasks([]);
      return;
    }

    getTasks().then(data => {
      if (data && Array.isArray(data)) {
        setTasks(data);
      }
    });
  }, [getTasks, tasksAvailable]);

  useEffectT(() => {
    if (taskId) setActive(taskId);
  }, [taskId]);

  useEffectT(() => {
    if (!tasks.length) return;
    const hasActive = tasks.some(tk => tk.id === activeId);
    if (!hasActive) {
      setActive(tasks[0].id);
    } else if (taskId && taskId !== activeId) {
      setActive(taskId);
    }
  }, [tasks, activeId, taskId]);

  // Subscribe to SSE task status updates
  useEffectT(() => {
    if (!tasksAvailable || typeof subscribeEvents !== 'function') return;
    return subscribeEvents(ev => {
      if (ev.type === 'task_status') {
        setTasks(prev => prev.map(tk =>
          tk.id === ev.task_id ? { ...tk, ...ev.updates } : tk
        ));
      } else if (ev.type === 'task_created' && ev.task && ev.task.id) {
        setTasks(prev => prev.some(tk => tk.id === ev.task.id) ? prev : [ev.task, ...prev]);
      }
    });
  }, [subscribeEvents, tasksAvailable]);

  const filtered = useMemoT(() => {
    return tasks.filter(tk => {
      if (filter !== 'all' && tk.status !== filter) return false;
      if (q && !(
        tk.title.toLowerCase().includes(q.toLowerCase())
        || tk.id.includes(q)
        || (tk.target || '').toLowerCase().includes(q.toLowerCase())
      )) return false;
      return true;
    });
  }, [filter, q, tasks]);

  const active = tasks.find(tk => tk.id === activeId);
  const filterKeys = ['all', 'running', 'queued', 'success', 'failed', 'stopped'];
  const tasksEmptyState = tasksAvailable ? t('tasks.noMatch') : (tasksUnavailableReason || t('c.unavailable'));
  const detailEmptyState = tasksAvailable ? t('tasks.noSelection') : (tasksUnavailableReason || t('c.unavailable'));

  function handleCreated(task) {
    setTasks(prev => {
      const existing = prev.find(tk => tk.id === task.id);
      if (existing) {
        return prev.map(tk => tk.id === task.id ? { ...tk, ...task } : tk);
      }
      return [task, ...prev];
    });
    setActive(task.id);
  }

  return (
    <div className="page" style={{ height: '100%', minHeight: 0 }}>
      <div className="page-h">
        <div>
          <div className="t">{t('tasks.t')}</div>
          <div className="sub">{taskSummaryLabel(tasks)}</div>
        </div>
        <div className="row">
          <button
            className="btn ghost"
            onClick={() => downloadJson(`tasks_${new Date().toISOString().replace(/[:.]/g, '-')}.json`, filtered)}
          >
            <span className="muted">{t('c.export')}</span>
          </button>
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
              <TaskItem
                key={tk.id}
                task={tk}
                active={tk.id === activeId}
                onClick={() => {
                  setActive(tk.id);
                  if (onNav) onNav(`tasks/${tk.id}`);
                }}
              />
            ))}
            {filtered.length === 0 && <Empty>{tasksEmptyState}</Empty>}
          </div>
        </Panel>

        {active ? (
          <TaskDetail
            task={active}
            key={active.id}
            onNav={onNav}
            taskViewMode={taskViewMode}
          />
        ) : (
          <Panel className="task-detail">
            <Empty>{detailEmptyState}</Empty>
          </Panel>
        )}
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
        <ModeBadge mode={tk.mode} />
        <SubtypeBadge value={tk.modeSubtype} />
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

function detailMessagesLabel(mode) {
  if (mode === 'session_snapshot') return 'observed session transcript';
  if (mode === 'metrics_observed') return 'metrics-derived summary';
  if (mode === 'synthetic_fallback') return 'synthetic fallback transcript';
  return mode || 'unknown';
}

function detailConfidenceLabel(level) {
  if (level === 'high') return 'high';
  if (level === 'medium') return 'medium';
  if (level === 'low') return 'low';
  if (level === 'very_low') return 'very low';
  return level || 'none';
}

function detailBlockedReasonLabel(reason) {
  if (reason === 'expected_session_missing') return 'expected session file missing';
  return reason || '—';
}

function detailKnowledgeLabel(mode) {
  if (mode === 'session_snapshot') return 'snapshot-backed';
  if (mode === 'metrics_observed') return 'metrics-observed';
  if (mode === 'live_event') return 'live event';
  if (mode === 'unobserved') return 'unobserved';
  return mode || 'unknown';
}

function knowledgeResultLabel(kind) {
  if (kind === 'matched') return 'matched';
  if (kind === 'no_match') return 'no match';
  if (kind === 'observed_only') return 'observed only';
  if (kind === 'failed') return 'failed';
  return kind || 'observed';
}

function knowledgeTone(kind) {
  if (kind === 'matched') return 'green';
  if (kind === 'no_match') return 'amber';
  if (kind === 'observed_only') return 'cyan';
  if (kind === 'failed') return 'red';
  return 'dim';
}

function TaskDetailSourceBanner({ source }) {
  if (!source) return null;
  const mode = source.messages || 'unknown';
  const tone = mode === 'session_snapshot' ? 'green' : mode === 'metrics_observed' ? 'amber' : 'red';
  const summary = mode === 'session_snapshot'
    ? 'conversation is backed by an observed session snapshot'
    : mode === 'metrics_observed'
      ? 'conversation is reconstructed from metrics because no trusted session snapshot was selected'
      : 'conversation is synthetic fallback only';

  return (
    <div className="side-card" style={{ margin: '0 0 10px 0' }}>
      <div className="h">◎ live detail <span className={`${tone} right`} style={{ letterSpacing: 0 }}>{detailMessagesLabel(mode)}</span></div>
      <div style={{ fontSize: 11.5, color: 'var(--fg-1)', lineHeight: 1.5, marginBottom: 10 }}>{summary}</div>
      <div className="kv-list">
        <div className="kv-row"><span className="k">confidence</span><span className="v">{detailConfidenceLabel(source.messagesConfidence)}</span></div>
        <div className="kv-row"><span className="k">session match</span><span className="v">{source.sessionMatchedBy || '—'}</span></div>
        <div className="kv-row"><span className="k">session</span><span className="v mono" style={{ fontSize: 10.5 }}>{source.session || '—'}</span></div>
        <div className="kv-row"><span className="k">expected session</span><span className="v mono" style={{ fontSize: 10.5 }}>{source.sessionExpectedId || source.metricsSessionId || source.taskSessionId || '—'}</span></div>
        <div className="kv-row"><span className="k">metrics</span><span className="v mono" style={{ fontSize: 10.5 }}>{source.metrics || '—'}</span></div>
        <div className="kv-row"><span className="k">plan</span><span className="v">{source.plan || '—'}</span></div>
        <div className="kv-row"><span className="k">notes</span><span className="v">{source.notesMode || '—'}</span></div>
        {source.sessionBlockedReason && <div className="kv-row"><span className="k">blocked</span><span className="v red">{detailBlockedReasonLabel(source.sessionBlockedReason)}</span></div>}
        {source.sessionMismatch && (
          <div className="kv-row">
            <span className="k">session mismatch</span>
            <span className="v mono" style={{ fontSize: 10.5 }}>{source.sessionMismatch.taskSessionId} → {source.sessionMismatch.metricsSessionId}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------
// Task detail
// ----------------------------------------------------------------
function TaskDetail({ task, onNav, taskViewMode }) {
  const [detailTask, setDetailTask] = useStateT(task);
  const isActive = detailTask.status === 'running';
  const [connection, setConnection] = useStateT(() => currentConnectionState());
  const getTask = window.API?.getTask;
  const taskDetailAvailable = ['connected', 'degraded'].includes(connection.status)
    && typeof getTask === 'function';
  const capabilityMap = normalizeTaskCapabilities(detailTask.capabilities);
  const hintSupported = !!capabilityMap.hint;
  const stopSupported = !!capabilityMap.stop;
  const continueSupported = !!capabilityMap.continue;
  const retrySupported = !!capabilityMap.retry;
  const attachmentsSupported = !!capabilityMap.attachments;
  const isActionLive = ['connected', 'degraded'].includes(connection.status);
  const hintAvailable = hintSupported
    && isActionLive
    && typeof window.API?.hintTask === 'function';
  const continueAvailable = continueSupported
    && isActionLive
    && typeof window.API?.continueTask === 'function';
  const retryAvailable = retrySupported
    && isActionLive
    && typeof window.API?.retryTask === 'function';
  const attachmentsUploadAvailable = attachmentsSupported
    && isActionLive
    && typeof window.API?.uploadAttachment === 'function';
  const attachmentsUnavailableReason = !attachmentsSupported
    ? t('c.unavailable')
    : !isActionLive
      ? t('c.notConnected')
      : typeof window.API?.uploadAttachment !== 'function'
        ? t('c.notWired')
        : '';
  const initialMessages = resolveTaskMessages(detailTask);

  const [messages, setMessages] = useStateT(initialMessages);
  const [hintMode, setHintMode] = useStateT(() => !continueAvailable);
  const [draft, setDraft] = useStateT('');
  const [obsFresh, setObsFresh] = useStateT(null);
  const [attachments, setAttachments] = useStateT(detailTask.attachments || []);
  const [attachmentsUploadBusy, setAttachmentsUploadBusy] = useStateT(false);
  const [attachmentsUploadError, setAttachmentsUploadError] = useStateT('');
  const attachmentInputRef = useRefT(null);
  const msgEnd = useRefT(null);

  useEffectT(() => {
    setDetailTask(prev => mergeTaskDetail(prev, task));
    setAttachments(task.attachments || []);
  }, [task]);

  useEffectT(() => {
    const handler = (e) => {
      setConnection(
        e.detail?.connection
        || currentConnectionState()
      );
    };
    window.addEventListener('fh:connection', handler);
    return () => window.removeEventListener('fh:connection', handler);
  }, []);

  useEffectT(() => {
    if (!taskDetailAvailable || typeof getTask !== 'function') return;
    getTask(task.id).then(data => {
      if (data && data.id) setDetailTask(prev => mergeTaskDetail(prev, data));
    });
  }, [getTask, task.id, taskDetailAvailable]);

  useEffectT(() => {
    if (!continueAvailable && !hintMode) setHintMode(true);
  }, [continueAvailable, hintMode]);

  useEffectT(() => {
    setMessages(resolveTaskMessages(detailTask));
  }, [
    detailTask.id,
    detailTask.messages,
    detailTask.finishedAt,
    detailTask.finalFlag,
    detailTask.stopReason,
  ]);

  useEffectT(() => {
    window.dispatchEvent(new CustomEvent('fh:route-label', {
      detail: { label: detailTask.id || task.id || 'task' }
    }));
  }, [detailTask.id, task.id]);

  async function refreshAttachments() {
    if (!attachmentsSupported || !window.API || !window.API.getAttachments) return;
    const attachmentsResult = await window.API.getAttachments(detailTask.id);
    if (attachmentsResult && Array.isArray(attachmentsResult.files)) setAttachments(attachmentsResult.files);
  }

  async function handleAttachmentFiles(files) {
    if (!attachmentsUploadAvailable || !files.length) return;
    setAttachmentsUploadBusy(true);
    setAttachmentsUploadError('');
    const uploadResult = await window.API.uploadAttachment(detailTask.id, files);
    if (!uploadResult || !Array.isArray(uploadResult.files)) {
      setAttachmentsUploadError('upload failed');
      setAttachmentsUploadBusy(false);
      return;
    }
    await refreshAttachments();
    setAttachmentsUploadBusy(false);
  }

  // Load attachments from server when task is selected (live mode)
  useEffectT(() => {
    refreshAttachments();
  }, [detailTask.id, attachmentsSupported]);

  const livePlan = Array.isArray(detailTask.plan) ? detailTask.plan : [];
  const liveNotes = Array.isArray(detailTask.notes) ? detailTask.notes : [];
  const liveKnowledgeHits = Array.isArray(detailTask.knowledgeHits) ? detailTask.knowledgeHits : [];
  const [obs, setObs] = useStateT([]);

  useEffectT(() => {
    setObs([]);
    setObsFresh(null);
  }, [detailTask.id]);

  useEffectT(() => {
    function pushObs(text, at) {
      const id = `live_obs_${at}_${Math.random().toString(36).slice(2, 6)}`;
      const ent = { id, t: at, text };
      setObs(o => [...o, ent].slice(-8));
      setObsFresh(id);
      setTimeout(() => setObsFresh(current => current === id ? null : current), 900);
    }

    const handler = (event) => {
      const ev = event?.detail || {};
      if (ev.task_id !== detailTask.id) return;
      const at = ev.t || ev.timestamp || new Date().toISOString();

      if (ev.type === 'task_status') {
        const updates = ev.updates || {};
        setDetailTask(prev => ({ ...(prev || {}), ...updates }));
        if (updates.status && updates.status !== 'running' && (updates.finishedAt || updates.finalFlag || updates.stopReason)) {
          const finishId = `live_finish_${updates.status}_${updates.finishedAt || at}`;
          setMessages(prev => prev.some(m => m.id === finishId) ? prev : [...prev, {
            id: finishId,
            role: 'system',
            t: updates.finishedAt || at,
            content: updates.finalFlag
              ? `flag verified ✓ ${updates.finalFlag}`
              : `task ended · stop_reason=${updates.stopReason || updates.status}`,
          }]);
          pushObs(`status → ${updates.status}`, updates.finishedAt || at);
        }
        return;
      }

      if (ev.type === 'tool_call') {
        const msgId = `live_tool_${at}_${ev.tool || 'tool'}`;
        const title = ev.tool || 'tool';
        setMessages(prev => prev.some(m => m.id === msgId) ? prev : [...prev, {
          id: msgId,
          role: 'system',
          t: at,
          content: `live tool call · ${title}`,
          tools: title ? [title] : undefined,
        }]);
        pushObs(`${title} · ${ev.summary || 'started'}`, at);
        return;
      }

      if (ev.type === 'tool.finished') {
        const title = ev.tool || 'tool';
        const msgId = `live_tool_finished_${title}_${at}`;
        const text = ev.success === false
          ? `tool finished · ${title} · failed`
          : `tool finished · ${title}`;
        setMessages(prev => prev.some(m => m.id === msgId) ? prev : [...prev, {
          id: msgId,
          role: 'system',
          t: at,
          content: text,
          tools: title ? [title] : undefined,
        }]);
        pushObs(`${title} finished · ${ev.summary || (ev.success === false ? 'failed' : 'done')}`, at);
        return;
      }

      if (ev.type === 'knowledge.retrieved') {
        const hitId = `live_knowledge_${ev.source || 'knowledge'}_${at}`;
        const output = ev.output || '';
        const lower = String(output || ev.summary || '').toLowerCase();
        const hit = {
          id: hitId,
          source: ev.source || 'knowledge',
          title: ev.summary || 'knowledge retrieved',
          score: null,
          output,
          preview: ev.summary || output.split('\n')[0] || 'knowledge retrieved',
          query: null,
          resultKind: lower.includes('no relevant knowledge found') || lower.includes('no relevant entries were returned') ? 'no_match' : 'matched',
          mode: 'live_event',
          t: at,
        };
        setDetailTask(prev => {
          const prevHits = Array.isArray(prev.knowledgeHits) ? prev.knowledgeHits : [];
          if (prevHits.some(item => item.id === hitId)) return prev;
          return { ...prev, knowledgeHits: [...prevHits, hit] };
        });
        pushObs(`knowledge retrieved · ${ev.summary || ev.source || 'knowledge'}`, at);
        return;
      }

      if (ev.type === 'note.created') {
        const noteId = `live_note_${at}`;
        const note = {
          id: noteId,
          key: ev.summary || 'note created',
          value: (ev.output || '').split('\n')[0] || 'saved',
          t: at,
        };
        setDetailTask(prev => {
          const prevNotes = Array.isArray(prev.notes) ? prev.notes : [];
          if (prevNotes.some(item => item.id === noteId)) return prev;
          return { ...prev, notes: [...prevNotes, note] };
        });
        pushObs(`note created · ${ev.summary || 'saved'}`, at);
        return;
      }

      if (ev.type === 'hint') {
        const hintId = `live_hint_${at}`;
        const text = ev.text || 'hint accepted';
        setMessages(prev => prev.some(m => m.id === hintId) ? prev : [...prev, {
          id: hintId,
          role: 'system',
          t: at,
          content: `hint accepted · ${text}`,
        }]);
        pushObs(`hint accepted · ${text}`, at);
      }
    };

    window.addEventListener('fh:event', handler);
    return () => window.removeEventListener('fh:event', handler);
  }, [detailTask.id]);

  useEffectT(() => {
    msgEnd.current?.scrollTo({ top: msgEnd.current.scrollHeight, behavior: 'smooth' });
  }, [messages.length]);

  function appendSystemMessage(content) {
    setMessages(prev => [...prev, {
      id: `m_system_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      role: 'system',
      t: new Date().toISOString(),
      content,
    }]);
  }

  const send = async () => {
    if (!draft.trim()) return;
    if (hintMode && !hintAvailable) return;
    if (!hintMode && !continueAvailable) return;

    if (!hintMode) {
      const continueResult = await window.API.continueTask(detailTask.id);
      if (!continueResult?.ok) {
        appendSystemMessage('continue request failed');
        return;
      }
      setDraft('');
      appendSystemMessage('continue request accepted');
      return;
    }

    const text = draft.trim();
    const result = await window.API.hintTask(detailTask.id, text);
    if (!result?.ok) {
      appendSystemMessage('hint request failed');
      return;
    }
    setDraft('');
  };

  async function handleStop() {
    const canStopTask = stopSupported && (
      ['connected', 'degraded'].includes(connection.status)
      && typeof window.API?.stopTask === 'function'
    );
    if (!canStopTask) return;
    const result = await window.API.stopTask(detailTask.id);
    if (!result?.ok) appendSystemMessage('stop request failed');
  }

  async function handleRetry() {
    if (!retryAvailable) return;
    const retryResult = await window.API.retryTask(detailTask.id);
    if (retryResult?.id && onNav) onNav(`tasks/${retryResult.id}`);
  }

  const continueUnavailableReason = !continueSupported
    ? t('td.continueUnavailable')
    : !isActionLive
      ? t('c.notConnected')
      : typeof window.API?.continueTask !== 'function'
        ? t('c.notWired')
      : '';
  const retryUnavailableReason = !retrySupported
    ? t('td.retryUnavailable')
    : !isActionLive
      ? t('c.notConnected')
      : typeof window.API?.retryTask !== 'function'
        ? t('c.notWired')
        : '';
  const hintUnavailableReason = !hintSupported
    ? t('td.hintUnavailable')
    : !isActionLive
      ? t('c.notConnected')
      : typeof window.API?.hintTask !== 'function'
        ? t('c.notWired')
        : '';

  return (
    <div className="task-detail">
      <div className="task-detail-head">
        <div className="left">
          <div className="identity-row">
            <StatusBadge status={detailTask.status} size="lg" />
            <ModeBadge mode={detailTask.mode} />
            <SubtypeBadge value={detailTask.modeSubtype} />
            <span className="dim mono">{detailTask.id}</span>
            {detailTask.currentRunId && (
              <span className="dim mono">· {t('td.run')} <span className="bright">{detailTask.currentRunId}</span></span>
            )}
            <span className="chip ghost">{taskViewMode === 'analysis' ? t('td.modeAnalysis') : t('td.modeConversation')}</span>
          </div>
          <div className="title">{detailTask.title}</div>
          <div className="descriptor-row">
            <span>{t('c.target')} <b>{detailTask.target}</b></span>
            <span>{t('c.goal')} <b>{detailTask.goal || '—'}</b></span>
          </div>
          <div className="runtime-row">
            <span>{t('c.started')} <b>{detailTask.startedAt ? fmt.since(detailTask.startedAt) : '—'}</b></span>
            <span>{t('c.tokens')} <b>{((detailTask.tokensUsed||0)/1000).toFixed(1)}k</b></span>
            <span>{t('c.tools')} <b>{detailTask.toolCalls || 0}</b></span>
            {detailTask.finalFlag && <span>{t('c.flag')} <b className="green">{detailTask.finalFlag}</b></span>}
            {detailTask.stopReason && <span>{t('c.stopReason')} <b className="red">{detailTask.stopReason}</b></span>}
          </div>
        </div>
        <div className="actions">
          <button
            className="btn ghost"
            onClick={() => downloadJson(`${detailTask.id}.json`, detailTask)}
          >
            ⤓ {t('c.export')}
          </button>
          <button className="btn ghost" onClick={() => detailTask.currentRunId && onNav && onNav(`traces/${detailTask.currentRunId}`)}>⧉ {t('c.trace')}</button>
          {!isActive && <button className="btn" onClick={handleRetry} disabled={!retryAvailable} title={!retryAvailable ? retryUnavailableReason : ''}>↻ {t('c.retry')}</button>}
          {isActive && stopSupported && <button className="btn danger" onClick={handleStop}>■ {t('c.stop')}</button>}
        </div>
      </div>

      <div className={`task-detail-body mode-${taskViewMode || 'conversation'}`}>
        {/* convo */}
        <div className="task-convo">
          {detailTask.detailSource && <TaskDetailSourceBanner source={detailTask.detailSource} />}
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
              <span
                className={`tab-mini ${!hintMode ? 'on' : ''} ${!continueAvailable ? 'disabled' : ''}`}
                style={!hintMode ? { color: 'var(--accent)', background: 'rgba(107,230,117,0.08)', borderColor: 'var(--accent-dim)' } : {}}
                onClick={() => continueAvailable && setHintMode(false)}
                title={!continueAvailable ? continueUnavailableReason : ''}
              >
                {t('td.continue')}
              </span>
              <span className={`tab-mini ${hintMode ? 'on' : ''} ${!hintAvailable ? 'disabled' : ''}`} onClick={() => hintAvailable && setHintMode(true)} title={!hintAvailable ? hintUnavailableReason : ''}>
                {t('td.injectHint')}
              </span>
              <span style={{ marginLeft: 'auto', color: 'var(--fg-3)', fontSize: 10.5, alignSelf: 'center' }}>
                {hintMode ? (hintAvailable ? t('td.hintDesc') : hintUnavailableReason) : (continueAvailable ? t('td.continueDesc') : continueUnavailableReason)}
              </span>
            </div>
            <div className="row">
              <textarea
                className="input"
                placeholder={hintMode ? t('td.composer.hint') : (continueAvailable ? t('td.composer.continue') : continueUnavailableReason)}
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }}}
                rows={2}
                disabled={hintMode ? !hintAvailable : !continueAvailable}
              />
              <button
                className={`btn ${hintMode ? '' : 'primary'}`}
                onClick={send}
                disabled={hintMode ? !hintAvailable : !continueAvailable}
                title={hintMode ? (!hintAvailable ? hintUnavailableReason : '') : (!continueAvailable ? continueUnavailableReason : '')}
              >
                {hintMode ? t('td.inject') : t('td.sendBtn')} <span className="kbd">⌘↵</span>
              </button>
            </div>
          </div>
        </div>

        {/* side panel */}
        <div className="side-panel">
          <LiveSidePanel
            task={{ ...detailTask, attachments }}
            plan={livePlan}
            notes={liveNotes}
            knowledgeHits={liveKnowledgeHits}
            observations={obs}
            freshObservationId={obsFresh}
            attachmentsAvailable={attachmentsSupported}
            attachmentsUploadAvailable={attachmentsUploadAvailable}
            attachmentsUploadBusy={attachmentsUploadBusy}
            attachmentsUploadError={attachmentsUploadError}
            onUploadRequest={() => attachmentInputRef.current?.click()}
            onUploadFiles={handleAttachmentFiles}
            attachmentInputRef={attachmentInputRef}
            attachmentsUnavailableReason={attachmentsUnavailableReason}
          />
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
          {t(whoKey)} <span className="dim" style={{ marginLeft: 8, letterSpacing: 0 }}>{m.t ? fmt.hh(m.t) : '—'}</span>
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
  const doneCount = plan.filter(p => p.state === 'done').length;
  return (
    <div className="side-card">
      <div className="h"><span className="accent">▸ {t('side.plan')}</span><span className="dim right">{doneCount}/{plan.length}</span></div>
      <div className="plan-list">
        {plan.map((p, i) => {
          const title = p.label || p.description || `step ${i + 1}`;
          return (
            <div key={p.id || i} className={`plan-step ${p.state}`}>
              <span className="marker">{p.state === 'done' ? '✓' : i + 1}</span>
              <span title={title}>{title}</span>
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
        {obs.length === 0 && <Empty>{t('td.obs.empty')}</Empty>}
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
  const items = Array.isArray(hits) ? hits : [];
  const sourceCounts = items.reduce((acc, hit) => {
    const key = hit?.source || 'knowledge';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const modeCounts = items.reduce((acc, hit) => {
    const key = hit?.mode || 'unknown';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const resultCounts = items.reduce((acc, hit) => {
    const key = hit?.resultKind || 'observed';
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const queryCount = items.filter(hit => hit?.query).length;
  const fidelity = modeCounts.session_snapshot > 0
    ? 'snapshot-backed'
    : modeCounts.metrics_observed > 0
      ? 'metrics-observed'
      : modeCounts.live_event > 0
        ? 'live events'
        : 'unobserved';
  const emptyHint = modeCounts.metrics_observed > 0
    ? t('td.knowledge.observedOnly')
    : t('td.knowledge.empty');

  return (
    <div className="side-card">
      <div className="h">◉ {t('side.knowledge')} <span className="dim right">{items.length}</span></div>
      <div className="kv-list" style={{ marginBottom: 8 }}>
        <div className="kv-row"><span className="k">fidelity</span><span className="v">{fidelity}</span></div>
        <div className="kv-row"><span className="k">queries</span><span className="v">{queryCount}</span></div>
        <div className="kv-row"><span className="k">matched</span><span className="v green">{resultCounts.matched || 0}</span></div>
        <div className="kv-row"><span className="k">no match</span><span className="v amber">{resultCounts.no_match || 0}</span></div>
        {(resultCounts.observed_only || 0) > 0 && (
          <div className="kv-row"><span className="k">observed only</span><span className="v cyan">{resultCounts.observed_only || 0}</span></div>
        )}
      </div>
      {Object.keys(sourceCounts).length > 0 && (
        <div className="row gap-6" style={{ flexWrap: 'wrap', marginBottom: 8 }}>
          {Object.entries(sourceCounts).map(([name, count]) => (
            <span key={name} className="chip ghost">{name} × {count}</span>
          ))}
        </div>
      )}
      <div className="col gap-6">
        {items.length === 0 && <Empty>{emptyHint}</Empty>}
        {items.map(h => (
          <div key={h.id} style={{ fontSize: 11.5, lineHeight: 1.45, padding: '6px 0', borderTop: '1px solid var(--line-1)' }}>
            <div className="row gap-6" style={{ alignItems: 'center' }}>
              <span className="blue" style={{ fontSize: 10 }}>{h.source || 'knowledge'}</span>
              <span className={`chip ghost ${knowledgeTone(h.resultKind)}`.trim()} style={{ fontSize: 9.5 }}>{knowledgeResultLabel(h.resultKind)}</span>
              <span className="dim mono" style={{ fontSize: 9.5, marginLeft: 'auto' }}>
                {h.score != null ? Number(h.score).toFixed(2) : detailKnowledgeLabel(h.mode)}
              </span>
            </div>
            <div className="bright" style={{ marginTop: 4 }}>{h.title || 'knowledge retrieved'}</div>
            {h.query && <div className="muted" style={{ marginTop: 4, fontSize: 10.5 }}>query · {h.query}</div>}
            {h.preview && <div className="dim" style={{ marginTop: 4, fontSize: 10.5 }}>{h.preview}</div>}
            <div className="row gap-8" style={{ marginTop: 4, fontSize: 10 }}>
              {h.chunkId && <span className="mono muted">{h.chunkId}</span>}
              {h.t && <span className="mono dim">{fmt.hh(h.t).slice(0, 8)}</span>}
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
        {notes.length === 0 && <Empty>{t('td.notes.empty')}</Empty>}
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

function TaskStatusCard({ task }) {
  const isFlagged = task.finalFlag;
  return (
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
  );
}

function TaskAttachmentsCard({
  attachments,
  attachmentsAvailable,
  unavailableReason,
  attachmentsUploadAvailable = false,
  attachmentsUploadBusy = false,
  attachmentsUploadError = '',
  onUploadRequest,
  onUploadFiles,
  attachmentInputRef,
}) {
  const items = Array.isArray(attachments) ? attachments : [];
  return (
    <div className="side-card">
      <div className="h">
        ◫ {t('side.attachments')} <span className="dim right">{items.length}</span>
        <button
          className="btn sm ghost"
          style={{ marginLeft: 'auto' }}
          disabled={!attachmentsUploadAvailable || attachmentsUploadBusy}
          title={!attachmentsUploadAvailable ? unavailableReason : ''}
          onClick={() => onUploadRequest && onUploadRequest()}
        >{attachmentsUploadBusy ? '…' : '+'}</button>
        <input
          ref={attachmentInputRef}
          type="file"
          multiple
          style={{ display: 'none' }}
          onChange={async e => {
            const files = Array.from(e.target.files || []);
            await onUploadFiles(files);
            e.target.value = '';
          }}
        />
      </div>
      {items.length === 0 ? (
        <Empty>{attachmentsUploadError || unavailableReason || t('tasks.noMatch')}</Empty>
      ) : (
      <div className="col gap-4">
        {items.map((a, i) => (
          <div key={i} className="row gap-8 attach-row">
            <span style={{ fontSize: 13 }}>{window.fileIcon ? window.fileIcon(a.name) : '◫'}</span>
            <span className="bright ellipsis flex1" style={{ fontSize: 11.5 }}>{a.name}</span>
            <span className="dim" style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}>
              {a.size < 1024 ? a.size + 'B'
                : a.size < 1048576 ? (a.size / 1024).toFixed(1) + 'KB'
                : (a.size / 1048576).toFixed(2) + 'MB'}
            </span>
            {a.path && (
              <span className="dim" title={a.path} style={{ fontSize: 9 }}>✓</span>
            )}
          </div>
        ))}
      </div>
      )}
      {attachmentsUploadError && items.length > 0 && (
        <div className="red" style={{ marginTop: 8, fontSize: 11 }}>{attachmentsUploadError}</div>
      )}
    </div>
  );
}

function TaskSummaryCard({ task }) {
  const isFlagged = task.finalFlag;
  let summaryKey;
  if (task.status === 'running') summaryKey = 'side.summary.running';
  else if (task.status === 'success') summaryKey = 'side.summary.success';
  else if (task.status === 'failed') summaryKey = 'side.summary.failed';
  else if (task.status === 'queued') summaryKey = 'side.summary.queued';
  else summaryKey = 'side.summary.stopped';

  return (
    <div className="side-card">
      <div className="h">◈ {t('side.summary')}</div>
      <div style={{ fontSize: 11.5, color: 'var(--fg-1)', lineHeight: 1.55 }}>
        {t(summaryKey, task.stopReason || '')}
      </div>
      {isFlagged && <div className="green" style={{ marginTop: 8, fontSize: 11.5 }}>{task.finalFlag}</div>}
    </div>
  );
}

function SyntheticSidePanel({ task, attachmentsAvailable, attachmentsUnavailableReason, ...attachmentProps }) {
  return (
    <>
      <TaskStatusCard task={task} />
      <TaskAttachmentsCard attachments={task.attachments || []} attachmentsAvailable={attachmentsAvailable} unavailableReason={attachmentsUnavailableReason} {...attachmentProps} />
      <TaskSummaryCard task={task} />
    </>
  );
}

function LiveSidePanel({ task, plan, notes, knowledgeHits, observations, freshObservationId, attachmentsAvailable, attachmentsUnavailableReason, ...attachmentProps }) {
  const showFallbackSummary = !plan.length && !notes.length && !knowledgeHits.length && !observations.length;
  return (
    <>
      {showFallbackSummary ? (
        <SyntheticSidePanel task={task} attachmentsAvailable={attachmentsAvailable} attachmentsUnavailableReason={attachmentsUnavailableReason} {...attachmentProps} />
      ) : (
        <>
          <TaskStatusCard task={task} />
          <TaskAttachmentsCard attachments={task.attachments || []} attachmentsAvailable={attachmentsAvailable} unavailableReason={attachmentsUnavailableReason} {...attachmentProps} />
        </>
      )}
      <div className="side-card">
        <div className="h">◎ observed sources</div>
        <div className="kv-list">
          <div className="kv-row"><span className="k">messages</span><span className="v">{detailMessagesLabel(task.detailSource?.messages)}</span></div>
          <div className="kv-row"><span className="k">confidence</span><span className="v">{detailConfidenceLabel(task.detailSource?.messagesConfidence)}</span></div>
          <div className="kv-row"><span className="k">session</span><span className="v mono" style={{ fontSize: 10.5 }}>{task.detailSource?.session || '—'}</span></div>
        <div className="kv-row"><span className="k">expected</span><span className="v mono" style={{ fontSize: 10.5 }}>{task.detailSource?.sessionExpectedId || task.detailSource?.metricsSessionId || task.detailSource?.taskSessionId || '—'}</span></div>
        <div className="kv-row"><span className="k">metrics</span><span className="v mono" style={{ fontSize: 10.5 }}>{task.detailSource?.metrics || '—'}</span></div>
        <div className="kv-row"><span className="k">notes</span><span className="v mono" style={{ fontSize: 10.5 }}>{(task.detailSource?.notes || []).join(', ') || '—'}</span></div>
        <div className="kv-row"><span className="k">knowledge</span><span className="v">{detailKnowledgeLabel(task.detailSource?.knowledge)}</span></div>
        <div className="kv-row"><span className="k">knowledge confidence</span><span className="v">{detailConfidenceLabel(task.detailSource?.knowledgeConfidence)}</span></div>
        {task.detailSource?.sessionBlockedReason && <div className="kv-row"><span className="k">blocked</span><span className="v red">{detailBlockedReasonLabel(task.detailSource?.sessionBlockedReason)}</span></div>}
      </div>
      </div>
      <ObsCard obs={observations || []} fresh={freshObservationId} />
      <PlanCardLive plan={plan} />
      <KnowledgeCard hits={knowledgeHits} />
      <NotesCard notes={notes} />
      {!showFallbackSummary && <TaskSummaryCard task={task} />}
    </>
  );
}

function PlanCardLive({ plan }) {
  if (!plan.length) {
    return (
      <div className="side-card">
        <div className="h"><span className="accent">▸ {t('side.plan')}</span><span className="dim right">0</span></div>
        <Empty>{t('td.plan.empty')}</Empty>
      </div>
    );
  }
  return <PlanCard plan={plan} />;
}

function resolveTaskMessages(tk) {
  if (Array.isArray(tk.messages) && tk.messages.length) return tk.messages;
  return buildSyntheticMessages(tk);
}

function preferTaskDetailField(nextValue, prevValue) {
  if (Array.isArray(nextValue)) return nextValue.length ? nextValue : (Array.isArray(prevValue) ? prevValue : nextValue);
  if (nextValue && typeof nextValue === 'object') return Object.keys(nextValue).length ? nextValue : (prevValue || nextValue);
  return nextValue == null ? prevValue : nextValue;
}

function mergeTaskDetail(prev, next) {
  if (!prev || prev.id !== next.id) return next;
  return {
    ...prev,
    ...next,
    messages: preferTaskDetailField(next.messages, prev.messages),
    hints: preferTaskDetailField(next.hints, prev.hints),
    capabilities: preferTaskDetailField(next.capabilities, prev.capabilities),
    detailSource: preferTaskDetailField(next.detailSource, prev.detailSource),
    plan: preferTaskDetailField(next.plan, prev.plan),
    notes: preferTaskDetailField(next.notes, prev.notes),
    knowledgeHits: preferTaskDetailField(next.knowledgeHits, prev.knowledgeHits),
  };
}

function normalizeTaskCapabilities(capabilities) {
  return {
    hint: capabilities?.hint !== false,
    stop: Boolean(capabilities?.stop),
    continue: Boolean(capabilities?.continue),
    retry: Boolean(capabilities?.retry),
    attachments: capabilities?.attachments !== false,
  };
}

function buildSyntheticMessages(tk) {
  if (tk.status === 'queued') {
    return [{ id: 'sm1', role: 'user', t: new Date().toISOString(), content: `${tk.goal || ''}\n${t('c.target')}: ${tk.target}` }];
  }
  const messages = [
    { id: 'sm1', role: 'user',   t: tk.startedAt || new Date().toISOString(), content: `${tk.goal || ''}\n${t('c.target')}: ${tk.target}` },
    { id: 'sm2', role: 'agent',  t: tk.startedAt || new Date().toISOString(), content: window.LANG === 'zh' ? '收到，开始 recon。' : 'Acknowledged. Starting recon.' },
  ];
  if (tk.status === 'running') return messages;
  return [
    ...messages,
    { id: 'sm3', role: 'system', t: tk.finishedAt || tk.startedAt || new Date().toISOString(),
      content: tk.finalFlag ? `flag verified ✓  ${tk.finalFlag}` :
        tk.stopReason ? `task ended · stop_reason=${tk.stopReason}` : 'task ended' },
  ];
}

window.TasksPage = TasksPage;
