/* global React, MOCK, fmt, t */
// ============================================================
// Knowledge — list + detail
// ============================================================

const { useState: uK, useEffect: uKE, useMemo: uKM } = React;

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

  const sourceDocs = apiDocs || MOCK.KNOWLEDGE;
  const docs = uKM(() => sourceDocs.filter(d =>
    (!q || d.title.toLowerCase().includes(q.toLowerCase()) || d.sourcePath.includes(q))
    && (tag === 'all' || (d.tags || []).includes(tag))
  ), [q, tag, sourceDocs]);

  const totalHits = sourceDocs.reduce((s, d) => s + (d.hitCount || 0), 0);
  const totalChunks = sourceDocs.reduce((s, d) => s + (d.chunkCount || 0), 0);

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
        <KSt label={t('kb.stat.topDoc')}    value="doc_002" sub={t('kb.stat.topDoc.sub')} />
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
              <tr key={d.id} onClick={() => onNav(`knowledge/${d.id}`)} style={{ cursor: 'pointer' }}>
                <td className="mono"><span className="bright">{d.id}</span></td>
                <td>
                  <div className="bright">{d.title}</div>
                  <div className="muted" style={{ fontSize: 10.5, marginTop: 2 }}>{d.sourcePath}</div>
                </td>
                <td>
                  <div className="tag-row">
                    {d.tags.map(tg => <span key={tg} className="chip ghost" style={{ fontSize: 9.5, padding: '0 6px' }}>{tg}</span>)}
                  </div>
                </td>
                <td style={{ textAlign: 'right' }} className="mono">{d.chunkCount}</td>
                <td style={{ textAlign: 'right' }}>
                  <span className="mono" style={{ color: d.hitCount > 30 ? 'var(--accent)' : d.hitCount > 10 ? 'var(--amber)' : 'var(--fg-2)' }}>
                    {d.hitCount}
                  </span>
                </td>
                <td className="muted">{fmt.since(d.lastHitAt)}</td>
                <td className="muted">{fmt.since(d.updatedAt)}</td>
                <td className="dim" style={{ textAlign: 'right' }}>›</td>
              </tr>
            ))}
          </tbody>
        </table>
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
  const doc = MOCK.KNOWLEDGE.find(d => d.id === docId) || MOCK.KNOWLEDGE[0];
  const [tab, setTab] = uK('overview');
  return (
    <div className="page">
      <div className="page-h">
        <div>
          <div className="t row gap-12" style={{ alignItems: 'center' }}>
            <span className="dim" style={{ cursor: 'pointer', fontSize: 13 }} onClick={() => onNav('knowledge')}>{t('kb.back')}</span>
            <span>{doc.title}</span>
          </div>
          <div className="sub mono">{doc.id} · {doc.sourcePath}</div>
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
              ['chunks',   t('kb.tab.chunks', doc.chunkCount)],
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
                <div style={{ fontSize: 12.5, color: 'var(--fg-1)', lineHeight: 1.6 }}>{doc.summary}</div>
              </div>
              <div>
                <div className="muted" style={{ fontSize: 10, letterSpacing: '0.16em', textTransform: 'uppercase', marginBottom: 6 }}>{t('c.preview')}</div>
                <pre className="code-block" style={{ maxHeight: 320 }}>{`# ${doc.title}\n\n${doc.summary}\n\n## When this fires\n\nThe RAG layer surfaces this doc whenever the agent encounters one of:\n- a JSON request body with quote-injectable fields\n- an unexpected response-size delta on probe payloads\n- an upstream that exposes pg_sleep timing\n\n## Working recipe\n\n1. Identify the field hosting the injection (often \`username\` or \`email\`).\n2. Detect dialect via a 5-second timing payload.\n3. Switch sqlmap technique to T with --dbms=postgresql.\n4. Avoid level>=3 unless the surface is rate-limit friendly.\n5. Verify any candidate flag against the project's flag-format spec.\n\n## Gotchas\n\n- Sequelize/Knex swallow exceptions silently — quote-close anomalies will not appear in stderr.\n- Cloudflare in front of the target will mask timing windows below ~2.5s.\n`}</pre>
              </div>
              <div className="row gap-12" style={{ flexWrap: 'wrap' }}>
                {doc.tags.map(tg => <span key={tg} className="chip ghost">{tg}</span>)}
              </div>
            </div>
          )}
          {tab === 'chunks' && (
            <div>
              {MOCK.CHUNKS_002.map(c => (
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
                {[
                  ['10:30:12', 'run_002', 'chunk_002', 0.79],
                  ['10:30:00', 'run_002', 'chunk_003', 0.72],
                  ['10:29:46', 'run_002', 'chunk_001', 0.81],
                  ['09:55:18', 'run_006', 'chunk_001', 0.66],
                  ['09:32:04', 'run_006', 'chunk_002', 0.71],
                ].map(([ts, rn, ch, sc], i) => (
                  <tr key={i}><td className="muted mono">{ts}</td><td className="bright mono">{rn}</td><td>{ch}</td><td style={{ textAlign: 'right' }} className={sc > 0.75 ? 'green mono' : 'mono muted'}>{sc.toFixed(2)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {tab === 'runs' && (
            <table className="k-table">
              <thead><tr><th>{t('tr.dr.run')}</th><th>{t('c.task')}</th><th>{t('kb.col.runUsed')}</th><th>{t('c.status')}</th></tr></thead>
              <tbody>
                <tr><td className="bright mono">run_002</td><td className="muted">sqli probe</td><td>strategy timing_based_blind</td><td><StatusBadge status="running" /></td></tr>
                <tr><td className="bright mono">run_006</td><td className="muted">stored XSS</td><td>exploit · cookie exfil</td><td><StatusBadge status="success" /></td></tr>
                <tr><td className="bright mono">run_003</td><td className="muted">JWT alg=none</td><td>recon · header probe</td><td><StatusBadge status="failed" /></td></tr>
              </tbody>
            </table>
          )}
        </Panel>

        <div className="col gap-8">
          <Panel title={t('kb.metadata')}>
            <div style={{ padding: '12px 14px' }} className="kv-list">
              <div className="kv-row"><span className="k">doc_id</span><span className="v mono">{doc.id}</span></div>
              <div className="kv-row"><span className="k">{t('c.path')}</span><span className="v mono" style={{ fontSize: 11 }}>{doc.sourcePath}</span></div>
              <div className="kv-row"><span className="k">{t('c.type')}</span><span className="v">{doc.type}</span></div>
              <div className="kv-row"><span className="k">{t('c.chunks')}</span><span className="v">{doc.chunkCount}</span></div>
              <div className="kv-row"><span className="k">{t('c.hits')}</span><span className="v green">{doc.hitCount}</span></div>
              <div className="kv-row"><span className="k">{t('c.lastHit')}</span><span className="v">{fmt.since(doc.lastHitAt)}</span></div>
              <div className="kv-row"><span className="k">{t('c.updated')}</span><span className="v">{fmt.since(doc.updatedAt)}</span></div>
            </div>
          </Panel>
          <Panel title={t('kb.heatmap')} accent={t('c.last24h')}>
            <div style={{ padding: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(24, 1fr)', gap: 2 }}>
                {Array.from({ length: 24 }).map((_, i) => {
                  const v = Math.max(0, Math.min(8, Math.round(Math.sin(i / 24 * Math.PI * 2 + 1) * 3 + 3 + (i === 10 ? 5 : 0))));
                  const op = 0.08 + v * 0.11;
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
              <div className="row gap-8"><span className="magenta">◈</span><span className="bright flex1">sql_injection_probe</span><span className="dim mono">12 {t('kb.cites')}</span></div>
              <div className="row gap-8"><span className="magenta">◈</span><span className="bright flex1">timing_based_blind</span><span className="dim mono">9 {t('kb.cites')}</span></div>
              <div className="row gap-8"><span className="magenta">◈</span><span className="bright flex1">union_exfil</span><span className="dim mono">4 {t('kb.cites')}</span></div>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}

window.KnowledgePage = KnowledgePage;
