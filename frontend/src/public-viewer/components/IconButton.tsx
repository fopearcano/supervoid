import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Props = {
  children: ReactNode;
  label: string;
  active?: boolean;
} & ButtonHTMLAttributes<HTMLButtonElement>;

/** A square, restrained control used across the reader chrome. */
export function IconButton({
  children,
  label,
  active = false,
  className = '',
  ...rest
}: Props) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      title={label}
      className={[
        'grid h-9 w-9 place-items-center border transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-30',
        active
          ? 'border-accent text-accent'
          : 'border-rule text-parchment-dim hover:border-parchment-dim hover:text-parchment',
        className,
      ].join(' ')}
      {...rest}
    >
      {children}
    </button>
  );
}
