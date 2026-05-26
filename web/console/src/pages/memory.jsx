/* global React, MOCK, t, fmt */
// ============================================================
// Strategy Memory Page — view / manage CTF strategy memory
// ============================================================

const { useState, useEffect, useMemo, useCallback } = React;

// ── helpers ──────────────────────────────────────────────────
const STATUS_CLS  = { active: 'green', muted: '', deprecated: 'red' };
const STATUS_DOT  = { active: '●', muted: '○', deprecated: '✕' };
const TYPE_ICON   = { web: '⬡', crypto: '⚿', reverse: '⟲', pwn: '⚡', misc: '◈', forensics: '🔍' };

function corrPct(v) { return Math.round((v || 0) * 100); }
function corrCls(v) {
  if (v >= 0.65) return 'green';
  if (v >= 0.35) return 'amber';
  return 'red';
}

function computeStats(entries) {
  return {
    total:            entries.length,
    active:           entries.filter(e => e.metadata.manual_status === 'active').length,
    muted:            entries.filter(e => e.metadata.manual_status === 'muted').length,
    deprecated:       entries.filter(e => e.metadata.manual_status === 'deprecated').length,
    audit_candidates: entries.filter(e =>
      e.metadata.applied_count >= 1 && e.metadata.success_correlation < 0.3
    ).length,
  };
}

// ── StatCard ─────────────────────────────────────────────────
function MemStatCard({ label, value, cls }) {
  return (
    <div className="mem-stat">
      <span className={'mem-stat-val' + (cls ? ' ' + cls : '')}>{value}</span>
      <span className="mem-stat-lbl">{label}</span>
    </div>
  );
}

// ── Kind tag ─────────────────────────────────────────────────
function KindTag({ text, variant }) {
  return <span className={'mem-kind' + (variant ? ' ' + variant : '')}>{text.replace(/_/g, ' ')}</span>;
}

// ── Corr bar ─────────────────────────────────────────────────
function CorrBar({ value }) {
  const pct = corrPct(value);
  const cls = corrCls(value);
  return (
    <div className="mem-corr-wrap" title={pct + '%'}>
      <div className={'mem-corr-bar ' + cls} style={{ width: pct + '%' }} />
      <span className={'mem-corr-num ' + cls}>{pct}%</span>
    </div>
  );
}

// ── Entry row ─────────────────────────────────────────────────
function EntryRow({ entry, selected, onSelect, onMute, onActivate, busy }) {
  const { id, fingerprint, winning_hypothesis_kinds, metadata, solved } = entry;
  const st = metadata.manual_status;
  const isBusy = busy === id;
  return (
    <div
      className={'mem-row' + (selected ? ' sel' : '')}
      onClick={() => onSelect(id)}
    >
      <span className={'mem-row-dot ' + (STATUS_CLS[st] || '')} title={st}>
        {STATUS_DOT[st] || '·'}
      </span>
      <span className="mem-row-type" title={fingerprint.detected_type}>
        {TYPE_ICON[fingerprint.detected_type] || '◇'}
      </span>
      <div className="mem-row-main">
        <span className="mem-row-id mono">{id}</span>
        <span className="mem-row-tech">{(fingerprint.tech_stack || []).slice(0, 2).join(' · ')}</span>
      </div>
      <div className="mem-row-kinds">
        {winning_hypothesis_kinds.slice(0, 2).map(k => (
          <KindTag key={k} text={k} variant="win" />
        ))}
        {winning_hypothesis_kinds.length === 0 && (
          <KindTag text="—" variant="" />
        )}
      </div>
      <div className="mem-row-corr">
        <CorrBar value={metadata.success_correlation} />
      </div>
      <span className="mem-row-applied">{metadata.applied_count}×</span>
      {solved && <span className="mem-solved-dot" title="solved">✓</span>}
      <div className="mem-row-actions" onClick={e => e.stopPropagation()}>
        {st === 'active' ? (
          <button
            className="mem-act-btn"
            disabled={isBusy}
            onClick={() => onMute(id)}
            title={t('mem.mute')}
          >⊘</button>
        ) : (
          <button
            className="mem-act-btn green"
            disabled={isBusy}
            onClick={() => onActivate(id)}
            title={t('mem.activate')}
          >⊕</button>
        )}
      </div>
    </div>
  );
}

// ── Detail panel ─────────────────────────────────────────────
function EntryDetail({ entry, onMute, onActivate, onDelete, busy }) {
  const {
    id, fingerprint, atomic_facts, winning_hypothesis_kinds, failed_hypothesis_kinds,
    winning_primitive_sequence, learned_rules, failed_payloads, failure_reasons,
    challenge_url, solved, avg_turns_to_flag, created_at, metadata,
  } = entry;
  const st = metadata.manual_status;
  const isBusy = busy === id;
  const corrCl = corrCls(metadata.success_correlation);

  return (
    <div className="mem-detail">
      {/* Header */}
      <div className="mem-detail-head">
        <div className="mem-detail-id mono">{id}</div>
        <div className="mem-detail-badges">
          <span className={'mem-solved-badge ' + (solved ? 'green' : 'red')}>
            {solved ? t('mem.solved') : t('mem.unsolved')}
          </span>
          <span className={'mem-status-badge ' + (STATUS_CLS[st] || '')}>
            {st.toUpperCase()}
          </span>
        </div>
      </div>

      {/* URL */}
      {challenge_url && (
        <div className="mem-detail-url mono">{challenge_url}</div>
      )}

      {/* Fingerprint */}
      <div className="mem-detail-section">
        <div className="mem-detail-sec-hd">Fingerprint</div>
        <div className="mem-fp-row">
          <span className="mem-fp-key">type</span>
          <span className={'mem-fp-val ' + (fingerprint.detected_type || '')}>{fingerprint.detected_type || '—'}</span>
        </div>
        {(fingerprint.tech_stack || []).length > 0 && (
          <div className="mem-fp-row">
            <span className="mem-fp-key">stack</span>
            <span className="mem-fp-val">{fingerprint.tech_stack.join(', ')}</span>
          </div>
        )}
        {fingerprint.auth_mechanism && (
          <div className="mem-fp-row">
            <span className="mem-fp-key">auth</span>
            <span className="mem-fp-val">{fingerprint.auth_mechanism}</span>
          </div>
        )}
      </div>

      {/* Stats */}
      <div className="mem-detail-section">
        <div className="mem-detail-sec-hd">{t('mem.stats')}</div>
        <div className="mem-stats-grid">
          <div className="mem-sg-cell">
            <span className="mem-sg-lbl">{t('mem.applied')}</span>
            <span className="mem-sg-val">{metadata.applied_count}</span>
          </div>
          <div className="mem-sg-cell">
            <span className="mem-sg-lbl">{t('mem.successRate')}</span>
            <span className={'mem-sg-val ' + corrCl}>{corrPct(metadata.success_correlation)}%</span>
          </div>
          <div className="mem-sg-cell">
            <span className="mem-sg-lbl">{t('mem.avgTurns')}</span>
            <span className="mem-sg-val">{avg_turns_to_flag || '—'}</span>
          </div>
          <div className="mem-sg-cell">
            <span className="mem-sg-lbl">{t('mem.decay')}</span>
            <span className="mem-sg-val">{Math.round((metadata.confidence_decay_factor || 1) * 100)}%</span>
          </div>
        </div>
      </div>

      {/* Winning strategies */}
      {winning_hypothesis_kinds.length > 0 && (
        <div className="mem-detail-section">
          <div className="mem-detail-sec-hd">{t('mem.winKinds')}</div>
          <div className="mem-kind-list">
            {winning_hypothesis_kinds.map(k => <KindTag key={k} text={k} variant="win" />)}
          </div>
        </div>
      )}

      {/* Attack sequence */}
      {winning_primitive_sequence.length > 0 && (
        <div className="mem-detail-section">
          <div className="mem-detail-sec-hd">{t('mem.sequence')}</div>
          <ol className="mem-sequence">
            {winning_primitive_sequence.map((s, i) => (
              <li key={i} className="mem-seq-item mono">{s}</li>
            ))}
          </ol>
        </div>
      )}

      {/* Atomic facts */}
      {atomic_facts.length > 0 && (
        <div className="mem-detail-section">
          <div className="mem-detail-sec-hd">{t('mem.facts')}</div>
          <ul className="mem-facts">
            {atomic_facts.map((f, i) => <li key={i}>{f}</li>)}
          </ul>
        </div>
      )}

      {/* Learned rules */}
      {learned_rules.length > 0 && (
        <div className="mem-detail-section">
          <div className="mem-detail-sec-hd">{t('mem.rules')}</div>
          <ol className="mem-rules">
            {learned_rules.map((r, i) => <li key={i}>{r}</li>)}
          </ol>
        </div>
      )}

      {/* Failed strategies */}
      {failed_hypothesis_kinds.length > 0 && (
        <div className="mem-detail-section">
          <div className="mem-detail-sec-hd">{t('mem.failKinds')}</div>
          <div className="mem-kind-list">
            {failed_hypothesis_kinds.map(k => <KindTag key={k} text={k} variant="fail" />)}
          </div>
        </div>
      )}

      {/* Failed payloads */}
      {(failed_payloads || []).length > 0 && (
        <div className="mem-detail-section">
          <div className="mem-detail-sec-hd">{t('mem.failedPayloads')}</div>
          <ul className="mem-facts mono">
            {failed_payloads.map((p, i) => <li key={i}>{p}</li>)}
          </ul>
        </div>
      )}

      {/* Actions */}
      <div className="mem-detail-actions">
        {st === 'active' ? (
          <button className="btn secondary" disabled={isBusy} onClick={() => onMute(id)}>
            ⊘ {t('mem.mute')}
          </button>
        ) : (
          <button className="btn primary" disabled={isBusy} onClick={() => onActivate(id)}>
            ⊕ {t('mem.activate')}
          </button>
        )}
        <button className="btn danger" disabled={isBusy} onClick={() => onDelete(id)}>
          ✕ {t('mem.delete')}
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────
function MemoryPage() {
  window.useLang();

  const [entries, setEntries]   = useState([]);
  const [stats, setStats]       = useState({ total: 0, active: 0, muted: 0, deprecated: 0, audit_candidates: 0 });
  const [filter, setFilter]     = useState('all');
  const [sortBy, setSortBy]     = useState('recent');
  const [search, setSearch]     = useState('');
  const [selected, setSelected] = useState(null);
  const [busy, setBusy]         = useState('');

  const loadData = useCallback(async () => {
    const [data, s] = await Promise.all([
      window.API.getMemory({ status: filter === 'all' ? null : filter, sort_by: sortBy }),
      window.API.getMemoryStats(),
    ]);
    if (data && data.length > 0) {
      setEntries(data);
      if (s) setStats(s);
    } else {
      const es = MOCK.MEMORY || [];
      setEntries(es);
      setStats(computeStats(es));
    }
  }, [filter, sortBy]);

  useEffect(() => { loadData(); }, [loadData]);

  const filtered = useMemo(() => {
    let list = filter !== 'all' ? entries.filter(e => e.metadata.manual_status === filter) : entries;
    const q = search.trim().toLowerCase();
    if (q) list = list.filter(e =>
      e.id.toLowerCase().includes(q) ||
      (e.fingerprint.detected_type || '').toLowerCase().includes(q) ||
      (e.fingerprint.tech_stack || []).some(s => s.toLowerCase().includes(q)) ||
      e.winning_hypothesis_kinds.some(k => k.toLowerCase().includes(q)) ||
      e.atomic_facts.some(f => f.toLowerCase().includes(q))
    );
    return list;
  }, [entries, filter, search]);

  const selectedEntry = filtered.find(e => e.id === selected) || null;

  async function handleMute(id) {
    setBusy(id);
    const updated = await window.API.muteMemoryEntry(id);
    if (updated) {
      setEntries(prev => prev.map(e => e.id === id ? updated : e));
    } else {
      setEntries(prev => prev.map(e => e.id === id
        ? { ...e, metadata: { ...e.metadata, manual_status: 'muted' } } : e));
    }
    setBusy('');
  }

  async function handleActivate(id) {
    setBusy(id);
    const updated = await window.API.activateMemoryEntry(id);
    if (updated) {
      setEntries(prev => prev.map(e => e.id === id ? updated : e));
    } else {
      setEntries(prev => prev.map(e => e.id === id
        ? { ...e, metadata: { ...e.metadata, manual_status: 'active' } } : e));
    }
    setBusy('');
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete memory entry ' + id + '?')) return;
    setBusy(id);
    await window.API.deleteMemoryEntry(id);
    setEntries(prev => prev.filter(e => e.id !== id));
    if (selected === id) setSelected(null);
    setBusy('');
  }

  const FILTERS = [
    { key: 'all',        label: t('mem.filterAll') },
    { key: 'active',     label: t('mem.active') },
    { key: 'muted',      label: t('mem.muted') },
    { key: 'deprecated', label: t('mem.deprecated') },
  ];

  return (
    <div className="mem-page">

      {/* ── Stats row ─────────────────────────────────────────── */}
      <div className="mem-stats-row">
        <MemStatCard label={t('mem.total')}      value={stats.total}            />
        <MemStatCard label={t('mem.active')}     value={stats.active}     cls="green" />
        <MemStatCard label={t('mem.muted')}      value={stats.muted}            />
        <MemStatCard label={t('mem.deprecated')} value={stats.deprecated}  cls="red" />
        <MemStatCard label={t('mem.audit')}      value={stats.audit_candidates}
          cls={stats.audit_candidates > 0 ? 'amber' : ''} />
      </div>

      {/* ── Toolbar ───────────────────────────────────────────── */}
      <div className="mem-toolbar">
        <div className="mem-filter-pills">
          {FILTERS.map(f => (
            <button
              key={f.key}
              className={'mem-filter-pill' + (filter === f.key ? ' on' : '')}
              onClick={() => { setFilter(f.key); setSelected(null); }}
            >{f.label}</button>
          ))}
        </div>
        <select
          className="input mem-sort-sel"
          value={sortBy}
          onChange={e => setSortBy(e.target.value)}
        >
          <option value="recent">{t('mem.sortRecent')}</option>
          <option value="correlation">{t('mem.sortCorr')}</option>
          <option value="applied">{t('mem.sortApplied')}</option>
        </select>
        <input
          className="input mem-search"
          placeholder={t('mem.search')}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {/* ── Content ───────────────────────────────────────────── */}
      <div className="mem-content">
        {/* List */}
        <div className="mem-list">
          {filtered.length === 0 ? (
            <div className="mem-empty">{t('mem.empty')}</div>
          ) : filtered.map(entry => (
            <EntryRow
              key={entry.id}
              entry={entry}
              selected={selected === entry.id}
              onSelect={setSelected}
              onMute={handleMute}
              onActivate={handleActivate}
              busy={busy}
            />
          ))}
        </div>

        {/* Detail */}
        <div className={'mem-detail-pane' + (selectedEntry ? ' open' : '')}>
          {selectedEntry ? (
            <EntryDetail
              entry={selectedEntry}
              onMute={handleMute}
              onActivate={handleActivate}
              onDelete={handleDelete}
              busy={busy}
            />
          ) : (
            <div className="mem-no-detail">{t('mem.noDetail')}</div>
          )}
        </div>
      </div>
    </div>
  );
}

window.MemoryPage = MemoryPage;
