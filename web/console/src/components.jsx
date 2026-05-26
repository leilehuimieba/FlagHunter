/* global React */
// ============================================================
// Shared UI primitives — StatusBadge, MetricCard, Sparkline,
// charts (mini bar / area / donut), TimelineList helpers
// ============================================================

const { useState, useEffect, useRef, useMemo, useCallback } = React;

// ---------- Status badges ----------
const STATUS_MAP = {
  running: { cls: 'amber',  tk: 'status.RUNNING' },
  queued:  { cls: 'blue',   tk: 'status.QUEUED'  },
  success: { cls: 'green',  tk: 'status.SUCCESS' },
  failed:  { cls: 'red',    tk: 'status.FAILED'  },
  stopped: { cls: '',       tk: 'status.STOPPED' },
  done:    { cls: 'green',  tk: 'status.DONE' },
  pending: { cls: '',       tk: 'status.PENDING' },
};
function StatusBadge({ status, size }) {
  const m = STATUS_MAP[status];
  const label = m ? window.t(m.tk) : (status?.toUpperCase() || '—');
  const cls = m ? m.cls : '';
  return (
    <span className={`chip ${cls} ${size === 'lg' ? 'lg' : ''}`}>
      <span className="led"></span>
      {label}
    </span>
  );
}

function TypeBadge({ type }) {
  const map = {
    web: 'blue', misc: 'magenta', reverse: 'cyan', crypto: 'amber',
    pwn: 'red', forensics: 'magenta'
  };
  if (!type) return null;
  return <span className={`chip ${map[type] || ''}`}>{type.toUpperCase()}</span>;
}

// ---------- Sparkline ----------
function Sparkline({ data, w = 80, h = 22, color = 'var(--accent)', fill = true }) {
  if (!data || !data.length) return <svg width={w} height={h} />;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const dx = w / (data.length - 1 || 1);
  const pts = data.map((v, i) => {
    const x = i * dx;
    const y = h - 2 - ((v - min) / range) * (h - 4);
    return [x, y];
  });
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ');
  const area = `${line} L${w},${h} L0,${h} Z`;
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      {fill && <path d={area} fill={color} opacity="0.14" />}
      <path d={line} stroke={color} strokeWidth="1.2" fill="none" />
    </svg>
  );
}

// ---------- Mini bar chart ----------
function MiniBarChart({ data, color = 'var(--accent)', height = 140 }) {
  const max = Math.max(...data.map(d => d.value), 1);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height }}>
      {data.map(d => {
        const pct = (d.value / max) * 100;
        return (
          <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 11.5 }}>
            <span style={{ flex: '0 0 90px', color: 'var(--fg-1)' }}>{d.name}</span>
            <div style={{ flex: 1, height: 8, background: 'var(--bg-2)', borderRadius: 2, position: 'relative', overflow: 'hidden' }}>
              <div style={{
                width: `${pct}%`, height: '100%',
                background: d.color || color,
                boxShadow: `0 0 8px ${d.color || color}`,
                opacity: 0.85,
              }} />
            </div>
            <span style={{ flex: '0 0 32px', textAlign: 'right', color: 'var(--fg-0)', fontFeatureSettings: '"tnum"' }}>
              {d.value}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------- Area chart (tokens) ----------
function AreaChart({ series, height = 180, color = 'var(--accent)' }) {
  const ref = useRef(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((ents) => setW(ents[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  if (!series?.length) return null;
  const max = Math.max(...series.map(s => s.v));
  const padL = 36, padR = 12, padT = 14, padB = 22;
  const cw = w - padL - padR;
  const ch = height - padT - padB;
  const dx = cw / (series.length - 1 || 1);
  const pts = series.map((s, i) => [padL + i * dx, padT + ch - (s.v / max) * ch]);
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ');
  const area = `${line} L${padL + cw},${padT + ch} L${padL},${padT + ch} Z`;
  const yTicks = [0, 0.5, 1].map(p => ({
    y: padT + ch - p * ch,
    label: Math.round(max * p / 1000) + 'k'
  }));
  return (
    <div ref={ref} style={{ position: 'relative', height }}>
      <svg width={w} height={height}>
        <defs>
          <linearGradient id="areaG" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.32" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {yTicks.map(t => (
          <g key={t.y}>
            <line x1={padL} y1={t.y} x2={w - padR} y2={t.y} stroke="var(--line-1)" strokeDasharray="2 4" />
            <text x={padL - 6} y={t.y + 3} textAnchor="end" fontSize="9.5" fill="var(--fg-3)">{t.label}</text>
          </g>
        ))}
        <path d={area} fill="url(#areaG)" />
        <path d={line} stroke={color} strokeWidth="1.4" fill="none" />
        {pts.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="2" fill={color} />
        ))}
        {series.map((s, i) => (
          i % 2 === 0 ? (
            <text key={i} x={padL + i * dx} y={height - 6} textAnchor="middle" fontSize="9.5" fill="var(--fg-3)">{s.t}</text>
          ) : null
        ))}
      </svg>
    </div>
  );
}

// ---------- Donut chart ----------
function Donut({ data, size = 130, label }) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const r = size / 2 - 12;
  const cx = size / 2, cy = size / 2;
  let acc = 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      <svg width={size} height={size}>
        <circle cx={cx} cy={cy} r={r} stroke="var(--bg-2)" strokeWidth="14" fill="none" />
        {data.map((d, i) => {
          const frac = d.value / total;
          const start = acc; acc += frac;
          const a1 = start * 2 * Math.PI - Math.PI / 2;
          const a2 = (start + frac) * 2 * Math.PI - Math.PI / 2;
          const x1 = cx + r * Math.cos(a1);
          const y1 = cy + r * Math.sin(a1);
          const x2 = cx + r * Math.cos(a2);
          const y2 = cy + r * Math.sin(a2);
          const large = frac > 0.5 ? 1 : 0;
          return (
            <path key={i}
              d={`M${x1},${y1} A${r},${r} 0 ${large} 1 ${x2},${y2}`}
              stroke={d.color} strokeWidth="14" fill="none" strokeLinecap="butt" />
          );
        })}
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize="18" fill="var(--fg-0)" fontWeight="500" style={{fontFamily: 'var(--font-mono)'}}>{total}</text>
        <text x={cx} y={cy + 12} textAnchor="middle" fontSize="9" fill="var(--fg-2)" letterSpacing="0.16em">{label || 'FAILURES'}</text>
      </svg>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 11.5 }}>
        {data.map(d => (
          <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 8, height: 8, background: d.color, borderRadius: 2 }} />
            <span style={{ color: 'var(--fg-1)', flex: 1 }}>{d.name}</span>
            <span style={{ color: 'var(--fg-0)', fontFeatureSettings: '"tnum"' }}>{d.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------- Stacked bar (knowledge hit trend) ----------
function BarTrend({ series, height = 140, color = 'var(--magenta)' }) {
  const max = Math.max(...series.map(s => s.v), 1);
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height, padding: '8px 4px 22px' }}>
      {series.map((s, i) => {
        const h = (s.v / max) * (height - 36);
        return (
          <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, height: '100%' }}>
            <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end', width: '100%' }}>
              <div style={{
                width: '100%',
                height: Math.max(h, 2),
                background: color, opacity: 0.7,
                borderRadius: '2px 2px 0 0',
                boxShadow: `0 0 4px ${color}`,
              }} title={`${s.t} · ${s.v}`} />
            </div>
            <span style={{ fontSize: 9, color: 'var(--fg-3)' }}>{s.t.slice(0, 2)}</span>
          </div>
        );
      })}
    </div>
  );
}

// ---------- Panel ----------
function Panel({ title, accent, actions, children, className }) {
  return (
    <div className={`panel ${className || ''}`}>
      {title && (
        <div className="panel-h">
          <span>{title}</span>
          {accent && <span className="accent">{accent}</span>}
          {actions && <div className="actions">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

// ---------- Empty state ----------
function Empty({ children }) {
  return (
    <div style={{
      padding: '40px 20px', textAlign: 'center',
      color: 'var(--fg-3)', fontSize: 12,
    }}>{children || '— no data —'}</div>
  );
}

// ---------- Loading dots ----------
function Dots() {
  return <span className="dots">
    <span style={{ animation: 'pulse 1.2s ease-in-out infinite' }}>·</span>
    <span style={{ animation: 'pulse 1.2s ease-in-out 0.2s infinite' }}>·</span>
    <span style={{ animation: 'pulse 1.2s ease-in-out 0.4s infinite' }}>·</span>
  </span>;
}

// ============================================================
// NewTaskModal
// ============================================================
function NewTaskModal({ onClose, onCreated }) {
  const [form, setForm] = useState({
    title: '',
    target: '',
    goal: '',
    ctfType: 'web',
    mode: 'agent',
    maxIter: 30,
    docker: false,
    flagFormat: 'flag\\{[^}]+\\}',
  });
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const fileRef = useRef(null);

  function patch(k, v) { setForm(f => ({ ...f, [k]: v })); setErr(''); }

  async function submit() {
    if (!form.target.trim()) { setErr(t('nt.err.noTarget')); return; }
    if (!form.title.trim()) { setErr(t('nt.err.noTitle')); return; }
    setLoading(true);
    const payload = { ...form };
    if (file) payload.attachment = file.name;
    let result = null;
    if (window.IS_LIVE) {
      result = await window.API.createTask(payload);
    }
    if (!result) {
      // mock response when backend offline
      result = {
        id: 'task_' + Date.now().toString().slice(-6),
        ...payload,
        status: 'queued',
        createdAt: new Date().toISOString(),
      };
    }
    setLoading(false);
    onCreated && onCreated(result);
    onClose();
  }

  const CTF_TYPES = ['web', 'crypto', 'reverse', 'pwn', 'misc', 'forensics'];
  const MODES = ['assist', 'agent', 'crew'];

  // close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="modal-title">{t('nt.title')}</div>
            <div className="modal-sub">{t('nt.sub')}</div>
          </div>
          <button className="icon-btn" onClick={onClose} style={{ fontSize: 16 }}>✕</button>
        </div>

        <div className="modal-body">
          <div className="modal-grid">
            {/* Task title */}
            <div className="mf full">
              <label>{t('nt.taskTitle')}</label>
              <input className="input" placeholder={t('nt.taskTitlePh')}
                value={form.title} onChange={e => patch('title', e.target.value)} />
            </div>

            {/* Target */}
            <div className="mf full">
              <label>{t('nt.target')}</label>
              <input className="input" placeholder={t('nt.targetPh')}
                value={form.target} onChange={e => patch('target', e.target.value)} />
            </div>

            {/* Goal */}
            <div className="mf full">
              <label>{t('nt.goal')}</label>
              <input className="input" placeholder={t('nt.goalPh')}
                value={form.goal} onChange={e => patch('goal', e.target.value)} />
            </div>

            {/* CTF Type */}
            <div className="mf">
              <label>{t('nt.ctfType')}</label>
              <div className="type-pills">
                {CTF_TYPES.map(tp => (
                  <span key={tp}
                    className={`type-pill ${form.ctfType === tp ? 'on' : ''}`}
                    onClick={() => patch('ctfType', tp)}
                  >{tp.toUpperCase()}</span>
                ))}
              </div>
            </div>

            {/* Mode */}
            <div className="mf">
              <label>{t('nt.mode')}</label>
              <div className="type-pills">
                {MODES.map(m => (
                  <span key={m}
                    className={`type-pill ${form.mode === m ? 'on' : ''} ${m === 'crew' ? 'crew' : ''}`}
                    onClick={() => patch('mode', m)}
                  >{m}</span>
                ))}
              </div>
            </div>

            {/* Max iterations */}
            <div className="mf">
              <label>{t('nt.maxIter')}</label>
              <input className="input" type="number" min="1" max="200"
                value={form.maxIter} onChange={e => patch('maxIter', parseInt(e.target.value) || 30)} />
            </div>

            {/* Docker */}
            <div className="mf" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <label style={{ marginBottom: 0 }}>{t('nt.docker')}</label>
              <Toggle on={form.docker} onChange={v => patch('docker', v)} />
            </div>

            {/* Flag format */}
            <div className="mf full">
              <label>{t('nt.flagFmt')}</label>
              <input className="input mono" placeholder={t('nt.flagFmtPh')}
                value={form.flagFormat} onChange={e => patch('flagFormat', e.target.value)} />
            </div>

            {/* Attachment */}
            <div className="mf full">
              <label>{t('nt.attach')}</label>
              <div
                className={`drop-zone ${file ? 'has-file' : ''}`}
                onClick={() => fileRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}
              >
                {file ? (
                  <span className="bright">{file.name} <span className="dim">({(file.size / 1024).toFixed(1)} KB)</span>
                    <span className="red" style={{ marginLeft: 8, cursor: 'pointer' }}
                      onClick={ev => { ev.stopPropagation(); setFile(null); }}>✕</span>
                  </span>
                ) : (
                  <span className="muted">{t('nt.attachDrop')}</span>
                )}
              </div>
              <input ref={fileRef} type="file" style={{ display: 'none' }}
                onChange={e => setFile(e.target.files[0] || null)} />
            </div>
          </div>

          {err && <div className="modal-err">{err}</div>}
        </div>

        <div className="modal-foot">
          <button className="btn ghost" onClick={onClose}>{t('c.cancel')}</button>
          <button className="btn primary" onClick={submit} disabled={loading}>
            {loading ? t('nt.launching') : t('c.launch')}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Toggle (reusable) ─────────────────────────────────────────
function Toggle({ on, onChange }) {
  return <div className={`toggle ${on ? 'on' : ''}`} onClick={() => onChange(!on)} />;
}

Object.assign(window, {
  StatusBadge, TypeBadge, Sparkline, MiniBarChart, AreaChart, Donut, BarTrend,
  Panel, Empty, Dots, NewTaskModal, Toggle,
});
