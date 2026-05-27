/* global React, MOCK, fmt, t */
// ============================================================
// Knowledge — list + detail
// ============================================================

const { useState: uK, useEffect: uKE, useMemo: uKM } = React;

function relTime(iso) {
  return iso ? fmt.since(iso) : '—';
}

function KnowledgePage({ docId, onNav }) {
  if (docId) return <KnowledgeDetail docId={docId} onNav={onNav} />;
  return <KnowledgeList onNav={onNav} />;
}

function KnowledgeList({ onNav }) {
  const [q, setQ] = uK('');
  const [tag, setTag] = uK('all');
  const [apiDocs, setApiDocs] = uK(null);

  uKE(() => {
    window.API.getKnowledge().then(data => {
      if (data && Array.isArray(data)) setApiDocs(data);
    });
  }, []);

  const sourceDocs = window.IS_LIVE ? (apiDocs || []) : (apiDocs || MOCK.KNOWLEDGE);
  const docs = uKM(() => sourceDocs.filter(d =>
    (!q || d.title.toLowerCase().includes(q.toLowerCase()) || d.sourcePath.includes(q))
    && (tag === 'all' || (d.tags || []).includes(tag))
  ), [q, tag, sourceDocs]);

  const totalHits = sourceDocs.reduce((s, d) => s + (d.hitCount || 0), 0);
  const totalChunks = sourceDocs.reduce((s, d) => s + (d.chunkCount || 0), 0);
  const topDoc = sourceDocs.slice().sort((a, b) => (b.hitCount || 0) - (a.hitCount || 0))[0];

  const tags = ['all', 'web', 'misc', 'reverse', 'forensics', 'meta', 'recon'];

  return (
    <div className="page">
      <div className="page-h">
        <div>
          <div className="t">{t('kb.t')}</div>
          <div className="sub">{t('kb.sub', sourceDocs.length, totalChunks, totalHits)}</div>
        </div>
        <div className="row">
          <button className="btn ghost">{t('c.reindex')}</button>
          <button className="btn ghost">⬇ {t('c.export')}</button>
          <button className="btn primary">{t('c.addDoc')}</button>
        </div>
      </div>

      <div className="dash-row r4">
        <KSt label={t('kb.stat.docs')}      value={sourceDocs.length} sub={t('kb.stat.indexed')} />
        <KSt label={t('kb.stat.chunks')}    value={totalChunks} sub={t('kb.stat.perDoc', sourceDocs.length ? (totalChunks / sourceDocs.length).toFixed(1) : '0')} />
        <KSt label={t('kb.stat.hitsToday')} value={totalHits} sub={t('kb.stat.hitsToday.sub')} />
        <KSt label={t('kb.stat.topDoc')}    value={topDoc?.id || '—'} sub={t('kb.stat.topDoc.sub')} />
      </div>

      <Panel>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--line-1)', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input className="input" style={{ maxWidth: 280 }} placeholder={t('kb.searchPh')} value={q} onChange={e => setQ(e.target.value)} />
          <div style={{ display: 'flex', gap: 6 }}>
            {tags.map(tg => (
              <span key={tg} className={`filter-pill ${tag === tg ? 'on' : ''}`} onClick={() => setTag(tg)}>{tg === 'all' ? t('flt.all') : tg}</span>
            ))}
          </div>
          <span className="muted" style={{ marginLeft: 'auto', fontSize: 11 }}>{t('kb.sortBy')}</span>
        </div>
        {docs.length === 0 ? (
          <Empty>{t('tasks.noMatch')}</Empty>
        ) : (
        <table className="k-table">
          <thead>
            <tr>
              <th>doc_id</th>
              <th>{t('c.title')}</th>
              <th>{t('c.tags')}</th>
              <th style={{ textAlign: 'right' }}>{t('c.chunks')}</th>
              <th style={{ textAlign: 'right' }}>{t('c.hits')}</th>
              <th>{t('c.lastHit')}</th>
              <th>{t('c.updated')}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {docs.map(d => (
              <tr key={`${d.id}|${d.sourcePath}`} onClick={() => onNav(`knowledge/${d.docKey || d.id}`)} style={{ cursor: 'pointer' }}>
                <td className="mono"><span className="bright">{d.id}</span></td>
                <td>
                  <div className="bright">{d.title}</div>
                  <div className="muted" style={{ fontSize: 10.5, marginTop: 2 }}>{d.sourcePath}</div>
                </td>
                <td>
                  <div className="tag-row">
                    {(d.tags || []).map(tg => <span key={tg} className="chip ghost" style={{ fontSize: 9.5, padding: '0 6px' }}>{tg}</span>)}
                  </div>
                </td>
                <td style={{ textAlign: 'right' }} className="mono">{d.chunkCount}</td>
                <td style={{ textAlign: 'right' }}>
                  <span className="mono" style={{ color: d.hitCount > 30 ? 'var(--accent)' : d.hitCount > 10 ? 'var(--amber)' : 'var(--fg-2)' }}>
                    {d.hitCount}
                  </span>
                </td>
                <td className="muted">{relTime(d.lastHitAt)}</td>
                <td className="muted">{relTime(d.updatedAt)}</td>
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

function KSt({ label, value, sub }) {
  return (
    <div className="kpi">
      <div className="lbl">{label}</div>
      <div className="val">{value}</div>
      <div className="delta muted">{sub}</div>
    </div>
  );
}

function KnowledgeDetail({ docId, onNav }) {
  const [doc, setDoc] = uK(null);
  const [tab, setTab] = uK('overview');

  uKE(() => {
    let done = false;
    if (window.IS_LIVE) {
      window.API.getKnowledgeDoc(docId).then(data => {
        if (!done && data && data.docKey) setDoc(data);
      });
    } else {
      setDoc(MOCK.KNOWLEDGE.find(d => d.id === docId) || MOCK.KNOWLEDGE[0]);
    }
    return () => { done = true; };
  }, [docId]);

  const liveFallbackDoc = {
    id: docId || 'knowledge',
    docKey: docId,
    title: docId || 'knowledge',
    sourcePath: '—',
    type: 'markdown',
    chunkCount: 0,
    hitCount: 0,
    lastHitAt: null,
    updatedAt: null,
    summary: '',
    preview: '',
    chunks: [],
    hitHistory: [],
    relatedRuns: [],
    citedBy: [],
    heatmap: Array(24).fill(0),
    tags: [],
  };
  const resolvedDoc = window.IS_LIVE
    ? (doc || liveFallbackDoc)
    : (doc || MOCK.KNOWLEDGE.find(d => d.id === docId) || MOCK.KNOWLEDGE[0]);
  const hitHistory = resolvedDoc.hitHistory || [];
  const relatedRuns = resolvedDoc.relatedRuns || [];
  const citedBy = resolvedDoc.citedBy || [];
  const previewText = resolvedDoc.preview || resolvedDoc.content || '';
  const heatmap = Array.isArray(resolvedDoc.heatmap) ? resolvedDoc.heatmap : [];
  const chunkHits = hitHistory.reduce((acc, h) => {
    const key = h.chunkId || '';
    if (key) acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const chunks = (resolvedDoc.chunks || MOCK.CHUNKS_002).map(c => ({
    ...c,
    hits: chunkHits[c.id] || c.hits || 0,
  }));

  uKE(() => {
    window.dispatchEvent(new CustomEvent('fh:route-label', {
      detail: { label: resolvedDoc.title || resolvedDoc.id || docId || 'knowledge' }
    }));
  }, [resolvedDoc.title, resolvedDoc.id, docId]);

  return (
    <div className="page">
      <div className="page-h">
        <div>
          <div className="t row gap-12" style={{ alignItems: 'center' }}>
            <span className="dim" style={{ cursor: 'pointer', fontSize: 13 }} onClick={() => onNav('knowledge')}>{t('kb.back')}</span>
            <span>{resolvedDoc.title}</span>
          </div>
          <div className="sub mono">{resolvedDoc.id} · {resolvedDoc.sourcePath}</div>
        </div>
        <div className="row">
          <button className="btn ghost">{t('c.reindex')}</button>
          <button className="btn ghost">{t('c.download')}</button>
          <button className="btn">{t('c.openFile')}</button>
        </div>
      </div>

      <div className="kb-detail-grid">
        <Panel>
          <div className="tabs">
            {[
              ['overview', t('kb.tab.overview')],
              ['chunks',   t('kb.tab.chunks', resolvedDoc.chunkCount || 0)],
              ['hits',     t('kb.tab.hits')],
              ['runs',     t('kb.tab.runs')],
            ].map(([k, l]) => (
              <div key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{l}</div>
            ))}
          </div>
          {tab === 'overview' && (
            <div style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <div className="muted" style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', marginBottom: 6 }}>{t('c.summary')}</div>
                <div style={{ fontSize: 12.5, color: 'var(--fg-1)', lineHeight: 1.6 }}>{resolvedDoc.summary || '—'}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', marginBottom: 6 }}>{t('c.preview')}</div>
                <pre className="code-block" style={{ maxHeight: 320 }}>{previewText || '—'}</pre>
              </div>
              <div className="row gap-12" style={{ flexWrap: 'wrap' }}>
                {(resolvedDoc.tags || []).map(tg => <span key={tg} className="chip ghost">{tg}</span>)}
              </div>
            </div>
          )}
          {tab === 'chunks' && (
            <div>
              {chunks.length === 0 && <Empty>{t('tasks.noMatch')}</Empty>}
              {chunks.map(c => (
                <div key={c.id} className="chunk-row">
                  <div className="h">
                    <span className="mono">{c.id}</span>
                    <span>{t('kb.col.idx', c.idx)}</span>
                    <span style={{ marginLeft: 'auto' }} className={c.hits > 4 ? 'green' : 'muted'}>{t('kb.col.hits', c.hits)}</span>
                  </div>
                  <div className="body">{c.text}</div>
                </div>
              ))}
            </div>
          )}
          {tab === 'hits' && (
            <table className="k-table">
              <thead><tr><th>{t('c.time')}</th><th>{t('tr.dr.run')}</th><th>chunk</th><th style={{ textAlign: 'right' }}>score</th></tr></thead>
              <tbody>
                {hitHistory.length === 0 && (
                  <tr><td colSpan="4"><Empty>{t('tasks.noMatch')}</Empty></td></tr>
                )}
                {hitHistory.map((h, i) => (
                  <tr key={i}>
                    <td className="muted mono">{h.t ? fmt.hh(h.t) : '—'}</td>
                    <td className="bright mono">{h.runId || '—'}</td>
                    <td>{h.chunkId || '—'}</td>
                    <td style={{ textAlign: 'right' }} className="mono muted">{h.score != null ? Number(h.score).toFixed(2) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {tab === 'runs' && (
            <table className="k-table">
              <thead><tr><th>{t('tr.dr.run')}</th><th>{t('c.task')}</th><th>{t('kb.col.runUsed')}</th><th>{t('c.status')}</th></tr></thead>
              <tbody>
                {relatedRuns.length === 0 && (
                  <tr><td colSpan="4"><Empty>{t('tasks.noMatch')}</Empty></td></tr>
                )}
                {relatedRuns.map((r, i) => (
                  <tr key={i}>
                    <td className="bright mono">{r.runId || '—'}</td>
                    <td className="muted">{r.taskTitle || r.taskId || '—'}</td>
                    <td>{r.usedFor || '—'}</td>
                    <td><StatusBadge status={r.status || 'stopped'} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <div className="col gap-8">
          <Panel title={t('kb.metadata')}>
            <div style={{ padding: '12px 14px' }} className="kv-list">
              <div className="kv-row"><span className="k">doc_id</span><span className="v mono">{resolvedDoc.id}</span></div>
              <div className="kv-row"><span className="k">{t('c.path')}</span><span className="v mono" style={{ fontSize: 11 }}>{resolvedDoc.sourcePath}</span></div>
              <div className="kv-row"><span className="k">{t('c.type')}</span><span className="v">{resolvedDoc.type}</span></div>
              <div className="kv-row"><span className="k">{t('c.chunks')}</span><span className="v">{resolvedDoc.chunkCount}</span></div>
              <div className="kv-row"><span className="k">{t('c.hits')}</span><span className="v green">{resolvedDoc.hitCount}</span></div>
              <div className="kv-row"><span className="k">{t('c.lastHit')}</span><span className="v">{relTime(resolvedDoc.lastHitAt)}</span></div>
              <div className="kv-row"><span className="k">{t('c.updated')}</span><span className="v">{relTime(resolvedDoc.updatedAt)}</span></div>
            </div>
          </Panel>
          <Panel title={t('kb.heatmap')} accent={t('c.last24h')}>
            <div style={{ padding: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(24, 1fr)', gap: 2 }}>
                {Array.from({ length: 24 }).map((_, i) => {
                  const v = Number(heatmap[i] || 0);
                  const capped = Math.max(0, Math.min(8, v));
                  const op = 0.08 + capped * 0.11;
                  return <div key={i} style={{
                    aspectRatio: '1',
                    background: `rgba(199,125,255,${op})`,
                    border: '1px solid var(--line-1)',
                    borderRadius: 2,
                  }} title={`${i}:00 · ${v} hits`}></div>;
                })}
              </div>
              <div className="row" style={{ marginTop: 8, justifyContent: 'space-between', fontSize: 9.5, color: 'var(--fg-3)' }}>
                <span>00</span><span>06</span><span>12</span><span>18</span><span>now</span>
              </div>
            </div>
          </Panel>
          <Panel title={t('kb.cited')}>
            <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
              {citedBy.length === 0 && <Empty>{t('tasks.noMatch')}</Empty>}
              {citedBy.map((c, i) => (
                <div key={i} className="row gap-8">
                  <span className="magenta">◈</span>
                  <span className="bright flex1">{c.name || c.strategy || '—'}</span>
                  <span className="dim mono">{c.count || 0} {t('kb.cites')}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

window.KnowledgePage = KnowledgePage;
