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

// ── Graph view ─────────────────────────────────────────────────
const TYPE_COLORS = {
  web: '#4fc3f7', sqli: '#ffb74d', xss: '#ce93d8',
  jwt: '#4db6ac', crypto: '#ef5350', reverse: '#f06292',
  pwn: '#ba68c8', misc: '#90a4ae', forensics: '#a1887f',
};

function MemoryGraphView({ filter, onSelect, selected }) {
  const canvasRef = React.useRef(null);
  const [graphData, setGraphData] = React.useState({ nodes: [], edges: [] });
  const [tooltip, setTooltip] = React.useState(null);

  // View state — 'clusters' | 'detail'. Cluster mode is default.
  const [mode, setMode] = React.useState('clusters');
  const [clusterType, setClusterType] = React.useState(null);

  // Zoom/pan for detail mode
  const [viewTransform, setViewTransform] = React.useState({ zoom: 1, px: 0, py: 0 });

  // Noise filter: hide nodes with appliedCount=0
  const [showNoise, setShowNoise] = React.useState(false);

  const dragRef = React.useRef(null);     // { kind: 'node', node, offsetX, offsetY } | { kind: 'pan', sx, sy, startPx, startPy }
  const nodesRef = React.useRef([]);
  const rafRef = React.useRef(null);
  const modeRef = React.useRef('clusters');       // keep sync for rAF closure
  const clusterTypeRef = React.useRef(null);
  const viewRef = React.useRef({ zoom: 1, px: 0, py: 0 });

  // Computed clusters from full graph data
  const clusters = React.useMemo(() => {
    const map = {};
    graphData.nodes.forEach(n => {
      const t = n.type || 'misc';
      if (!map[t]) map[t] = { type: t, color: TYPE_COLORS[t] || '#90a4ae', nodes: [], totalApplied: 0, solvedCount: 0 };
      map[t].nodes.push(n);
      map[t].totalApplied += n.appliedCount || 0;
      if (n.solved) map[t].solvedCount++;
    });
    return Object.values(map).sort((a, b) => b.nodes.length - a.nodes.length);
  }, [graphData.nodes]);

  // Active clusters (filtered by showNoise)
  const visibleClusters = React.useMemo(() => {
    if (showNoise) return clusters;
    return clusters.map(c => ({
      ...c,
      nodes: c.nodes.filter(n => (n.appliedCount || 0) > 0),
    })).filter(c => c.nodes.length > 0);
  }, [clusters, showNoise]);

  // ── Data loading ────────────────────────────────────────────
  React.useEffect(() => {
    window.API.getMemoryGraph({ status: filter === 'all' ? null : filter }).then(data => {
      if (data && data.nodes) {
        setGraphData({ nodes: data.nodes, edges: data.edges || [] });
        // Reset to cluster view on new data
        setMode('clusters');
        setClusterType(null);
      }
    });
  }, [filter]);

  // ── Force simulation (detail mode only) ─────────────────────
  React.useEffect(() => {
    if (mode !== 'detail' || !clusterType) return;
    const allNodes = graphData.nodes;
    const filtered = showNoise
      ? allNodes.filter(n => n.type === clusterType)
      : allNodes.filter(n => n.type === clusterType && (n.appliedCount || 0) > 0);

    if (filtered.length === 0) return;

    const w = canvasRef.current ? canvasRef.current.clientWidth : 800;
    const h = canvasRef.current ? canvasRef.current.clientHeight : 600;
    const cx = w / 2, cy = h / 2, r = Math.min(w, h) * 0.35;

    const nodes = filtered.map((n, i) => ({
      ...n,
      x: cx + r * Math.cos((2 * Math.PI * i) / Math.max(filtered.length, 1)),
      y: cy + r * Math.sin((2 * Math.PI * i) / Math.max(filtered.length, 1)),
      vx: 0, vy: 0,
    }));
    nodesRef.current = nodes;

    // Build edge lookup (only edges where both ends are in filtered set)
    const nodeIds = new Set(nodes.map(n => n.id));
    const edges = graphData.edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
    const edgeMap = {};
    edges.forEach(e => {
      if (!edgeMap[e.source]) edgeMap[e.source] = new Set();
      if (!edgeMap[e.target]) edgeMap[e.target] = new Set();
      edgeMap[e.source].add(e.target);
      edgeMap[e.target].add(e.source);
    });

    // Build neighbor set for selected node
    const neighSet = selected ? new Set(edgeMap[selected] || []) : null;

    const REPULSION = 6000;
    const ATTRACTION = 0.004;
    const DAMPING = 0.82;
    const CENTER_FORCE = 0.008;

    function step() {
      const cw = canvasRef.current ? canvasRef.current.clientWidth : 800;
      const ch = canvasRef.current ? canvasRef.current.clientHeight : 600;
      // Repulsion
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[j].x - nodes[i].x;
          const dy = nodes[j].y - nodes[i].y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = REPULSION / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          nodes[i].vx -= fx; nodes[i].vy -= fy;
          nodes[j].vx += fx; nodes[j].vy += fy;
        }
      }
      // Attraction
      edges.forEach(e => {
        const src = nodes.find(n => n.id === e.source);
        const tgt = nodes.find(n => n.id === e.target);
        if (!src || !tgt) return;
        const dx = tgt.x - src.x;
        const dy = tgt.y - src.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = dist * ATTRACTION * (e.weight || 1);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        src.vx += fx; src.vy += fy;
        tgt.vx -= fx; tgt.vy -= fy;
      });
      // Center gravity + damping
      const dragNode = dragRef.current && dragRef.current.kind === 'node' ? dragRef.current.node : null;
      nodes.forEach(n => {
        if (n === dragNode) return;
        n.vx += (cw / 2 - n.x) * CENTER_FORCE;
        n.vy += (ch / 2 - n.y) * CENTER_FORCE;
        n.vx *= DAMPING; n.vy *= DAMPING;
        n.x += n.vx; n.y += n.vy;
      });
      drawDetail(nodes, edges, edgeMap, neighSet);
      rafRef.current = requestAnimationFrame(step);
    }
    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [mode, clusterType, graphData, selected, showNoise]);

  // ── Sync refs for rAF closure ───────────────────────────────
  React.useEffect(() => { modeRef.current = mode; }, [mode]);
  React.useEffect(() => { clusterTypeRef.current = clusterType; }, [clusterType]);
  React.useEffect(() => { viewRef.current = { zoom: viewTransform.zoom, px: viewTransform.px, py: viewTransform.py }; }, [viewTransform]);

  // ── Drawing: cluster mode ────────────────────────────────────
  function drawClusters() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width = canvas.clientWidth;
    const h = canvas.height = canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2, cy = h / 2;
    const count = visibleClusters.length;
    if (count === 0) return;

    const baseR = Math.min(w, h) * 0.18;
    const orbitR = Math.min(w, h) * 0.28;

    visibleClusters.forEach((c, i) => {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2;
      const ox = cx + orbitR * Math.cos(angle);
      const oy = cy + orbitR * Math.sin(angle);
      const size = Math.sqrt(c.nodes.length) * 3;
      const r = Math.max(baseR * 0.5, Math.min(size, baseR * 1.6));

      // Bubble glow
      const grad = ctx.createRadialGradient(ox - r * 0.2, oy - r * 0.2, r * 0.1, ox, oy, r);
      grad.addColorStop(0, c.color + 'cc');
      grad.addColorStop(0.7, c.color + '44');
      grad.addColorStop(1, c.color + '10');
      ctx.beginPath();
      ctx.arc(ox, oy, r + 8, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      // Bubble circle
      ctx.beginPath();
      ctx.arc(ox, oy, r, 0, Math.PI * 2);
      ctx.fillStyle = c.color + '55';
      ctx.fill();
      ctx.strokeStyle = c.color + 'aa';
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Type label
      ctx.fillStyle = '#fff';
      ctx.font = `bold ${Math.max(11, r * 0.35)}px "JetBrains Mono", monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(c.type.toUpperCase(), ox, oy - 6);

      // Node count
      ctx.font = `${Math.max(10, r * 0.25)}px "JetBrains Mono", monospace`;
      ctx.fillStyle = c.color + 'cc';
      ctx.fillText(c.nodes.length + ' nodes', ox, oy + r * 0.3 + 4);

      // Bar beneath type: solved / total
      if (c.solvedCount > 0) {
        const bw = r * 1.2, bh = 4, bx = ox - bw / 2, by = oy + r * 0.48;
        ctx.fillStyle = 'rgba(255,255,255,0.15)';
        ctx.fillRect(bx, by, bw, bh);
        ctx.fillStyle = c.color;
        ctx.fillRect(bx, by, bw * (c.solvedCount / c.nodes.length), bh);
      }
    });
  }

  // ── Drawing: detail mode ─────────────────────────────────────
  function drawDetail(nodes, edges, edgeMap, neighSet) {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width = canvas.clientWidth;
    const h = canvas.height = canvas.clientHeight;
    const { zoom, px, py } = viewRef.current;

    ctx.clearRect(0, 0, w, h);
    ctx.save();
    ctx.translate(px, py);
    ctx.scale(zoom, zoom);

    // Edges
    edges.forEach(e => {
      const src = nodes.find(n => n.id === e.source);
      const tgt = nodes.find(n => n.id === e.target);
      if (!src || !tgt) return;
      const highlight = neighSet && (neighSet.has(e.source) || neighSet.has(e.target));
      ctx.beginPath();
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.strokeStyle = highlight
        ? 'rgba(107, 230, 117, 0.35)'
        : 'rgba(107, 230, 117, 0.06)';
      ctx.lineWidth = highlight ? Math.min((e.weight || 1) * 1.5, 3) : Math.min(e.weight || 1, 2);
      ctx.stroke();
    });

    // Nodes
    nodes.forEach(n => {
      const r = 3 + Math.sqrt(Math.max(n.appliedCount || 0, 1)) * 2;
      const isSel = n.id === selected;
      const isNeighbor = neighSet && neighSet.has(n.id);
      const dimmed = neighSet && !isSel && !isNeighbor;

      ctx.beginPath();
      ctx.arc(n.x, n.y, isSel ? r + 3 : r, 0, Math.PI * 2);
      ctx.fillStyle = n.color || '#90a4ae';
      ctx.globalAlpha = n.status === 'muted' ? 0.2 : dimmed ? 0.15 : 0.85;
      ctx.fill();

      if (isSel) {
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2.5;
        ctx.stroke();
        // Pulse ring
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 8, 0, Math.PI * 2);
        ctx.strokeStyle = n.color + '66';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    });

    ctx.restore();
  }

  // ── Hit tests ────────────────────────────────────────────────
  function screenToWorld(sx, sy) {
    const { zoom, px, py } = viewRef.current;
    return { x: (sx - px) / zoom, y: (sy - py) / zoom };
  }

  function getClusterAt(sx, sy) {
    const canvas = canvasRef.current;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    const cx = w / 2, cy = h / 2;
    const count = visibleClusters.length;
    if (count === 0) return null;
    const baseR = Math.min(w, h) * 0.18;
    const orbitR = Math.min(w, h) * 0.28;

    for (let i = 0; i < count; i++) {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2;
      const ox = cx + orbitR * Math.cos(angle);
      const oy = cy + orbitR * Math.sin(angle);
      const size = Math.sqrt(visibleClusters[i].nodes.length) * 3;
      const r = Math.max(baseR * 0.5, Math.min(size, baseR * 1.6));
      const dx = sx - ox, dy = sy - oy;
      if (dx * dx + dy * dy < (r + 8) * (r + 8)) return visibleClusters[i];
    }
    return null;
  }

  function getNodeAt(sx, sy) {
    const nodes = nodesRef.current;
    const w = canvasRef.current ? canvasRef.current.clientWidth : 800;
    const h = canvasRef.current ? canvasRef.current.clientHeight : 600;
    const { zoom, px, py } = viewRef.current;

    // In cluster mode or with no transform, use screen coords directly
    // In detail mode with zoom/pan, use world coords
    const useWorld = modeRef.current === 'detail' && (zoom !== 1 || px !== 0 || py !== 0);
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      const nx = useWorld ? n.x * zoom + px : n.x;
      const ny = useWorld ? n.y * zoom + py : n.y;
      const nr = (useWorld ? (3 + Math.sqrt(Math.max(n.appliedCount || 0, 1)) * 2) * zoom : (3 + Math.sqrt(Math.max(n.appliedCount || 0, 1)) * 2)) + 5;
      const dx = nx - sx, dy = ny - sy;
      if (dx * dx + dy * dy < nr * nr) return n;
    }
    return null;
  }

  // ── Mouse events ─────────────────────────────────────────────
  function handleMouseMove(e) {
    const rect = canvasRef.current.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    if (dragRef.current) {
      if (dragRef.current.kind === 'node') {
        const w = screenToWorld(sx, sy);
        dragRef.current.node.x = w.x + dragRef.current.offsetX;
        dragRef.current.node.y = w.y + dragRef.current.offsetY;
        return;
      }
      if (dragRef.current.kind === 'pan') {
        const d = dragRef.current;
        setViewTransform(prev => ({ ...prev, px: d.startPx + (sx - d.sx), py: d.startPy + (sy - d.sy) }));
        return;
      }
    }

    if (modeRef.current === 'clusters') {
      const c = getClusterAt(sx, sy);
      setTooltip(c ? { x: e.clientX - rect.left, y: e.clientY - rect.top, cluster: c } : null);
    } else {
      const node = getNodeAt(sx, sy);
      setTooltip(node ? { x: e.clientX - rect.left, y: e.clientY - rect.top, node } : null);
    }
  }

  function handleMouseDown(e) {
    const rect = canvasRef.current.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    if (modeRef.current === 'clusters') {
      const c = getClusterAt(sx, sy);
      if (c) {
        setClusterType(c.type);
        setMode('detail');
        setViewTransform({ zoom: 1, px: 0, py: 0 });
        return;
      }
      return;
    }

    // Detail mode
    const node = getNodeAt(sx, sy);
    if (node) {
      const w = screenToWorld(sx, sy);
      dragRef.current = { kind: 'node', node, offsetX: node.x - w.x, offsetY: node.y - w.y };
    } else {
      // Pan
      dragRef.current = { kind: 'pan', sx, sy, startPx: viewRef.current.px, startPy: viewRef.current.py };
      e.preventDefault();
    }
  }

  function handleMouseUp(e) {
    if (dragRef.current && dragRef.current.kind === 'node') {
      const rect = canvasRef.current.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      const node = getNodeAt(sx, sy);
      if (node === dragRef.current.node) onSelect(node.id);
    }
    dragRef.current = null;
  }

  // Wheel zoom — must use non-passive listener so we can preventDefault
  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    function onWheel(e) {
      if (modeRef.current !== 'detail') return;
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      setViewTransform(prev => {
        const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
        const newZoom = Math.max(0.2, Math.min(4, prev.zoom * factor));
        const newPx = mx - (mx - prev.px) * (newZoom / Math.max(prev.zoom, 0.01));
        const newPy = my - (my - prev.py) * (newZoom / Math.max(prev.zoom, 0.01));
        return { zoom: newZoom, px: newPx, py: newPy };
      });
    }
    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', onWheel);
  }, []);

  // ── Edge list helper ─────────────────────────────────────────
  function edgesForType(type) {
    if (!type) return [];
    const nodeIds = new Set(graphData.nodes.filter(n => n.type === type).map(n => n.id));
    return graphData.edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
  }

  // ── Empty check ──────────────────────────────────────────────
  if (graphData.nodes.length === 0) {
    return <div className="mem-empty">{t('mem.empty')}</div>;
  }

  // Active type chips for detail toolbar
  const nodeTypesForChips = [...new Set(graphData.nodes.map(n => n.type || 'misc'))].sort();

  return (
    <div style={{ position: 'relative', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      {/* ── Detail toolbar ──────────────────────────────────────── */}
      {mode === 'detail' && clusterType && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px',
          borderBottom: '1px solid var(--line-2)', flexWrap: 'wrap', flexShrink: 0,
        }}>
          <button
            className="mem-filter-pill on"
            onClick={() => { setMode('clusters'); setClusterType(null); setViewTransform({ zoom: 1, px: 0, py: 0 }); }}
          >← {t('mem.clusters') || 'Clusters'}</button>
          <span style={{ width: 1, height: 16, background: 'var(--line-2)', display: 'inline-block', alignSelf: 'center' }}></span>
          {nodeTypesForChips.map(nt => (
            <button
              key={nt}
              className={'mem-filter-pill' + (nt === clusterType ? ' on' : '')}
              style={{ borderColor: TYPE_COLORS[nt] || '#90a4ae' }}
              onClick={() => {
                setClusterType(nt);
                setViewTransform({ zoom: 1, px: 0, py: 0 });
                if (selected) onSelect(null);
              }}
            >{nt} ({graphData.nodes.filter(n => (n.type || 'misc') === nt).length})</button>
          ))}
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--fg-2)' }}>
            {nodesRef.current.length} nodes · {edgesForType(clusterType).length} edges
          </span>
          <button
            className={'mem-filter-pill' + (showNoise ? '' : ' on')}
            style={{ fontSize: 10 }}
            onClick={() => setShowNoise(v => !v)}
            title="Hide low-applied nodes"
          >{showNoise ? '◉ all' : '○ active'}</button>
        </div>
      )}

      {/* ── Canvas ──────────────────────────────────────────────── */}
      <canvas
        ref={canvasRef}
        style={{
          width: '100%', height: '100%', display: 'block', flex: 1, minHeight: 0,
          cursor: dragRef.current
            ? (dragRef.current.kind === 'pan' ? 'grabbing' : 'grabbing')
            : mode === 'clusters' ? 'pointer' : 'grab',
        }}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={() => { dragRef.current = null; setTooltip(null); }}
      />

      {/* ── Cluster-mode overlay (legend) ────────────────────────── */}
      {mode === 'clusters' && (
        <div style={{
          position: 'absolute', bottom: 12, left: 12,
          display: 'flex', gap: 10, flexWrap: 'wrap',
          background: 'var(--bg-overlay)', borderRadius: 8, padding: '6px 10px',
          fontSize: 10, color: 'var(--fg-2)',
        }}>
          {visibleClusters.map(c => (
            <span key={c.type} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: c.color, display: 'inline-block' }}></span>
              {c.type} ({c.nodes.length})
            </span>
          ))}
        </div>
      )}

      {/* ── Cluster tooltip ─────────────────────────────────────── */}
      {tooltip && tooltip.cluster && (
        <div style={{
          position: 'absolute', left: tooltip.x + 12, top: tooltip.y + 12,
          background: 'var(--bg-1)', border: '1px solid var(--line-1)',
          borderRadius: 6, padding: '8px 12px', fontSize: 11, color: 'var(--fg-0)',
          zIndex: 100, pointerEvents: 'none', maxWidth: 220,
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: tooltip.cluster.color }}>
            {tooltip.cluster.type.toUpperCase()}
          </div>
          <div>{tooltip.cluster.nodes.length} nodes</div>
          <div>{tooltip.cluster.solvedCount} solved</div>
          <div>avg applied: {tooltip.cluster.nodes.length ? Math.round(tooltip.cluster.totalApplied / tooltip.cluster.nodes.length) : 0}x</div>
        </div>
      )}

      {/* ── Node tooltip ────────────────────────────────────────── */}
      {tooltip && tooltip.node && (
        <div style={{
          position: 'absolute', left: tooltip.x + 12, top: tooltip.y + 12,
          background: 'var(--bg-1)', border: '1px solid var(--line-1)',
          borderRadius: 6, padding: '8px 12px', fontSize: 11, color: 'var(--fg-0)',
          zIndex: 100, pointerEvents: 'none', maxWidth: 240,
        }}>
          <div className="mono" style={{ fontSize: 10, color: 'var(--accent)' }}>{tooltip.node.id}</div>
          <div>type: <span style={{ color: tooltip.node.color }}>{tooltip.node.type}</span></div>
          <div>applied: {tooltip.node.appliedCount}x</div>
          <div>status: {tooltip.node.status}</div>
          {tooltip.node.solved && <div style={{ color: 'var(--accent)' }}>solved</div>}
        </div>
      )}

      {/* ── Cluster paint via rAF ────────────────────────────────── */}
      {mode === 'clusters' && (
        <ClusterRenderer canvasRef={canvasRef} drawFn={drawClusters} />
      )}
    </div>
  );
}

// Tiny helper: re-draw clusters on every frame (no physics, just static)
function ClusterRenderer({ canvasRef, drawFn }) {
  const drawRef = React.useRef(drawFn);
  drawRef.current = drawFn;
  React.useEffect(() => {
    let running = true;
    function tick() {
      if (!running) return;
      drawRef.current();
      if (running) rafRef.current = requestAnimationFrame(tick);
    }
    const rafRef = { current: requestAnimationFrame(tick) };
    return () => { running = false; cancelAnimationFrame(rafRef.current); };
  }, []);
  return null;
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
  const [viewMode, setViewMode] = useState('list');  // 'list' | 'graph'

  const loadData = useCallback(async () => {
    const [data, s] = await Promise.all([
      window.API.getMemory({ status: filter === 'all' ? null : filter, sort_by: sortBy }),
      window.API.getMemoryStats(),
    ]);
    if (Array.isArray(data)) {
      setEntries(data);
      setStats(s || computeStats(data));
      return;
    }
    setEntries([]);
    setStats(s || computeStats([]));
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
    try {
      const updated = await window.API.muteMemoryEntry(id);
      if (updated) {
        await loadData();
      }
    } finally {
      setBusy('');
    }
  }

  async function handleActivate(id) {
    setBusy(id);
    try {
      const updated = await window.API.activateMemoryEntry(id);
      if (updated) {
        await loadData();
      }
    } finally {
      setBusy('');
    }
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete memory entry ' + id + '?')) return;
    setBusy(id);
    try {
      const result = await window.API.deleteMemoryEntry(id);
      if (result && result.ok) {
        await loadData();
        if (selected === id) setSelected(null);
      }
    } finally {
      setBusy('');
    }
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
          {[
            { key: 'list', label: t('mem.listView') || 'List' },
            { key: 'graph', label: t('mem.graphView') || 'Graph' },
          ].map(v => (
            <button
              key={v.key}
              className={'mem-filter-pill' + (viewMode === v.key ? ' on' : '')}
              onClick={() => setViewMode(v.key)}
            >{v.label}</button>
          ))}
          <span style={{ width: 1, height: 16, background: 'var(--line-2)', margin: '0 4px', display: 'inline-block', alignSelf: 'center' }}></span>
          {FILTERS.map(f => (
            <button
              key={f.key}
              className={'mem-filter-pill' + (filter === f.key ? ' on' : '')}
              onClick={() => { setFilter(f.key); setSelected(null); }}
            >{f.label}</button>
          ))}
        </div>
        {viewMode === 'list' && (
          <select
            className="input mem-sort-sel"
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
          >
            <option value="recent">{t('mem.sortRecent')}</option>
            <option value="correlation">{t('mem.sortCorr')}</option>
            <option value="applied">{t('mem.sortApplied')}</option>
          </select>
        )}
        {viewMode === 'list' && (
          <input
            className="input mem-search"
            placeholder={t('mem.search')}
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        )}
      </div>

      {/* ── Content ───────────────────────────────────────────── */}
      <div className="mem-content">
        {viewMode === 'graph' ? (
          <MemoryGraphView filter={filter} onSelect={setSelected} selected={selected} />
        ) : (
          /* List */
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
        )}

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
