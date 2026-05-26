/* global React, ReactDOM, Sidebar, Topbar, DashboardPage, TasksPage, TracesPage, KnowledgePage, LogsPage, SettingsPage, MemoryPage, CommandPalette */

const { useState: uA, useEffect: uAE } = React;

function App() {
  window.useLang();

  const [route, setRoute] = uA(() => {
    const h = window.location.hash.replace(/^#\/?/, '') || 'dashboard';
    return h;
  });

  const [showCP, setShowCP] = uA(false);

  // Global SSE subscription — ensures the event stream is always open
  // so all pages (dashboard, traces, knowledge, etc.) receive real-time events.
  // Each page can also add its own subscribeEvents() for page-specific handling.
  uAE(() => {
    if (!window.API) return;
    return window.API.subscribeEvents(ev => {
      // Route task_status events to a global event so any page can react
      window.dispatchEvent(new CustomEvent('fh:event', { detail: ev }));
    });
  }, []);

  uAE(() => {
    const handler = () => {
      const h = window.location.hash.replace(/^#\/?/, '') || 'dashboard';
      setRoute(h);
    };
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, []);

  // Global ⌘K / Ctrl+K
  uAE(() => {
    function onKey(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setShowCP(s => !s);
      }
      if (e.key === 'Escape') setShowCP(false);
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  // fh:toggle-cp event (from topbar ⌘ button)
  uAE(() => {
    const handler = () => setShowCP(s => !s);
    window.addEventListener('fh:toggle-cp', handler);
    return () => window.removeEventListener('fh:toggle-cp', handler);
  }, []);

  function nav(to) {
    window.location.hash = '#/' + to;
  }

  const crumbRoute = (() => {
    if (route.startsWith('traces/')) return 'traces/detail';
    if (route.startsWith('knowledge/')) return 'knowledge/detail';
    return route;
  })();

  return (
    <div className="shell">
      <Sidebar route={route.split('/')[0]} onNav={nav} />
      <Topbar route={crumbRoute} />
      <div className="main">
        {route === 'dashboard' && <DashboardPage onNav={nav} />}
        {route === 'tasks' && <TasksPage onNav={nav} />}
        {route.startsWith('traces') && (
          <TracesPage runId={route.split('/')[1]} onNav={nav} />
        )}
        {route.startsWith('knowledge') && (
          <KnowledgePage docId={route.split('/')[1]} onNav={nav} />
        )}
        {route === 'memory' && <MemoryPage />}
        {route === 'logs' && <LogsPage />}
        {route === 'settings' && <SettingsPage />}
      </div>
      {showCP && <CommandPalette onClose={() => setShowCP(false)} onNav={nav} />}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
