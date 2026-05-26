// ============================================================
// FlagHunter API layer — tries /api/* first, falls back to MOCK
// Sets window.IS_LIVE = true/false and fires 'fh:connection' events
// ============================================================

(function () {
  window.IS_LIVE = false;
  window.FH_NO_MOCK = window.FH_NO_MOCK || false;  // set true to disable MOCK fallback
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
  let _sseRetries = 0;
  let _sseTimer = null;

  function subscribeEvents(fn) {
    _sseSubs.push(fn);
    _openSSE();  // always open SSE eagerly (IS_LIVE guard removed — fixes issue #1 and #2)
    return () => { const i = _sseSubs.indexOf(fn); if (i >= 0) _sseSubs.splice(i, 1); };
  }

  function _openSSE() {
    if (_sse) return;
    if (_sseTimer) { clearTimeout(_sseTimer); _sseTimer = null; }
    _sse = new EventSource('/api/events/stream');
    _sse.onmessage = (e) => {
      try {
        _sseRetries = 0;  // reset backoff on successful message
        const ev = JSON.parse(e.data);
        _sseSubs.forEach(fn => fn(ev));
        // also feed into LiveTicker if available
        if (window.LiveTicker && ev.type === 'tool_call') {
          window.LiveTicker._push({ kind: 'tool', who: ev.tool, what: ev.summary });
        }
      } catch {}
    };
    _sse.onerror = () => {
      if (_sse) { _sse.close(); _sse = null; }
      // exponential backoff: 1s → 2s → 4s → 8s → 16s → 30s max (fixes issue #3)
      if (_sseSubs.length === 0) return;
      const delay = Math.min(1000 * Math.pow(2, _sseRetries), 30000);
      _sseRetries++;
      _sseTimer = setTimeout(() => {
        _sseTimer = null;
        _openSSE();
      }, delay);
    };
  }

  window.addEventListener('fh:connection', (e) => {
    if (e.detail.type === 'connected' && _sseSubs.length > 0) _openSSE();
    if (e.detail.type === 'disconnected') { if (_sse) { _sse.close(); _sse = null; } }
  });

  // ── Memory API ────────────────────────────────────────────────
  async function getMemory(params = {}) {
    try {
      const qs = new URLSearchParams();
      if (params.status) qs.set('status', params.status);
      if (params.sort_by) qs.set('sort_by', params.sort_by);
      if (params.limit)   qs.set('limit', params.limit);
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

  async function getAttachments(taskId) {
    return apiFetch('/api/tasks/' + encodeURIComponent(taskId) + '/attachments');
  }

  // ── File upload ───────────────────────────────────────────────
  // fileList: FileList or Array<File>
  // Returns { taskId, files: [{name, size, path}] } or null on error
  async function uploadAttachment(taskId, fileList, onProgress) {
    try {
      const fd = new FormData();
      Array.from(fileList).forEach(f => fd.append('files', f));
      // Use XMLHttpRequest so we get upload progress events
      return await new Promise((resolve, reject) => {
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
    probe, getStatus, getSettings, putSettings,
    getDashboard, getTasks, createTask, getTask, stopTask, hintTask,
    getTraces, getLogs, getKnowledge, subscribeEvents,
    getMemory, getMemoryStats, getMemoryEntry, muteMemoryEntry, activateMemoryEntry, deleteMemoryEntry,
    getAttachments, uploadAttachment,
  };
})();
