import { useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '@/auth/AuthContext';
import { ROLE_LABELS } from '@/types/auth';

export type AppView =
  | 'command'
  | 'work-command'
  | 'dashboard'
  | 'manuscript'
  | 'search'
  | 'archive'
  | 'production'
  | 'production-tasks'
  | 'asset-library'
  | 'gn-studio'
  | 'pictures-studio'
  | 'agent-centre'
  | 'brain-state'
  | 'integrations-hub'
  | 'rights-desk'
  | 'contacts'
  | 'editions'
  | 'curation'
  | 'calendar'
  | 'production-item'
  | 'story-worlds'
  | 'story-world'
  | 'adaptations'
  | 'work-transmedia';

interface AppShellProps {
  children: ReactNode;
  onNavigate: (view: AppView) => void;
  activeView: AppView;
}

interface NavItem {
  view: AppView;
  label: string;
  // Detail views (reached by drill-down) that should keep this item highlighted.
  also?: AppView[];
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Studio',
    items: [{ view: 'command', label: 'Studio', also: ['work-command'] }],
  },
  {
    label: 'IP & Story',
    items: [
      { view: 'story-worlds', label: 'Story Worlds', also: ['story-world', 'work-transmedia'] },
      { view: 'adaptations', label: 'Adaptations' },
      { view: 'dashboard', label: 'Manuscripts', also: ['manuscript'] },
    ],
  },
  {
    label: 'Production',
    items: [
      { view: 'production', label: 'Production', also: ['production-item'] },
      { view: 'production-tasks', label: 'Tasks' },
      { view: 'gn-studio', label: 'GN Studio' },
      { view: 'pictures-studio', label: 'Pictures' },
      { view: 'asset-library', label: 'Assets' },
    ],
  },
  {
    label: 'Audience',
    items: [
      { view: 'curation', label: 'Curation' },
      { view: 'calendar', label: 'Calendar' },
    ],
  },
  {
    label: 'Business',
    items: [
      { view: 'rights-desk', label: 'Rights' },
      { view: 'contacts', label: 'Contacts' },
      { view: 'editions', label: 'Editions' },
    ],
  },
  {
    label: 'System',
    items: [
      { view: 'agent-centre', label: 'Agents' },
      { view: 'brain-state', label: 'Brain' },
      { view: 'integrations-hub', label: 'Integrations' },
      { view: 'search', label: 'Search' },
      { view: 'archive', label: 'Archive' },
    ],
  },
];

const SIDEBAR_KEY = 'supervoid.sidebar.collapsed';

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_KEY) === '1';
  } catch {
    return false;
  }
}

function AccountBadge() {
  const { user, signOut } = useAuth();
  if (!user) return null;
  return (
    <div className="flex items-center justify-between gap-2 border-t border-rule px-3 py-3">
      <div className="min-w-0 leading-tight">
        <div className="truncate text-sm text-parchment">{user.full_name}</div>
        <div className="font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
          {ROLE_LABELS[user.role]}
        </div>
      </div>
      <button
        type="button"
        onClick={signOut}
        className="shrink-0 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim transition-colors hover:text-signal"
      >
        Sign out
      </button>
    </div>
  );
}

export function AppShell({ children, onNavigate, activeView }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(readCollapsed);

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  const isActive = (item: NavItem) =>
    activeView === item.view || (item.also?.includes(activeView) ?? false);

  return (
    <div className="flex min-h-screen bg-ink-800">
      {!collapsed && (
        <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-rule bg-ink-900/40">
          {/* Brand + collapse */}
          <div className="flex items-start justify-between gap-2 px-4 pb-4 pt-5">
            <button
              type="button"
              onClick={() => onNavigate('command')}
              className="flex flex-col items-start text-left transition-opacity hover:opacity-90 focus:outline-none"
            >
              <span className="font-display font-semibold text-[1.25rem] leading-none tracking-[0.05em] text-parchment">
                SUPERVOID
              </span>
              <span className="mt-1 font-mono text-[0.58rem] uppercase tracking-widest text-parchment-dim">
                Publishing
              </span>
            </button>
            <button
              type="button"
              onClick={() => setCollapsed(true)}
              aria-label="Hide menu"
              title="Hide menu"
              className="rounded-sm border border-rule px-1.5 py-0.5 font-mono text-[0.7rem] text-parchment-muted transition-colors hover:border-parchment-muted hover:text-parchment"
            >
              ‹
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto px-2 pb-4">
            {NAV_GROUPS.map((group) => (
              <div key={group.label}>
                <div className="side-group-label">{group.label}</div>
                {group.items.map((item) => (
                  <button
                    key={item.view}
                    type="button"
                    onClick={() => onNavigate(item.view)}
                    className={`side-link w-full text-left ${
                      isActive(item) ? 'side-link-active' : ''
                    }`}
                  >
                    <span
                      aria-hidden
                      className={`h-3.5 w-px ${
                        isActive(item) ? 'bg-accent' : 'bg-transparent'
                      }`}
                    />
                    {item.label}
                  </button>
                ))}
              </div>
            ))}
          </nav>

          <AccountBadge />
          <div className="border-t border-rule px-3 py-3">
            <span className="font-mono text-[0.54rem] uppercase tracking-widest text-parchment-dim">
              Locally hosted · SQLite
            </span>
          </div>
        </aside>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {collapsed && (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            aria-label="Show menu"
            title="Show menu"
            className="fixed left-4 top-4 z-30 rounded-sm border border-rule bg-ink-800/90 px-2.5 py-1.5 font-mono text-[0.8rem] text-parchment-muted backdrop-blur transition-colors hover:border-parchment-muted hover:text-parchment"
          >
            ☰
          </button>
        )}
        <main
          className={`mx-auto w-full max-w-editorial flex-1 px-8 py-12 ${
            collapsed ? 'pt-16' : ''
          }`}
        >
          {children}
        </main>
        <footer className="border-t border-rule">
          <div className="mx-auto flex max-w-editorial items-center justify-between px-8 py-5 font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim">
            <span>Locally hosted</span>
            <span>Editorial Office · Folio I</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
