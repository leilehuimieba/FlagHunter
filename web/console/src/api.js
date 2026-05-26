// ============================================================
// FlagHunter API layer — tries /api/* first, falls back to MOCK
// Sets window.IS_LIVE = true/false and fires 'fh:connection' events
// ============================================================

(function () {
  window.IS_LIVE = false;
  const _listeners = [];

  async function probe() {
    try {
      const r = await fetch('/api/status', { signal: AbortSignal.timeout(1500) });
      if (!r.ok) throw new Error('not ok');
      const data = await r.json();
      const was = window.IS_LIVE;
      window.IS_LIVE = true;
      if (!was) _fire('connected', data);
      return true;
    } catch {
      const was = window.IS_LIVE;
      window.IS_LIVE = false;
      if (was) _fire('disconnected', null);
      return false;
    }
  }

  function _fire(type, detail) {
    window.dispatchEvent(new CustomEvent('fh:connection', { detail: { type, ...detail } }));
    _listeners.forEach(fn => fn({ type, detail }));
  }

  // Poll for connection every 8 seconds
  probe();
  setInterval(probe, 8000);

  // Generic fetch wrapper — falls back to null on error
  async function apiFetch(path, opts) {
    try {
      const r = await fetch(path, opts);
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch {
      return null;
    }
  }

  // ── API methods ───────────────────────────────────────────────

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

  async function getDashboard() {
    return apiFetch('/api/dashboard/summary');
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

  async function getLogs(params) {
    const q = params ? '?' + new URLSearchParams(params) : '';
    return apiFetch('/api/logs' + q);
  }

  async function getKnowledge() {
    return apiFetch('/api/knowledge');
  }

  // ── SSE event stream ──────────────────────────────────────────
  let _sse = null;
  const _sseSubs = [];

  function subscribeEvents(fn) {
    _sseSubs.push(fn);
    if (!_sse && window.IS_LIVE) _openSSE();
    return () => { const i = _sseSubs.indexOf(fn); if (i >= 0) _sseSubs.splice(i, 1); };
  }

  function _openSSE() {
    if (_sse) return;
    _sse = new EventSource('/api/events/stream');
    _sse.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data);
        _sseSubs.forEach(fn => fn(ev));
        // also feed into LiveTicker if available
        if (window.LiveTicker && ev.type === 'tool_call') {
          window.LiveTicker._push({ kind: 'tool', who: ev.tool, what: ev.summary });
        }
      } catch {}
    };
    _sse.onerror = () => { _sse = null; };
  }

  window.addEventListener('fh:connection', (e) => {
    if (e.detail.type === 'connected' && _sseSubs.length > 0) _openSSE();
    if (e.detail.type === 'disconnected') { if (_sse) { _sse.close(); _sse = null; } }
  });

  window.API = {
    probe, getStatus, getSettings, putSettings,
    getDashboard, getTasks, createTask, getTask, stopTask, hintTask,
    getTraces, getLogs, getKnowledge, subscribeEvents,
  };
})();
