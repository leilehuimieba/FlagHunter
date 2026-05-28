// ============================================================
// FlagHunter API layer — probes backend, manages unified
// connection state, and exposes REST + SSE helpers
// ============================================================

(function () {
  window.FH_NO_MOCK = window.FH_NO_MOCK || false;
  const _listeners = [];
  const _liveState = {
    probeFailures: 0,
    lastSseAt: 0,
  };
  const PROBE_FAILURE_THRESHOLD = 3;
  const SSE_FRESH_MS = 45000;

  window.FH_CONNECTION = window.FH_CONNECTION || {
    status: 'connecting',
    isLive: false,
    via: 'boot',
    probeFailures: 0,
    lastSseAt: 0,
  };
  window.IS_LIVE = Boolean(window.FH_CONNECTION.isLive);

  function _isSseFresh() {
    return _liveState.lastSseAt > 0 && (Date.now() - _liveState.lastSseAt) < SSE_FRESH_MS;
  }

  function getConnectionState() {
    return {
      ...window.FH_CONNECTION,
      probeFailures: _liveState.probeFailures,
      lastSseAt: _liveState.lastSseAt,
    };
  }

  function _fire(type, detail) {
    const connection = getConnectionState();
    window.dispatchEvent(new CustomEvent('fh:connection', { detail: { type, connection, ...detail } }));
    _listeners.forEach(fn => fn({ type, detail: { connection, ...detail } }));
  }

  function _syncConnection(partial) {
    const previous = getConnectionState();
    window.FH_CONNECTION = {
      ...previous,
      ...partial,
      probeFailures: _liveState.probeFailures,
      lastSseAt: _liveState.lastSseAt,
    };
    window.IS_LIVE = Boolean(window.FH_CONNECTION.isLive);

    const next = getConnectionState();
    if (
      previous.status !== next.status
      || previous.isLive !== next.isLive
    ) {
      _fire(next.status, { via: next.via, status: next.status });
    }
    return next;
  }

  function _markSseAlive() {
    _liveState.lastSseAt = Date.now();
    const nextStatus = _liveState.probeFailures > 0 ? 'degraded' : 'connected';
    _syncConnection({
      status: nextStatus,
      isLive: true,
      via: 'sse',
    });
  }

  async function probe() {
    try {
      const r = await fetch('/api/status', { signal: AbortSignal.timeout(2500) });
      if (!r.ok) throw new Error('not ok');
      const data = await r.json();
      _liveState.probeFailures = 0;
      _syncConnection({
        status: 'connected',
        isLive: true,
        via: 'probe',
      });
      return data;
    } catch {
      _liveState.probeFailures += 1;
      if (_isSseFresh()) {
        _syncConnection({
          status: 'degraded',
          isLive: true,
          via: 'probe_degraded',
        });
        return false;
      }
      if (_liveState.probeFailures < PROBE_FAILURE_THRESHOLD) {
        _syncConnection({
          status: 'reconnecting',
          isLive: Boolean(window.FH_CONNECTION?.isLive),
          via: 'probe_retry',
        });
        return false;
      }
      _syncConnection({
        status: 'disconnected',
        isLive: false,
        via: 'probe_failures',
      });
      return false;
    }
  }

  probe();
  setInterval(probe, 8000);

  async function apiFetch(path, opts) {
    try {
      const r = await fetch(path, opts);
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch {
      return null;
    }
  }

  async function getStatus() {
    return apiFetch('/api/status');
  }

  async function getSettings() {
    return apiFetch('/api/settings');
  }

  async function putSettings(payload) {
    return apiFetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  async function addMcpServer(payload) {
    return apiFetch('/api/settings/mcp/servers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  async function testRuntime() {
    return apiFetch('/api/runtime/test', { method: 'POST' });
  }

  async function getDashboard(params) {
    const q = params ? '?' + new URLSearchParams(params) : '';
    return apiFetch('/api/dashboard/summary' + q);
  }

  async function getTasks(params) {
    const q = params ? '?' + new URLSearchParams(params) : '';
    return apiFetch('/api/tasks' + q);
  }

  async function createTask(payload) {
    return apiFetch('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  async function getTask(taskId) {
    return apiFetch('/api/tasks/' + taskId);
  }

  async function stopTask(taskId) {
    return apiFetch('/api/tasks/' + taskId + '/stop', { method: 'POST' });
  }

  async function retryTask(taskId) {
    return apiFetch('/api/tasks/' + encodeURIComponent(taskId) + '/retry', { method: 'POST' });
  }

  async function continueTask(taskId) {
    return apiFetch('/api/tasks/' + encodeURIComponent(taskId) + '/continue', { method: 'POST' });
  }

  async function hintTask(taskId, text) {
    return apiFetch('/api/tasks/' + taskId + '/hint', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
  }

  async function getTraces(params) {
    const q = params ? '?' + new URLSearchParams(params) : '';
    return apiFetch('/api/traces' + q);
  }

  async function getTrace(runId) {
    return apiFetch('/api/traces/' + encodeURIComponent(runId));
  }

  async function replayTrace(runId) {
    return apiFetch('/api/traces/' + encodeURIComponent(runId) + '/replay', { method: 'POST' });
  }

  async function getLogs(params) {
    const q = params ? '?' + new URLSearchParams(params) : '';
    return apiFetch('/api/logs' + q);
  }

  async function getKnowledge() {
    return apiFetch('/api/knowledge');
  }

  async function reindexKnowledge() {
    return apiFetch('/api/knowledge/reindex', { method: 'POST' });
  }

  async function getKnowledgeDoc(docKey) {
    return apiFetch('/api/knowledge/' + encodeURIComponent(docKey));
  }

  async function openKnowledgeDocument(docKey) {
    return apiFetch('/api/knowledge/' + encodeURIComponent(docKey) + '/open');
  }

  // ── SSE event stream ──────────────────────────────────────────
  let _sse = null;
  const _sseSubs = [];
  let _sseRetries = 0;
  let _sseTimer = null;

  function subscribeEvents(fn) {
    _sseSubs.push(fn);
    _openSSE();
    return () => {
      const i = _sseSubs.indexOf(fn);
      if (i >= 0) _sseSubs.splice(i, 1);
    };
  }

  function _openSSE() {
    if (_sse) return;
    if (_sseTimer) {
      clearTimeout(_sseTimer);
      _sseTimer = null;
    }
    _sse = new EventSource('/api/events/stream');
    _sse.onopen = () => {
      _markSseAlive();
    };
    _sse.onmessage = (e) => {
      try {
        _markSseAlive();
        _sseRetries = 0;
        const ev = JSON.parse(e.data);
        _sseSubs.forEach(fn => fn(ev));
        if (window.LiveTicker && ev.type === 'tool_call') {
          window.LiveTicker._push({ kind: 'tool', who: ev.tool, what: ev.summary });
        }
      } catch {}
    };
    _sse.onerror = () => {
      if (_sse) {
        _sse.close();
        _sse = null;
      }
      if (_sseSubs.length === 0) return;
      if (_isSseFresh()) {
        _syncConnection({
          status: 'reconnecting',
          isLive: true,
          via: 'sse_retry',
        });
      } else if (_liveState.probeFailures >= PROBE_FAILURE_THRESHOLD) {
        _syncConnection({
          status: 'disconnected',
          isLive: false,
          via: 'sse_error',
        });
      } else {
        _syncConnection({
          status: 'reconnecting',
          isLive: false,
          via: 'sse_error',
        });
      }
      const delay = Math.min(1000 * Math.pow(2, _sseRetries), 30000);
      _sseRetries += 1;
      _sseTimer = setTimeout(() => {
        _sseTimer = null;
        _openSSE();
      }, delay);
    };
  }

  window.addEventListener('fh:connection', (e) => {
    if (
      e.detail?.via === 'probe'
      && e.detail?.connection?.status === 'connected'
      && _sseSubs.length > 0
    ) {
      _openSSE();
    }
  });

  // ── Memory API ────────────────────────────────────────────────
  async function getMemory(params = {}) {
    try {
      const qs = new URLSearchParams();
      if (params.status) qs.set('status', params.status);
      if (params.sort_by) qs.set('sort_by', params.sort_by);
      if (params.limit) qs.set('limit', params.limit);
      const r = await fetch('/api/memory?' + qs.toString());
      return r.ok ? r.json() : null;
    } catch { return null; }
  }

  async function getMemoryStats() {
    try { const r = await fetch('/api/memory/stats'); return r.ok ? r.json() : null; }
    catch { return null; }
  }

  async function getMemoryEntry(id) {
    try { const r = await fetch('/api/memory/' + encodeURIComponent(id)); return r.ok ? r.json() : null; }
    catch { return null; }
  }

  async function muteMemoryEntry(id) {
    try { const r = await fetch('/api/memory/' + encodeURIComponent(id) + '/mute', { method: 'POST' }); return r.ok ? r.json() : null; }
    catch { return null; }
  }

  async function activateMemoryEntry(id) {
    try { const r = await fetch('/api/memory/' + encodeURIComponent(id) + '/activate', { method: 'POST' }); return r.ok ? r.json() : null; }
    catch { return null; }
  }

  async function deleteMemoryEntry(id) {
    try { const r = await fetch('/api/memory/' + encodeURIComponent(id), { method: 'DELETE' }); return r.ok ? r.json() : null; }
    catch { return null; }
  }

  async function getMemoryGraph(params = {}) {
    try {
      const qs = new URLSearchParams();
      if (params.status) qs.set('status', params.status);
      const r = await fetch('/api/memory/graph?' + qs.toString());
      return r.ok ? r.json() : null;
    } catch { return null; }
  }

  async function getAttachments(taskId) {
    return apiFetch('/api/tasks/' + encodeURIComponent(taskId) + '/attachments');
  }

  // ── File upload ───────────────────────────────────────────────
  async function uploadKnowledgeDocument(file, onProgress) {
    try {
      const fd = new FormData();
      fd.append('file', file);
      return await new Promise((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/knowledge/documents');
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try { resolve(JSON.parse(xhr.responseText)); }
            catch { resolve(null); }
          } else {
            resolve(null);
          }
        };
        xhr.onerror = () => resolve(null);
        if (onProgress) {
          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
          };
        }
        xhr.send(fd);
      });
    } catch { return null; }
  }

  async function uploadAttachment(taskId, fileList, onProgress) {
    try {
      const fd = new FormData();
      Array.from(fileList).forEach(f => fd.append('files', f));
      return await new Promise((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/tasks/' + encodeURIComponent(taskId) + '/attachments');
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try { resolve(JSON.parse(xhr.responseText)); }
            catch { resolve(null); }
          } else {
            resolve(null);
          }
        };
        xhr.onerror = () => resolve(null);
        if (onProgress) {
          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100));
          };
        }
        xhr.send(fd);
      });
    } catch { return null; }
  }

  window.API = {
    probe,
    getConnectionState,
    getStatus,
    getSettings,
    putSettings,
    addMcpServer,
    testRuntime,
    getDashboard,
    getTasks,
    createTask,
    getTask,
    stopTask,
    retryTask,
    continueTask,
    hintTask,
    getTraces,
    getTrace,
    replayTrace,
    getLogs,
    getKnowledge,
    reindexKnowledge,
    getKnowledgeDoc,
    openKnowledgeDocument,
    subscribeEvents,
    getMemory,
    getMemoryStats,
    getMemoryEntry,
    muteMemoryEntry,
    activateMemoryEntry,
    deleteMemoryEntry,
    getMemoryGraph,
    getAttachments,
    uploadKnowledgeDocument,
    uploadAttachment,
  };
})();
