import { THEME_LABELS, useTheme, type Theme } from '@/theme/ThemeContext';

const ORDER: Theme[] = ['archival', 'hacker'];

/** A compact two-option segmented switch between the archival and hacker
 * themes. Used in the sidebar footer and on the landing page. */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  return (
    <div
      role="group"
      aria-label="Theme"
      className="flex items-center gap-0.5 rounded-sm border border-rule p-0.5"
    >
      {ORDER.map((option) => {
        const active = theme === option;
        return (
          <button
            key={option}
            type="button"
            aria-pressed={active}
            onClick={() => setTheme(option)}
            className={`flex-1 rounded-[2px] px-2 py-1 font-mono text-[0.55rem] uppercase tracking-widest transition-colors ${
              active
                ? 'bg-accent text-ink-900'
                : 'text-parchment-dim hover:text-parchment'
            }`}
          >
            {THEME_LABELS[option]}
          </button>
        );
      })}
    </div>
  );
}
