import { NavLink, Outlet } from 'react-router-dom';

const navItems = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/customers', label: 'Customers' },
  { to: '/projects', label: 'Projects' },
  { to: '/requirements', label: 'Requirements' },
  { to: '/issues', label: 'Issues' },
  { to: '/ai-copilot', label: 'AI Copilot' },
  { to: '/ai-evaluation', label: 'AI Evaluation' },
  { to: '/agent-runs', label: 'Agent Investigation' },
];

export function Layout() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <p className="brand">Delivery Copilot</p>
          <p className="subtitle">AI-powered enterprise delivery dashboard</p>
        </div>
        <nav className="nav">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
