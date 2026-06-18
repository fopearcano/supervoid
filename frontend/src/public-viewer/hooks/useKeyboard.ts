import { useEffect, useRef } from 'react';

type KeyHandlers = Record<string, (event: KeyboardEvent) => void>;

/**
 * Bind keyboard handlers keyed by `event.key`. Ignores keystrokes originating
 * in form fields. Handlers are read through a ref so callers can pass a fresh
 * object each render without re-binding the listener.
 */
export function useKeyboard(handlers: KeyHandlers, enabled = true) {
  const ref = useRef(handlers);
  ref.current = handlers;

  useEffect(() => {
    if (!enabled) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return;
      }
      const handler = ref.current[event.key];
      if (handler) handler(event);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [enabled]);
}
