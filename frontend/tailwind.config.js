/** @type {import('tailwindcss').Config} */

// Colours are driven by CSS custom properties (channel triplets like "13 12 10")
// so the whole admin app can be re-themed at runtime by switching `data-theme`
// on <html> — see src/index.css for the archival (default) and hacker palettes.
// The `rgb(var(--c-*) / <alpha-value>)` form keeps Tailwind's opacity modifiers
// (e.g. text-parchment/90, bg-ink-700/40) working per theme.
const v = (name) => `rgb(var(${name}) / <alpha-value>)`;

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        ink: {
          50: v('--c-ink-50'),
          100: v('--c-ink-100'),
          200: v('--c-ink-200'),
          300: v('--c-ink-300'),
          400: v('--c-ink-400'),
          500: v('--c-ink-500'),
          600: v('--c-ink-600'),
          650: v('--c-ink-650'),
          700: v('--c-ink-700'),
          800: v('--c-ink-800'),
          900: v('--c-ink-900'),
        },
        parchment: {
          DEFAULT: v('--c-parchment'),
          muted: v('--c-parchment-muted'),
          dim: v('--c-parchment-dim'),
          shadow: v('--c-parchment-shadow'),
        },
        accent: {
          DEFAULT: v('--c-accent'),
          soft: v('--c-accent-soft'),
          deep: v('--c-accent-deep'),
        },
        rule: v('--c-rule'),
        // Trouble states (overdue, blocked, reject, errors) — oxblood in the
        // archival theme, a readable red in the hacker theme.
        signal: {
          DEFAULT: v('--c-signal'),
          soft: v('--c-signal-soft'),
          dim: v('--c-signal-dim'),
        },
      },
      fontFamily: {
        serif: ['"EB Garamond"', '"Cormorant Garamond"', 'Georgia', 'serif'],
        sans: ['"Inter"', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'ui-monospace', 'monospace'],
        // Display wordmark (Cinzel) + decorative script (Pinyon) — used for the
        // SUPERVOID wordmark and the home kicker.
        display: ['"Cinzel"', '"EB Garamond"', 'Georgia', 'serif'],
        script: ['"Pinyon Script"', 'cursive'],
      },
      letterSpacing: {
        wider: '0.08em',
        widest: '0.22em',
      },
      maxWidth: {
        editorial: '78rem',
        chronicle: '34rem', // a book-page width for long-form prose
      },
    },
  },
  plugins: [],
};
