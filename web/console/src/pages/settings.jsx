/* global React, t, Toggle */
// ============================================================
// Settings — partial live write for env-backed fields
// ============================================================

const { useState: uSt, useEffect: uStE } = React;

function currentConnectionState() {
  if (window.API?.getConnectionState) return window.API.getConnectionState();
  return {
    status: 'disconnected',
    isLive: false,
  };
}

const PROVIDERS = [
  { id: 'su8.codes',  label: 'su8.codes (中转)', base: 'https://api.su8.codes/v1' },
  { id: 'anthropic',  label: 'Anthropic',        base: '' },
  { id: 'openai',     label: 'OpenAI',           base: '' },
  { id: 'mimo',       label: 'Mimo',             base: 'https://api.mimo.run/v1' },
  { id: 'kimi',       label: 'Kimi (月之暗面)',   base: 'https://api.moonshot.cn/v1' },
  { id: 'deepseek',   label: 'DeepSeek',         base: 'https://api.deepseek.com/v1' },
  { id: 'google',     label: 'Google',           base: '' },
  { id: 'mistral',    label: 'Mistral',          base: '' },
  { id: 'custom',     label: 'Custom / LiteLLM', base: '' },
];

const DEFAULT_META = {
  editablePaths: [
    'model.provider', 'model.apiBase', 'model.name', 'model.apiKey',
    'runtime.dockerEnabled', 'runtime.workdir',
    'budget.dailyTokenLimit', 'budget.dailyCostLimit', 'budget.perTaskTokenLimit', 'budget.alertAt',
    'knowledge.embeddingModel',
    'ctf.enabled', 'ctf.maxIterations', 'ctf.autoRetry', 'ctf.hintPolicy',
    'ctf.hypothesisDepth', 'ctf.strategyMemory', 'ctf.flagFormat', 'ctf.verifierUrl',
  ],
  restartRequiredPaths: [
    'model.provider', 'model.apiBase', 'model.name', 'model.apiKey',
    'runtime.dockerEnabled', 'runtime.workdir', 'knowledge.embeddingModel',
    'ctf.enabled', 'ctf.maxIterations', 'ctf.autoRetry', 'ctf.hintPolicy',
    'ctf.hypothesisDepth', 'ctf.strategyMemory', 'ctf.flagFormat', 'ctf.verifierUrl',
  ],
  saveMode: 'partial',
};

const SETTINGS_DEFAULTS = {
  model: {
    provider: 'custom',
    apiBase: '',
    name: '',
    temperature: 0.2,
    maxTokens: 8192,
    apiKey: '',
    streaming: true,
  },
  runtime: {
    mode: 'local',
    autoSsh: false,
    dockerEnabled: false,
    sshConfigured: false,
    workdir: 'workspaces',
    sandboxNetwork: 'host',
  },
  mcp: {
    enabled: true,
    servers: [],
    timeoutMs: 30000,
  },
  knowledge: {
    enabled: true,
    embeddingModel: 'local',
    chunkSize: 1000,
    overlap: 200,
    threshold: 0.35,
  },
  budget: {
    dailyTokenLimit: 500000,
    dailyCostLimit: 50,
    perTaskTokenLimit: 80000,
    alertAt: 0.8,
  },
  audit: {
    persistToolIO: true,
    persistObservations: true,
    redactSecrets: true,
    retentionDays: 30,
  },
  ctf: {
    enabled: true,
    maxIterations: 30,
    autoRetry: 2,
    hintPolicy: 'manual',
    hypothesisDepth: 3,
    strategyMemory: true,
    flagFormat: 'flag\\{[^}]+\\}',
    verifierUrl: '',
  },
  meta: { ...DEFAULT_META },
};

function mergeSettings(data) {
  const source = data || {};
  return {
    model: { ...SETTINGS_DEFAULTS.model, ...(source.model || {}) },
    runtime: { ...SETTINGS_DEFAULTS.runtime, ...(source.runtime || {}) },
    mcp: { ...SETTINGS_DEFAULTS.mcp, ...(source.mcp || {}) },
    knowledge: { ...SETTINGS_DEFAULTS.knowledge, ...(source.knowledge || {}) },
    budget: { ...SETTINGS_DEFAULTS.budget, ...(source.budget || {}) },
    audit: { ...SETTINGS_DEFAULTS.audit, ...(source.audit || {}) },
    ctf: { ...SETTINGS_DEFAULTS.ctf, ...(source.ctf || {}) },
    meta: { ...DEFAULT_META, ...(source.meta || {}) },
  };
}

function formatLocalTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

function isEditable(path, meta) {
  return (meta?.editablePaths || DEFAULT_META.editablePaths).includes(path);
}

function needsRestart(path, meta) {
  return (meta?.restartRequiredPaths || DEFAULT_META.restartRequiredPaths).includes(path);
}

function supportHint(base, path, meta) {
  const hints = [];
  if (base) hints.push(base);
  if (!path) return hints.join(' · ');
  if (!isEditable(path, meta)) hints.push(t('st.fieldReadOnly'));
  else if (needsRestart(path, meta)) hints.push(t('st.fieldRestart'));
  return hints.join(' · ');
}

function buildSavePayload(draft, meta) {
  const payload = {};
  Object.entries(draft || {}).forEach(([section, values]) => {
    if (section === 'meta' || !values || typeof values !== 'object') return;
    Object.entries(values).forEach(([key, value]) => {
      const path = `${section}.${key}`;
      if (!isEditable(path, meta)) return;
      if (!payload[section]) payload[section] = {};
      payload[section][key] = value;
    });
  });
  return payload;
}

function SettingsPage() {
  const TABS = [
    { id: 'model', tk: 'st.tab.model', icon: '◯' },
    { id: 'runtime', tk: 'st.tab.runtime', icon: '⚙' },
    { id: 'mcp', tk: 'st.tab.mcp', icon: '⌬' },
    { id: 'knowledge', tk: 'st.tab.knowledge', icon: '◉' },
    { id: 'budget', tk: 'st.tab.budget', icon: '$' },
    { id: 'audit', tk: 'st.tab.audit', icon: '✓' },
    { id: 'ctf', tk: 'st.tab.ctf', icon: '⚑' },
  ];

  const [tab, setTab] = uSt('model');
  const [draft, setDraft] = uSt(() => mergeSettings());
  const [baseDraft, setBaseDraft] = uSt(() => mergeSettings());
  const [meta, setMeta] = uSt(DEFAULT_META);
  const [dirty, setDirty] = uSt(false);
  const [saved, setSaved] = uSt(false);
  const [saving, setSaving] = uSt(false);
  const [error, setError] = uSt('');
  const [saveResult, setSaveResult] = uSt(null);
  const [connection, setConnection] = uSt(() => currentConnectionState());
  const [dashboardStats, setDashboardStats] = uSt(null);
  const [knowledgeDocs, setKnowledgeDocs] = uSt(null);

  function patch(section, key, value) {
    const path = `${section}.${key}`;
    if (!isEditable(path, meta)) return;
    setDraft(d => ({ ...d, [section]: { ...d[section], [key]: value } }));
    setDirty(true);
    setSaved(false);
    setError('');
  }

  async function loadSettings() {
    const data = await window.API.getSettings();
    if (!data) return false;
    const merged = mergeSettings(data);
    setDraft(merged);
    setBaseDraft(merged);
    setMeta(merged.meta || DEFAULT_META);
    setDirty(false);
    setError('');
    return true;
  }

  async function refreshReadonlyData() {
    const [dashboardData, knowledgeData] = await Promise.all([
      window.API.getDashboard(),
      window.API.getKnowledge(),
    ]);
    setDashboardStats(dashboardData || null);
    setKnowledgeDocs(Array.isArray(knowledgeData) ? knowledgeData : []);
  }

  async function save() {
    if (connection?.status !== 'connected') {
      setError(t('st.saveLiveOnly'));
      return;
    }
    setSaving(true);
    setSaved(false);
    setError('');
    try {
      const resp = await window.API.putSettings(buildSavePayload(draft, meta));
      if (!resp || !resp.ok) {
        setError(t('st.saveError'));
        return;
      }
      const merged = mergeSettings(resp.settings || draft);
      setDraft(merged);
      setBaseDraft(merged);
      setMeta(merged.meta || DEFAULT_META);
      setDirty(false);
      setSaved(true);
      setSaveResult(resp);
      setTimeout(() => setSaved(false), 3000);
    } catch {
      setError(t('st.saveError'));
    } finally {
      setSaving(false);
    }
  }

  uStE(() => {
    loadSettings();
    refreshReadonlyData();
    const handler = (e) => {
      const nextConnection = (
        e.detail?.connection
        || currentConnectionState()
      );
      setConnection(nextConnection);
      if (nextConnection.status === 'connected') refreshReadonlyData();
    };
    window.addEventListener('fh:connection', handler);
    return () => window.removeEventListener('fh:connection', handler);
  }, []);

  const sharedProps = { draft, patch, meta, dashboardStats, knowledgeDocs };

  return (
    <div className="page" style={{ minHeight: 0 }}>
      <div className="page-h">
        <div>
          <div className="t">{t('st.t')}</div>
          <div className="sub">{t('st.sub')}</div>
        </div>
      </div>

      <Panel style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div className="set-layout" style={{ flex: 1 }}>
          <div className="set-tabs" style={{ borderRight: '1px solid var(--line-1)' }}>
            {TABS.map(tg => (
              <div key={tg.id} className={`set-tab ${tab === tg.id ? 'on' : ''}`} onClick={() => setTab(tg.id)}>
                <span className="ico">{tg.icon}</span>
                <span>{t(tg.tk)}</span>
                {tg.id === 'ctf' && draft.ctf?.enabled && (
                  <span className="badge" style={{ marginLeft: 'auto', background: 'var(--accent)', color: 'var(--bg-0)' }}>ON</span>
                )}
              </div>
            ))}
          </div>
          <div className="set-body">
            {tab === 'model' && <ModelSec {...sharedProps} />}
            {tab === 'runtime' && <RuntimeSec {...sharedProps} />}
            {tab === 'mcp' && <McpSec {...sharedProps} />}
            {tab === 'knowledge' && <KnSec {...sharedProps} />}
            {tab === 'budget' && <BudgetSec {...sharedProps} />}
            {tab === 'audit' && <AuditSec {...sharedProps} />}
            {tab === 'ctf' && <CtfSec {...sharedProps} />}

            <div className="save-bar">
              {dirty && <span className="changes">{t('c.unsaved')}</span>}
              {saved && <span className="green">{t('c.saved')}</span>}
              {error && <span className="red">{error}</span>}
              {!dirty && saveResult?.ignored?.length > 0 && (
                <span className="muted">{t('st.partialSave', saveResult.saved.length, saveResult.ignored.length)}</span>
              )}
              {!dirty && saveResult?.restartRequired?.length > 0 && (
                <span className="amber">{t('st.restartHint', saveResult.restartRequired.length)}</span>
              )}
              <span className="muted" style={{ marginLeft: 12, fontSize: 11 }}>
                {connection?.status === 'connected' ? t('st.liveWritable') : t('st.saveLiveOnly')}
              </span>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                <button
                  className="btn ghost"
                  disabled={saving || !dirty}
                  onClick={() => {
                    setDraft(mergeSettings(baseDraft));
                    setDirty(false);
                    setSaved(false);
                    setError('');
                  }}
                >
                  {t('c.discard')}
                </button>
                <button
                  className={`btn ${dirty ? 'primary' : ''}`}
                  onClick={save}
                  disabled={!dirty || saving || connection?.status !== 'connected'}
                  title={connection?.status !== 'connected' ? t('st.saveLiveOnly') : ''}
                >
                  {saving ? '…' : t('c.save')}
                </button>
              </div>
            </div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function Section({ title, sub, children }) {
  return (
    <div className="set-section">
      <div className="h">{title}</div>
      <div className="sub">{sub}</div>
      <div className="set-grid">{children}</div>
    </div>
  );
}

function SupportBadges({ path, meta }) {
  if (!path) return null;
  const editable = isEditable(path, meta);
  return (
    <span className="badges">
      <span className={`chip ${editable ? 'green' : 'ghost'}`}>{editable ? t('st.editable') : t('st.readOnlyChip')}</span>
      {editable && needsRestart(path, meta) && <span className="chip ghost">{t('st.restartChip')}</span>}
    </span>
  );
}

function Field({ label, hint, children, path, meta }) {
  return (
    <div className="set-field">
      <div className="lbl">
        <span>{label}</span>
        <SupportBadges path={path} meta={meta} />
      </div>
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

function SecretField({ value, onChange, placeholder, disabled = false, title = '' }) {
  const [show, setShow] = uSt(false);
  return (
    <div className="secret-field">
      <input
        className="input"
        type={show ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        placeholder={placeholder || ''}
        autoComplete="off"
        disabled={disabled}
        title={title}
      />
      <button
        className="secret-toggle"
        onClick={() => setShow(s => !s)}
        title={show ? t('c.hide') : t('c.show')}
        type="button"
        disabled={disabled}
      >{show ? '◉' : '○'}</button>
    </div>
  );
}

function ModelSec({ draft, patch, meta }) {
  const m = draft.model || {};

  function onProviderChange(id) {
    const p = PROVIDERS.find(px => px.id === id);
    patch('model', 'provider', id);
    if (p && p.base) patch('model', 'apiBase', p.base);
  }

  return (
    <Section title={t('st.model.t')} sub={t('st.model.sub')}>
      <Field label={t('st.model.provider')} path="model.provider" meta={meta}>
        <select className="input" value={m.provider || 'anthropic'} onChange={e => onProviderChange(e.target.value)} disabled={!isEditable('model.provider', meta)}>
          {PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
      </Field>
      <Field label={t('st.model.apiBase')} hint={supportHint(t('st.model.apiBaseHint'), 'model.apiBase', meta)} path="model.apiBase" meta={meta}>
        <input className="input mono" value={m.apiBase || ''} placeholder="https://api.example.com/v1" onChange={e => patch('model', 'apiBase', e.target.value)} disabled={!isEditable('model.apiBase', meta)} />
      </Field>
      <Field label={t('st.model.name')} hint={supportHint(t('st.model.nameHint'), 'model.name', meta)} path="model.name" meta={meta}>
        <input className="input" value={m.name || ''} onChange={e => patch('model', 'name', e.target.value)} disabled={!isEditable('model.name', meta)} />
      </Field>
      <Field label={t('st.model.temp')} hint={supportHint(t('st.model.tempHint'), 'model.temperature', meta)} path="model.temperature" meta={meta}>
        <input className="input" type="number" min="0" max="1" step="0.05" value={m.temperature ?? 0.2} onChange={e => patch('model', 'temperature', parseFloat(e.target.value))} disabled={!isEditable('model.temperature', meta)} />
      </Field>
      <Field label={t('st.model.max')} hint={supportHint(t('st.model.maxHint'), 'model.maxTokens', meta)} path="model.maxTokens" meta={meta}>
        <input className="input" type="number" value={m.maxTokens || 8192} onChange={e => patch('model', 'maxTokens', parseInt(e.target.value, 10))} disabled={!isEditable('model.maxTokens', meta)} />
      </Field>
      <Field label={t('st.model.key')} hint={supportHint(t('st.model.keyHint'), 'model.apiKey', meta)} path="model.apiKey" meta={meta}>
        <SecretField value={m.apiKey || ''} onChange={e => patch('model', 'apiKey', e.target.value)} disabled={!isEditable('model.apiKey', meta)} title={!isEditable('model.apiKey', meta) ? t('st.fieldReadOnly') : ''} />
      </Field>
      <Field label={t('st.model.stream')} hint={supportHint('', 'model.streaming', meta)} path="model.streaming" meta={meta}>
        <Toggle on={m.streaming !== false} onChange={v => patch('model', 'streaming', v)} disabled={!isEditable('model.streaming', meta)} title={!isEditable('model.streaming', meta) ? t('st.fieldReadOnly') : ''} />
      </Field>
    </Section>
  );
}

function RuntimeSec({ draft, patch, meta }) {
  const r = draft.runtime || {};
  return (
    <Section title={t('st.rt.t')} sub={t('st.rt.sub')}>
      <Field label={t('st.rt.mode')} hint={supportHint('', 'runtime.mode', meta)} path="runtime.mode" meta={meta}>
        <select className="input" value={r.mode || 'local'} onChange={e => patch('runtime', 'mode', e.target.value)} disabled={!isEditable('runtime.mode', meta)}>
          <option value="local">LocalRuntime</option>
          <option value="docker">DockerRuntime</option>
          <option value="ssh">SSHRuntime</option>
        </select>
      </Field>
      <Field label={t('st.rt.workdir')} hint={supportHint(t('st.rt.workdirHint'), 'runtime.workdir', meta)} path="runtime.workdir" meta={meta}>
        <input className="input mono" value={r.workdir || ''} onChange={e => patch('runtime', 'workdir', e.target.value)} disabled={!isEditable('runtime.workdir', meta)} />
      </Field>
      <Field label={t('st.rt.autoSsh')} hint={supportHint(t('st.rt.autoSshHint'), 'runtime.autoSsh', meta)} path="runtime.autoSsh" meta={meta}>
        <Toggle on={r.autoSsh} onChange={v => patch('runtime', 'autoSsh', v)} disabled={!isEditable('runtime.autoSsh', meta)} title={!isEditable('runtime.autoSsh', meta) ? t('st.fieldReadOnly') : ''} />
      </Field>
      <Field label={t('st.rt.docker')} hint={supportHint('', 'runtime.dockerEnabled', meta)} path="runtime.dockerEnabled" meta={meta}>
        <Toggle on={r.dockerEnabled} onChange={v => patch('runtime', 'dockerEnabled', v)} disabled={!isEditable('runtime.dockerEnabled', meta)} title={!isEditable('runtime.dockerEnabled', meta) ? t('st.fieldReadOnly') : ''} />
      </Field>
      <Field label={t('st.rt.ssh')} hint={supportHint('', 'runtime.sshConfigured', meta)} path="runtime.sshConfigured" meta={meta}>
        <Toggle on={r.sshConfigured} onChange={v => patch('runtime', 'sshConfigured', v)} disabled={!isEditable('runtime.sshConfigured', meta)} title={!isEditable('runtime.sshConfigured', meta) ? t('st.fieldReadOnly') : ''} />
      </Field>
      <Field label={t('st.rt.net')} hint={supportHint(t('st.rt.netHint'), 'runtime.sandboxNetwork', meta)} path="runtime.sandboxNetwork" meta={meta}>
        <select className="input" value={r.sandboxNetwork || 'bridge'} onChange={e => patch('runtime', 'sandboxNetwork', e.target.value)} disabled={!isEditable('runtime.sandboxNetwork', meta)}>
          <option>bridge</option><option>host</option><option>none</option>
        </select>
      </Field>
      <div className="set-field" style={{ gridColumn: '1 / -1' }}>
        <div className="lbl">
          <span>{t('st.rt.test')}</span>
          <span className="badges"><span className="chip ghost">{t('st.readOnlyChip')}</span></span>
        </div>
        <div className="row gap-8">
          <button className="btn" disabled={true} title={t('c.unavailable')}>{t('st.rt.testBtn')}</button>
          <span className="muted">{t('c.unavailable')}</span>
        </div>
      </div>
    </Section>
  );
}

function McpSec({ draft, patch, meta }) {
  const m = draft.mcp || {};
  return (
    <Section title={t('st.mcp.t')} sub={t('st.mcp.sub')}>
      <Field label={t('st.mcp.enabled')} hint={supportHint('', 'mcp.enabled', meta)} path="mcp.enabled" meta={meta}>
        <Toggle on={m.enabled} onChange={v => patch('mcp', 'enabled', v)} disabled={!isEditable('mcp.enabled', meta)} title={t('st.fieldReadOnly')} />
      </Field>
      <Field label={t('st.mcp.timeout')} hint={supportHint('', 'mcp.timeoutMs', meta)} path="mcp.timeoutMs" meta={meta}>
        <input className="input" type="number" value={m.timeoutMs || 30000} onChange={e => patch('mcp', 'timeoutMs', parseInt(e.target.value, 10))} disabled={!isEditable('mcp.timeoutMs', meta)} />
      </Field>
      <div className="set-field" style={{ gridColumn: '1 / -1' }}>
        <div className="lbl">
          <span>{t('st.mcp.servers')}</span>
          <span className="badges"><span className="chip ghost">{t('st.readOnlyChip')}</span></span>
        </div>
        <div className="row gap-6" style={{ flexWrap: 'wrap' }}>
          {(m.servers || []).map(s => (
            <span key={s} className="chip green"><span className="led"></span>{s}</span>
          ))}
          <button className="btn sm ghost" disabled={true} title={t('c.unavailable')}>{t('st.mcp.addServer')}</button>
        </div>
      </div>
    </Section>
  );
}

function KnSec({ draft, patch, meta, knowledgeDocs }) {
  const k = draft.knowledge || {};
  const docs = Array.isArray(knowledgeDocs) ? knowledgeDocs : [];
  const totalChunks = docs.reduce((sum, doc) => sum + Number(doc.chunkCount || 0), 0);
  const latestBuild = docs.reduce((latest, doc) => {
    if (!doc?.updatedAt) return latest;
    if (!latest) return doc.updatedAt;
    return new Date(doc.updatedAt) > new Date(latest) ? doc.updatedAt : latest;
  }, null);
  return (
    <Section title={t('st.kn.t')} sub={t('st.kn.sub')}>
      <Field label={t('st.kn.enabled')} hint={supportHint('', 'knowledge.enabled', meta)} path="knowledge.enabled" meta={meta}>
        <Toggle on={k.enabled} onChange={v => patch('knowledge', 'enabled', v)} disabled={!isEditable('knowledge.enabled', meta)} title={t('st.fieldReadOnly')} />
      </Field>
      <Field label={t('st.kn.emb')} hint={supportHint('', 'knowledge.embeddingModel', meta)} path="knowledge.embeddingModel" meta={meta}>
        <input className="input" value={k.embeddingModel || ''} onChange={e => patch('knowledge', 'embeddingModel', e.target.value)} disabled={!isEditable('knowledge.embeddingModel', meta)} />
      </Field>
      <Field label={t('st.kn.chunkSize')} hint={supportHint(t('st.kn.chunkSizeHint'), 'knowledge.chunkSize', meta)} path="knowledge.chunkSize" meta={meta}>
        <input className="input" type="number" value={k.chunkSize || 1000} onChange={e => patch('knowledge', 'chunkSize', parseInt(e.target.value, 10))} disabled={!isEditable('knowledge.chunkSize', meta)} />
      </Field>
      <Field label={t('st.kn.overlap')} hint={supportHint('', 'knowledge.overlap', meta)} path="knowledge.overlap" meta={meta}>
        <input className="input" type="number" value={k.overlap || 200} onChange={e => patch('knowledge', 'overlap', parseInt(e.target.value, 10))} disabled={!isEditable('knowledge.overlap', meta)} />
      </Field>
      <Field label={t('st.kn.threshold')} hint={supportHint(t('st.kn.thresholdHint'), 'knowledge.threshold', meta)} path="knowledge.threshold" meta={meta}>
        <input className="input" type="number" step="0.01" min="0" max="1" value={k.threshold ?? 0.35} onChange={e => patch('knowledge', 'threshold', parseFloat(e.target.value))} disabled={!isEditable('knowledge.threshold', meta)} />
      </Field>
      <div className="set-field" style={{ gridColumn: '1 / -1' }}>
        <div className="lbl">
          <span>{t('st.kn.indexStatus')}</span>
          <span className="badges"><span className="chip ghost">{t('st.readOnlyChip')}</span></span>
        </div>
        <div className="row gap-12" style={{ fontSize: 11.5 }}>
          <span><span className="muted">{t('st.kn.lastBuild')}</span> <span className="bright">{formatLocalTime(latestBuild)}</span></span>
          <span><span className="muted">{t('st.kn.docs')}</span> <span className="bright">{docs.length}</span></span>
          <span><span className="muted">{t('st.kn.chunks')}</span> <span className="bright">{totalChunks}</span></span>
          <span><span className="muted">{t('st.kn.dim')}</span> <span className="bright">—</span></span>
          <button className="btn sm" style={{ marginLeft: 'auto' }} disabled={true} title={t('c.unavailable')}>{t('st.kn.rebuild')}</button>
        </div>
      </div>
    </Section>
  );
}

function BudgetSec({ draft, patch, meta, dashboardStats }) {
  const b = draft.budget || {};
  const usedTokens = Number(dashboardStats?.kpis?.dailyTokens || 0);
  const tokenCap = Number(b.dailyTokenLimit || 0);
  const usagePct = tokenCap > 0 ? Math.min(100, (usedTokens / tokenCap) * 100) : 0;
  const estCost = Number(dashboardStats?.kpis?.estimatedCost || 0);
  return (
    <Section title={t('st.bg.t')} sub={t('st.bg.sub')}>
      <Field label={t('st.bg.dailyToken')} path="budget.dailyTokenLimit" meta={meta}>
        <input className="input" type="number" value={b.dailyTokenLimit || 500000} onChange={e => patch('budget', 'dailyTokenLimit', parseInt(e.target.value, 10))} disabled={!isEditable('budget.dailyTokenLimit', meta)} />
      </Field>
      <Field label={t('st.bg.dailyCost')} path="budget.dailyCostLimit" meta={meta}>
        <input className="input" type="number" value={b.dailyCostLimit || 50} onChange={e => patch('budget', 'dailyCostLimit', parseFloat(e.target.value))} disabled={!isEditable('budget.dailyCostLimit', meta)} />
      </Field>
      <Field label={t('st.bg.perTask')} path="budget.perTaskTokenLimit" meta={meta}>
        <input className="input" type="number" value={b.perTaskTokenLimit || 80000} onChange={e => patch('budget', 'perTaskTokenLimit', parseInt(e.target.value, 10))} disabled={!isEditable('budget.perTaskTokenLimit', meta)} />
      </Field>
      <Field label={t('st.bg.alertAt')} hint={supportHint(t('st.bg.alertAtHint'), 'budget.alertAt', meta)} path="budget.alertAt" meta={meta}>
        <input className="input" type="number" step="0.05" min="0" max="1" value={b.alertAt ?? 0.8} onChange={e => patch('budget', 'alertAt', parseFloat(e.target.value))} disabled={!isEditable('budget.alertAt', meta)} />
      </Field>
      <div className="set-field" style={{ gridColumn: '1 / -1' }}>
        <div className="lbl">
          <span>{t('st.bg.usage')}</span>
          <span className="badges"><span className="chip ghost">{t('st.readOnlyChip')}</span></span>
        </div>
        <div style={{ background: 'var(--bg-2)', borderRadius: 3, height: 10, overflow: 'hidden', position: 'relative' }}>
          <div style={{ width: `${usagePct}%`, height: '100%', background: 'linear-gradient(90deg, var(--accent), var(--amber))', boxShadow: '0 0 8px var(--accent-glow)' }}></div>
        </div>
        <div className="row gap-12" style={{ fontSize: 11, marginTop: 4 }}>
          <span><span className="muted">{t('st.bg.used')}</span> <span className="bright">{usedTokens.toLocaleString()}</span></span>
          <span><span className="muted">{t('st.bg.cap')}</span> <span className="bright">{tokenCap.toLocaleString()}</span></span>
          <span><span className="muted">{t('st.bg.est')}</span> <span className="bright">${estCost.toFixed(2)} / ${Number(b.dailyCostLimit || 0).toFixed(2)}</span></span>
        </div>
      </div>
    </Section>
  );
}

function AuditSec({ draft, patch, meta }) {
  const a = draft.audit || {};
  return (
    <Section title={t('st.au.t')} sub={t('st.au.sub')}>
      <Field label={t('st.au.toolIO')} hint={supportHint('', 'audit.persistToolIO', meta)} path="audit.persistToolIO" meta={meta}>
        <Toggle on={a.persistToolIO} onChange={v => patch('audit', 'persistToolIO', v)} disabled={!isEditable('audit.persistToolIO', meta)} title={t('st.fieldReadOnly')} />
      </Field>
      <Field label={t('st.au.obs')} hint={supportHint('', 'audit.persistObservations', meta)} path="audit.persistObservations" meta={meta}>
        <Toggle on={a.persistObservations} onChange={v => patch('audit', 'persistObservations', v)} disabled={!isEditable('audit.persistObservations', meta)} title={t('st.fieldReadOnly')} />
      </Field>
      <Field label={t('st.au.redact')} hint={supportHint(t('st.au.redactHint'), 'audit.redactSecrets', meta)} path="audit.redactSecrets" meta={meta}>
        <Toggle on={a.redactSecrets} onChange={v => patch('audit', 'redactSecrets', v)} disabled={!isEditable('audit.redactSecrets', meta)} title={t('st.fieldReadOnly')} />
      </Field>
      <Field label={t('st.au.retention')} hint={supportHint('', 'audit.retentionDays', meta)} path="audit.retentionDays" meta={meta}>
        <input className="input" type="number" value={a.retentionDays || 30} onChange={e => patch('audit', 'retentionDays', parseInt(e.target.value, 10))} disabled={!isEditable('audit.retentionDays', meta)} />
      </Field>
    </Section>
  );
}

function CtfSec({ draft, patch, meta }) {
  const c = draft.ctf || {};
  const HINT_POLICIES = ['manual', 'auto', 'disabled'];
  return (
    <Section title={t('st.ctf.t')} sub={t('st.ctf.sub')}>
      <Field label={t('st.ctf.enabled')} path="ctf.enabled" meta={meta}>
        <Toggle on={c.enabled !== false} onChange={v => patch('ctf', 'enabled', v)} disabled={!isEditable('ctf.enabled', meta)} />
      </Field>
      <Field label={t('st.ctf.maxIter')} hint={supportHint(t('st.ctf.maxIterHint'), 'ctf.maxIterations', meta)} path="ctf.maxIterations" meta={meta}>
        <input className="input" type="number" min="1" max="200" value={c.maxIterations || 30} onChange={e => patch('ctf', 'maxIterations', parseInt(e.target.value, 10))} disabled={!isEditable('ctf.maxIterations', meta)} />
      </Field>
      <Field label={t('st.ctf.autoRetry')} hint={supportHint(t('st.ctf.autoRetryHint'), 'ctf.autoRetry', meta)} path="ctf.autoRetry" meta={meta}>
        <input className="input" type="number" min="0" max="10" value={c.autoRetry ?? 2} onChange={e => patch('ctf', 'autoRetry', parseInt(e.target.value, 10))} disabled={!isEditable('ctf.autoRetry', meta)} />
      </Field>
      <Field label={t('st.ctf.hintPolicy')} hint={supportHint('', 'ctf.hintPolicy', meta)} path="ctf.hintPolicy" meta={meta}>
        <select className="input" value={c.hintPolicy || 'manual'} onChange={e => patch('ctf', 'hintPolicy', e.target.value)} disabled={!isEditable('ctf.hintPolicy', meta)}>
          {HINT_POLICIES.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </Field>
      <Field label={t('st.ctf.hypoDepth')} hint={supportHint(t('st.ctf.hypoDepthHint'), 'ctf.hypothesisDepth', meta)} path="ctf.hypothesisDepth" meta={meta}>
        <input className="input" type="number" min="1" max="10" value={c.hypothesisDepth || 3} onChange={e => patch('ctf', 'hypothesisDepth', parseInt(e.target.value, 10))} disabled={!isEditable('ctf.hypothesisDepth', meta)} />
      </Field>
      <Field label={t('st.ctf.stratMem')} hint={supportHint(t('st.ctf.stratMemHint'), 'ctf.strategyMemory', meta)} path="ctf.strategyMemory" meta={meta}>
        <Toggle on={c.strategyMemory !== false} onChange={v => patch('ctf', 'strategyMemory', v)} disabled={!isEditable('ctf.strategyMemory', meta)} />
      </Field>
      <Field label={t('st.ctf.flagFmt')} hint={supportHint(t('st.ctf.flagFmtHint'), 'ctf.flagFormat', meta)} path="ctf.flagFormat" meta={meta}>
        <input className="input mono" value={c.flagFormat || 'flag\\{[^}]+\\}'} onChange={e => patch('ctf', 'flagFormat', e.target.value)} disabled={!isEditable('ctf.flagFormat', meta)} />
      </Field>
      <Field label={t('st.ctf.verifierUrl')} hint={supportHint(t('st.ctf.verifierUrlHint'), 'ctf.verifierUrl', meta)} path="ctf.verifierUrl" meta={meta}>
        <input className="input mono" placeholder="https://ctf.example.com/submit" value={c.verifierUrl || ''} onChange={e => patch('ctf', 'verifierUrl', e.target.value)} disabled={!isEditable('ctf.verifierUrl', meta)} />
      </Field>
    </Section>
  );
}

window.SettingsPage = SettingsPage;
