/**
 * The "Enter / Start Experience" gate. Browsers block audio until a user
 * gesture; this overlay provides that gesture and lets the reader choose
 * whether to begin with sound. Audio is never forced.
 */
export function EnterOverlay({
  title,
  subtitle,
  hasAudio,
  onEnter,
}: {
  title: string;
  subtitle?: string | null;
  hasAudio: boolean;
  onEnter: (withSound: boolean) => void;
}) {
  return (
    <div className="absolute inset-0 z-40 grid place-items-center bg-ink-900/95 px-6 backdrop-blur-sm sv-page-fade">
      <div className="max-w-md text-center">
        <p className="font-mono text-[0.6rem] uppercase tracking-[0.3em] text-parchment-dim">
          SUPERVOID · Graphic Novel
        </p>
        <h1 className="mt-5 font-serif text-4xl leading-tight text-parchment">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-2 font-serif text-lg italic text-parchment-dim">
            {subtitle}
          </p>
        )}
        <p className="mx-auto mt-6 max-w-sm text-sm leading-relaxed text-parchment-muted/70">
          An interactive reading experience.
          {hasAudio
            ? ' Best with sound — music and ambience play as you read.'
            : ' Use the controls to change reading mode, zoom, and fullscreen.'}
        </p>

        <div className="mt-9 flex flex-col items-center gap-3">
          <button
            type="button"
            onClick={() => onEnter(hasAudio)}
            className="border border-accent px-6 py-2.5 font-mono text-[0.66rem] uppercase tracking-[0.28em] text-accent transition-colors hover:bg-accent hover:text-ink-900"
          >
            {hasAudio ? 'Enter with sound' : 'Enter'}
          </button>
          {hasAudio && (
            <button
              type="button"
              onClick={() => onEnter(false)}
              className="button-quiet"
            >
              Enter silently
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
