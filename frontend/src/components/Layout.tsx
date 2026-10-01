import { AnimatePresence, motion } from 'framer-motion';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import type { Role } from '../api/types';

interface NavItem {
  to: string;
  label: string;
  icon: string;
  roles: Role[];
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: '📊', roles: ['hr', 'interviewer', 'ceo'] },
  { to: '/interviews', label: 'Interviews', icon: '🎙️', roles: ['hr', 'interviewer'] },
  { to: '/executive', label: 'Executive', icon: '👑', roles: ['hr', 'ceo'] },
];

const roleBadge: Record<Role, { label: string; className: string }> = {
  hr: { label: 'HR', className: 'bg-indigo-500/20 text-indigo-300 border-indigo-400/30' },
  interviewer: {
    label: 'Interviewer',
    className: 'bg-sky-500/20 text-sky-300 border-sky-400/30',
  },
  ceo: { label: 'CEO', className: 'bg-amber-500/20 text-amber-300 border-amber-400/30' },
};

function Sidebar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const items = NAV_ITEMS.filter((item) => user && item.roles.includes(user.role));
  const badge = user ? roleBadge[user.role] : null;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-white/10 bg-surface-950/90 backdrop-blur-xl">
      <div className="flex items-center gap-3 px-6 py-6">
        <motion.div
          initial={{ rotate: -10, scale: 0.8 }}
          animate={{ rotate: 0, scale: 1 }}
          transition={{ type: 'spring', stiffness: 200, damping: 15 }}
          className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 via-violet-500 to-fuchsia-500 text-xl shadow-glow"
        >
          ⚡
        </motion.div>
        <div>
          <div className="text-lg font-extrabold tracking-tight text-white">TalentFlow</div>
          <div className="text-[11px] font-medium uppercase tracking-[0.2em] text-slate-500">
            Hiring OS
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all duration-200 ${
                isActive
                  ? 'bg-gradient-to-r from-indigo-500/25 to-violet-500/15 text-white'
                  : 'text-slate-400 hover:bg-white/5 hover:text-white'
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <motion.span
                    layoutId="nav-active"
                    className="absolute left-0 top-1/2 h-8 w-1 -translate-y-1/2 rounded-r-full bg-gradient-to-b from-indigo-400 to-violet-500"
                  />
                )}
                <span className="text-lg">{item.icon}</span>
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-white/10 p-4">
        <div className="mb-3 flex items-center gap-3 rounded-xl bg-white/5 p-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-slate-600 to-slate-800 text-sm font-bold text-white">
            {user?.full_name?.charAt(0).toUpperCase() ?? '?'}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-white">{user?.full_name}</div>
            <div className="truncate text-xs text-slate-400">{user?.email}</div>
          </div>
        </div>
        {badge && (
          <div className="mb-3 flex justify-center">
            <span
              className={`rounded-full border px-3 py-0.5 text-[11px] font-bold uppercase tracking-widest ${badge.className}`}
            >
              {badge.label}
            </span>
          </div>
        )}
        <button
          onClick={handleLogout}
          className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-rose-500/15 hover:text-rose-300"
        >
          🚪 Sign out
        </button>
      </div>
    </aside>
  );
}

export function Layout() {
  return (
    <div className="min-h-screen bg-surface-950 text-slate-200">
      {/* Ambient background */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute -top-40 right-0 h-96 w-96 rounded-full bg-indigo-600/15 blur-[120px]" />
        <div className="absolute bottom-0 left-64 h-96 w-96 rounded-full bg-violet-600/10 blur-[120px]" />
      </div>
      <Sidebar />
      <main className="relative ml-64 min-h-screen">
        <AnimatePresence mode="wait">
          <Outlet />
        </AnimatePresence>
      </main>
    </div>
  );
}
