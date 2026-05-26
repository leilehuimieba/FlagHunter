/* global React, ReactDOM, Sidebar, Topbar, DashboardPage, TasksPage, TracesPage, KnowledgePage, LogsPage, SettingsPage */

const { useState: uA, useEffect: uAE } = React;

function App() {
  window.useLang();

  const [route, setRoute] = uA(() => {
    const h = window.location.hash.replace(/^#\/?/, '') || 'dashboard';
    return h;
  });

  uAE(() => {
    const handler = () => {
      const h = window.location.hash.replace(/^#\/?/, '') || 'dashboard';
      setRoute(h);
    };
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
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
        {route === 'logs' && <LogsPage />}
        {route === 'settings' && <SettingsPage />}
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
