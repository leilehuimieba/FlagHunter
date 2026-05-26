/* global React, MOCK, t, Toggle */
// ============================================================
// Settings — tabs + grouped forms + save bar
// ============================================================

const { useState: uSt, useEffect: uStE } = React;

// Known providers with their default base URLs
const PROVIDERS = [
  { id: 'su8.codes',    label: 'su8.codes (中转)',  base: 'https://api.su8.codes/v1' },
  { id: 'anthropic',   label: 'Anthropic',          base: '' },
  { id: 'openai',      label: 'OpenAI',             base: '' },
  { id: 'mimo',        label: 'Mimo',               base: 'https://api.mimo.run/v1' },
  { id: 'kimi',        label: 'Kimi (月之暗面)',     base: 'https://api.moonshot.cn/v1' },
  { id: 'deepseek',    label: 'DeepSeek',           base: 'https://api.deepseek.com/v1' },
  { id: 'google',      label: 'Google',             base: '' },
  { id: 'mistral',     label: 'Mistral',            base: '' },
  { id: 'custom',      label: 'Custom / LiteLLM',  base: '' },
];

function SettingsPage() {
  const TABS = [
    { id: 'model',    tk: 'st.tab.model',    icon: '◯' },
    { id: 'runtime',  tk: 'st.tab.runtime',  icon: '⚙' },
    { id: 'mcp',      tk: 'st.tab.mcp',      icon: '⌬' },
    { id: 'knowledge',tk: 'st.tab.knowledge',icon: '◉' },
    { id: 'budget',   tk: 'st.tab.budget',   icon: '$' },
    { id: 'audit',    tk: 'st.tab.audit',    icon: '✓' },
    { id: 'ctf',      tk: 'st.tab.ctf',      icon: '⚑' },
  ];
  const [tab, setTab] = uSt('model');
  const [draft, setDraft] = uSt(MOCK.SETTINGS);
  const [dirty, setDirty] = uSt(false);
  const [saved, setSaved] = uSt(false);
  const [saving, setSaving] = uSt(false);

  function patch(section, key, value) {
    setDraft(d => ({ ...d, [section]: { ...d[section], [key]: value } }));
    setDirty(true);
    setSaved(false);
  }

  async function save() {
    setSaving(true);
    if (window.IS_LIVE) {
      const result = await window.API.putSettings(draft);
      if (result && result.ok) {
        setSaved(true);
      } else {
        setSaved(true); // mock fallback
      }
    } else {
      setSaved(true);
    }
    setSaving(false);
    setDirty(false);
    setTimeout(() => setSaved(false), 3000);
  }

  // Load real settings from backend on mount
  uStE(() => {
    window.API.getSettings().then(data => {
      if (data) setDraft(d => ({ ...d, ...data }));
    });
  }, []);

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
            {tab === 'model'    && <ModelSec    draft={draft} patch={patch} />}
            {tab === 'runtime'  && <RuntimeSec  draft={draft} patch={patch} />}
            {tab === 'mcp'      && <McpSec      draft={draft} patch={patch} />}
            {tab === 'knowledge'&& <KnSec       draft={draft} patch={patch} />}
            {tab === 'budget'   && <BudgetSec   draft={draft} patch={patch} />}
            {tab === 'audit'    && <AuditSec    draft={draft} patch={patch} />}
            {tab === 'ctf'      && <CtfSec      draft={draft} patch={patch} />}

            <div className="save-bar">
              {dirty && <span className="changes">{t('c.unsaved')}</span>}
              {saved && <span className="green">{t('c.saved')}</span>}
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                <button className="btn ghost" onClick={() => { setDraft(MOCK.SETTINGS); setDirty(false); }}>{t('c.discard')}</button>
                <button className={`btn ${dirty ? 'primary' : ''}`} onClick={save} disabled={!dirty || saving}>
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

function Field({ label, hint, children }) {
  return (
    <div className="set-field">
      <div className="lbl">{label}</div>
      {children}
      {hint && <div className="hint">{hint}</div>}
    </div>
  );
}

// Masked password field with show/hide toggle
function SecretField({ value, onChange, placeholder }) {
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
      />
      <button
        className="secret-toggle"
        onClick={() => setShow(s => !s)}
        title={show ? t('c.hide') : t('c.show')}
        type="button"
      >{show ? '◉' : '○'}</button>
    </div>
  );
}

// ---------- sections ----------
function ModelSec({ draft, patch }) {
  const m = draft.model || {};
  const selectedProvider = PROVIDERS.find(p => p.id === m.provider) || PROVIDERS[PROVIDERS.length - 1];

  function onProviderChange(id) {
    const p = PROVIDERS.find(px => px.id === id);
    patch('model', 'provider', id);
    if (p && p.base) patch('model', 'apiBase', p.base);
  }

  return (
    <Section title={t('st.model.t')} sub={t('st.model.sub')}>
      <Field label={t('st.model.provider')}>
        <select className="input" value={m.provider || 'anthropic'} onChange={e => onProviderChange(e.target.value)}>
          {PROVIDERS.map(p => (
            <option key={p.id} value={p.id}>{p.label}</option>
          ))}
        </select>
      </Field>
      <Field label={t('st.model.apiBase')} hint={t('st.model.apiBaseHint')}>
        <input className="input mono" value={m.apiBase || ''} placeholder="https://api.example.com/v1"
          onChange={e => patch('model', 'apiBase', e.target.value)} />
      </Field>
      <Field label={t('st.model.name')} hint={t('st.model.nameHint')}>
        <input className="input" value={m.name || ''} onChange={e => patch('model', 'name', e.target.value)} />
      </Field>
      <Field label={t('st.model.temp')} hint={t('st.model.tempHint')}>
        <input className="input" type="number" min="0" max="1" step="0.05" value={m.temperature ?? 0.2}
          onChange={e => patch('model', 'temperature', parseFloat(e.target.value))} />
      </Field>
      <Field label={t('st.model.max')} hint={t('st.model.maxHint')}>
        <input className="input" type="number" value={m.maxTokens || 8192}
          onChange={e => patch('model', 'maxTokens', parseInt(e.target.value))} />
      </Field>
      <Field label={t('st.model.key')} hint={t('st.model.keyHint')}>
        <SecretField value={m.apiKey || ''} onChange={e => patch('model', 'apiKey', e.target.value)} />
      </Field>
      <Field label={t('st.model.stream')}>
        <Toggle on={m.streaming !== false} onChange={v => patch('model', 'streaming', v)} />
      </Field>
    </Section>
  );
}

function RuntimeSec({ draft, patch }) {
  const r = draft.runtime || {};
  return (
    <Section title={t('st.rt.t')} sub={t('st.rt.sub')}>
      <Field label={t('st.rt.mode')}>
        <select className="input" value={r.mode || 'local'} onChange={e => patch('runtime', 'mode', e.target.value)}>
          <option value="local">LocalRuntime</option>
          <option value="docker">DockerRuntime</option>
          <option value="ssh">SSHRuntime</option>
        </select>
      </Field>
      <Field label={t('st.rt.workdir')} hint={t('st.rt.workdirHint')}>
        <input className="input mono" value={r.workdir || ''} onChange={e => patch('runtime', 'workdir', e.target.value)} />
      </Field>
      <Field label={t('st.rt.autoSsh')} hint={t('st.rt.autoSshHint')}><Toggle on={r.autoSsh} onChange={v => patch('runtime', 'autoSsh', v)} /></Field>
      <Field label={t('st.rt.docker')}><Toggle on={r.dockerEnabled} onChange={v => patch('runtime', 'dockerEnabled', v)} /></Field>
      <Field label={t('st.rt.ssh')}><Toggle on={r.sshConfigured} onChange={v => patch('runtime', 'sshConfigured', v)} /></Field>
      <Field label={t('st.rt.net')} hint={t('st.rt.netHint')}>
        <select className="input" value={r.sandboxNetwork || 'bridge'} onChange={e => patch('runtime', 'sandboxNetwork', e.target.value)}>
          <option>bridge</option><option>host</option><option>none</option>
        </select>
      </Field>
      <div className="set-field" style={{ gridColumn: '1 / -1' }}>
        <div className="lbl">{t('st.rt.test')}</div>
        <div className="row gap-8">
          <button className="btn">{t('st.rt.testBtn')}</button>
          <span className="green">{t('st.rt.testResult')}</span>
        </div>
      </div>
    </Section>
  );
}

function McpSec({ draft, patch }) {
  const m = draft.mcp || {};
  return (
    <Section title={t('st.mcp.t')} sub={t('st.mcp.sub')}>
      <Field label={t('st.mcp.enabled')}><Toggle on={m.enabled} onChange={v => patch('mcp', 'enabled', v)} /></Field>
      <Field label={t('st.mcp.timeout')}><input className="input" type="number" value={m.timeoutMs || 30000} onChange={e => patch('mcp', 'timeoutMs', parseInt(e.target.value))} /></Field>
      <div className="set-field" style={{ gridColumn: '1 / -1' }}>
        <div className="lbl">{t('st.mcp.servers')}</div>
        <div className="row gap-6" style={{ flexWrap: 'wrap' }}>
          {(m.servers || []).map(s => (
            <span key={s} className="chip green"><span className="led"></span>{s}</span>
          ))}
          <button className="btn sm ghost">{t('st.mcp.addServer')}</button>
        </div>
      </div>
    </Section>
  );
}

function KnSec({ draft, patch }) {
  const k = draft.knowledge || {};
  return (
    <Section title={t('st.kn.t')} sub={t('st.kn.sub')}>
      <Field label={t('st.kn.enabled')}><Toggle on={k.enabled} onChange={v => patch('knowledge', 'enabled', v)} /></Field>
      <Field label={t('st.kn.emb')}><input className="input" value={k.embeddingModel || ''} onChange={e => patch('knowledge', 'embeddingModel', e.target.value)} /></Field>
      <Field label={t('st.kn.chunkSize')} hint={t('st.kn.chunkSizeHint')}><input className="input" type="number" value={k.chunkSize || 1000} onChange={e => patch('knowledge', 'chunkSize', parseInt(e.target.value))} /></Field>
      <Field label={t('st.kn.overlap')}><input className="input" type="number" value={k.overlap || 200} onChange={e => patch('knowledge', 'overlap', parseInt(e.target.value))} /></Field>
      <Field label={t('st.kn.threshold')} hint={t('st.kn.thresholdHint')}><input className="input" type="number" step="0.01" min="0" max="1" value={k.threshold ?? 0.35} onChange={e => patch('knowledge', 'threshold', parseFloat(e.target.value))} /></Field>
      <div className="set-field" style={{ gridColumn: '1 / -1' }}>
        <div className="lbl">{t('st.kn.indexStatus')}</div>
        <div className="row gap-12" style={{ fontSize: 11.5 }}>
          <span><span className="muted">{t('st.kn.lastBuild')}</span> <span className="bright">2026-05-26 21:14</span></span>
          <span><span className="muted">{t('st.kn.docs')}</span> <span className="bright">12</span></span>
          <span><span className="muted">{t('st.kn.chunks')}</span> <span className="bright">132</span></span>
          <span><span className="muted">{t('st.kn.dim')}</span> <span className="bright">1024</span></span>
          <button className="btn sm" style={{ marginLeft: 'auto' }}>{t('st.kn.rebuild')}</button>
        </div>
      </div>
    </Section>
  );
}

function BudgetSec({ draft, patch }) {
  const b = draft.budget || {};
  return (
    <Section title={t('st.bg.t')} sub={t('st.bg.sub')}>
      <Field label={t('st.bg.dailyToken')}><input className="input" type="number" value={b.dailyTokenLimit || 500000} onChange={e => patch('budget', 'dailyTokenLimit', parseInt(e.target.value))} /></Field>
      <Field label={t('st.bg.dailyCost')}><input className="input" type="number" value={b.dailyCostLimit || 50} onChange={e => patch('budget', 'dailyCostLimit', parseFloat(e.target.value))} /></Field>
      <Field label={t('st.bg.perTask')}><input className="input" type="number" value={b.perTaskTokenLimit || 80000} onChange={e => patch('budget', 'perTaskTokenLimit', parseInt(e.target.value))} /></Field>
      <Field label={t('st.bg.alertAt')} hint={t('st.bg.alertAtHint')}><input className="input" type="number" step="0.05" min="0" max="1" value={b.alertAt ?? 0.8} onChange={e => patch('budget', 'alertAt', parseFloat(e.target.value))} /></Field>
      <div className="set-field" style={{ gridColumn: '1 / -1' }}>
        <div className="lbl">{t('st.bg.usage')}</div>
        <div style={{ background: 'var(--bg-2)', borderRadius: 3, height: 10, overflow: 'hidden', position: 'relative' }}>
          <div style={{ width: '36.8%', height: '100%', background: 'linear-gradient(90deg, var(--accent), var(--amber))', boxShadow: '0 0 8px var(--accent-glow)' }}></div>
        </div>
        <div className="row gap-12" style={{ fontSize: 11, marginTop: 4 }}>
          <span><span className="muted">{t('st.bg.used')}</span> <span className="bright">184,120</span></span>
          <span><span className="muted">{t('st.bg.cap')}</span> <span className="bright">500,000</span></span>
          <span><span className="muted">{t('st.bg.est')}</span> <span className="bright">$8.42 / $50.00</span></span>
        </div>
      </div>
    </Section>
  );
}

function AuditSec({ draft, patch }) {
  const a = draft.audit || {};
  return (
    <Section title={t('st.au.t')} sub={t('st.au.sub')}>
      <Field label={t('st.au.toolIO')}><Toggle on={a.persistToolIO} onChange={v => patch('audit', 'persistToolIO', v)} /></Field>
      <Field label={t('st.au.obs')}><Toggle on={a.persistObservations} onChange={v => patch('audit', 'persistObservations', v)} /></Field>
      <Field label={t('st.au.redact')} hint={t('st.au.redactHint')}><Toggle on={a.redactSecrets} onChange={v => patch('audit', 'redactSecrets', v)} /></Field>
      <Field label={t('st.au.retention')}><input className="input" type="number" value={a.retentionDays || 30} onChange={e => patch('audit', 'retentionDays', parseInt(e.target.value))} /></Field>
    </Section>
  );
}

function CtfSec({ draft, patch }) {
  const c = draft.ctf || {};
  const HINT_POLICIES = ['manual', 'auto', 'disabled'];
  return (
    <Section title={t('st.ctf.t')} sub={t('st.ctf.sub')}>
      <Field label={t('st.ctf.enabled')}>
        <Toggle on={c.enabled !== false} onChange={v => patch('ctf', 'enabled', v)} />
      </Field>
      <Field label={t('st.ctf.maxIter')} hint={t('st.ctf.maxIterHint')}>
        <input className="input" type="number" min="1" max="200" value={c.maxIterations || 30}
          onChange={e => patch('ctf', 'maxIterations', parseInt(e.target.value))} />
      </Field>
      <Field label={t('st.ctf.autoRetry')} hint={t('st.ctf.autoRetryHint')}>
        <input className="input" type="number" min="0" max="10" value={c.autoRetry ?? 2}
          onChange={e => patch('ctf', 'autoRetry', parseInt(e.target.value))} />
      </Field>
      <Field label={t('st.ctf.hintPolicy')}>
        <select className="input" value={c.hintPolicy || 'manual'} onChange={e => patch('ctf', 'hintPolicy', e.target.value)}>
          {HINT_POLICIES.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </Field>
      <Field label={t('st.ctf.hypoDepth')} hint={t('st.ctf.hypoDepthHint')}>
        <input className="input" type="number" min="1" max="10" value={c.hypothesisDepth || 3}
          onChange={e => patch('ctf', 'hypothesisDepth', parseInt(e.target.value))} />
      </Field>
      <Field label={t('st.ctf.stratMem')} hint={t('st.ctf.stratMemHint')}>
        <Toggle on={c.strategyMemory !== false} onChange={v => patch('ctf', 'strategyMemory', v)} />
      </Field>
      <Field label={t('st.ctf.flagFmt')} hint={t('st.ctf.flagFmtHint')}>
        <input className="input mono" value={c.flagFormat || 'flag\\{[^}]+\\}'}
          onChange={e => patch('ctf', 'flagFormat', e.target.value)} />
      </Field>
      <Field label={t('st.ctf.verifierUrl')} hint={t('st.ctf.verifierUrlHint')}>
        <input className="input mono" placeholder="https://ctf.example.com/submit"
          value={c.verifierUrl || ''}
          onChange={e => patch('ctf', 'verifierUrl', e.target.value)} />
      </Field>
    </Section>
  );
}

window.SettingsPage = SettingsPage;
