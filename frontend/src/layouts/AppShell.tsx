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
  | 'brain-hub'
  | 'memory-review'
  | 'brain-state'
  | 'brain-tokens'
  | 'brain-account'
  | 'identity-access'
  | 'brain-ops'
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
      { view: 'brain-hub', label: 'SUPERVOID Brain' },
      { view: 'memory-review', label: 'Memory Review' },
      { view: 'agent-centre', label: 'Agents' },
      { view: 'brain-ops', label: 'Brain Operations' },
      { view: 'brain-state', label: 'Brain State' },
      { view: 'brain-tokens', label: 'Brain Tokens' },
      { view: 'brain-account', label: 'Brain Account' },
      { view: 'identity-access', label: 'Identity & Access' },
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

/** Sidebar contents, shared by the desktop column and the mobile drawer. */
function SidebarInner({
  onNavigate,
  isActive,
  onCollapse,
  onClose,
}: {
  onNavigate: (view: AppView) => void;
  isActive: (item: NavItem) => boolean;
  onCollapse?: () => void;
  onClose?: () => void;
}) {
  return (
    <>
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
        {onCollapse && (
          <button
            type="button"
            onClick={onCollapse}
            aria-label="Hide menu"
            title="Hide menu"
            className="rounded-sm border border-rule px-1.5 py-0.5 font-mono text-[0.7rem] text-parchment-muted transition-colors hover:border-parchment-muted hover:text-parchment"
          >
            ‹
          </button>
        )}
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            title="Close menu"
            className="rounded-sm border border-rule px-2 py-0.5 font-mono text-[0.8rem] text-parchment-muted transition-colors hover:border-parchment-muted hover:text-parchment"
          >
            ✕
          </button>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="side-group-label">{group.label}</div>
            {group.items.map((item) => (
              <button
                key={item.view}
                type="button"
                onClick={() => onNavigate(item.view)}
                className={`side-link w-full text-left ${isActive(item) ? 'side-link-active' : ''}`}
              >
                <span
                  aria-hidden
                  className={`h-3.5 w-px ${isActive(item) ? 'bg-accent' : 'bg-transparent'}`}
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
    </>
  );
}

export function AppShell({ children, onNavigate, activeView }: AppShellProps) {
  const [collapsed, setCollapsed] = useState(readCollapsed); // desktop only (persisted)
  const [mobileOpen, setMobileOpen] = useState(false); // mobile drawer (ephemeral)

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_KEY, collapsed ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  const isActive = (item: NavItem) =>
    activeView === item.view || (item.also?.includes(activeView) ?? false);

  const navigateMobile = (view: AppView) => {
    onNavigate(view);
    setMobileOpen(false);
  };

  return (
    <div className="flex min-h-screen bg-ink-800">
      {/* Desktop sidebar — in-flow, collapsible (lg and up). */}
      {!collapsed && (
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-rule bg-ink-900/40 lg:flex">
          <SidebarInner
            onNavigate={onNavigate}
            isActive={isActive}
            onCollapse={() => setCollapsed(true)}
          />
        </aside>
      )}

      {/* Mobile drawer + backdrop (below lg). */}
      <div
        aria-hidden
        onClick={() => setMobileOpen(false)}
        className={`fixed inset-0 z-40 bg-black/60 transition-opacity lg:hidden ${
          mobileOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 max-w-[82%] flex-col border-r border-rule bg-ink-900 shadow-xl transition-transform duration-200 lg:hidden ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <SidebarInner
          onNavigate={navigateMobile}
          isActive={isActive}
          onClose={() => setMobileOpen(false)}
        />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar — always available below lg. */}
        <div className="sticky top-0 z-30 flex items-center gap-3 border-b border-rule bg-ink-800/95 px-4 py-3 backdrop-blur lg:hidden">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
            title="Open menu"
            className="rounded-sm border border-rule px-2.5 py-1 font-mono text-[0.9rem] text-parchment-muted transition-colors hover:border-parchment-muted hover:text-parchment"
          >
            ☰
          </button>
          <button
            type="button"
            onClick={() => onNavigate('command')}
            className="font-display font-semibold tracking-[0.05em] text-parchment"
          >
            SUPERVOID
          </button>
        </div>

        {/* Desktop "show menu" affordance when the column is collapsed. */}
        {collapsed && (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            aria-label="Show menu"
            title="Show menu"
            className="fixed left-4 top-4 z-30 hidden rounded-sm border border-rule bg-ink-800/90 px-2.5 py-1.5 font-mono text-[0.8rem] text-parchment-muted backdrop-blur transition-colors hover:border-parchment-muted hover:text-parchment lg:block"
          >
            ☰
          </button>
        )}

        <main
          className={`mx-auto w-full max-w-editorial flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-12 ${
            collapsed ? 'lg:pt-16' : ''
          }`}
        >
          {children}
        </main>
        <footer className="border-t border-rule">
          <div className="mx-auto flex max-w-editorial items-center justify-between gap-3 px-4 py-5 font-mono text-[0.62rem] uppercase tracking-widest text-parchment-dim sm:px-8">
            <span>Locally hosted</span>
            <span>Editorial Office · Folio I</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
