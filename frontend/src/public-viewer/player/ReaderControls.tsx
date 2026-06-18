import type {
  PublicMediaAsset,
  PublishedChapterSummary,
  PublishedVolume,
  ReaderMode,
} from '../types/reader';
import { READER_MODE_LABELS } from '../types/reader';
import { IconButton } from '../components/IconButton';
import { Icon } from './icons';
import type { IconName } from './icons';
import { AudioPlayer } from './AudioPlayer';

type FitMode = 'width' | 'height' | 'none';

const MODE_ICON: Record<ReaderMode, IconName> = {
  single: 'single',
  double: 'double',
  scroll: 'scroll',
  cinematic: 'cinematic',
};

export interface ReaderControlsProps {
  chromeVisible: boolean;
  workTitle: string;
  chapterTitle: string;
  onExit: () => void;

  mode: ReaderMode;
  onMode: (mode: ReaderMode) => void;

  pageLabel: string;
  progress: number;
  onPrev: () => void;
  onNext: () => void;

  fit: FitMode;
  zoom: number;
  onSetFit: (fit: FitMode) => void;
  onZoom: (delta: number) => void;

  hotspotsVisible: boolean;
  onToggleHotspots: () => void;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onHideChrome: () => void;

  volumes: PublishedVolume[];
  volumeId: string;
  chapters: PublishedChapterSummary[];
  chapterId: string;
  onSelectVolume: (volume: PublishedVolume) => void;
  onSelectChapter: (chapterId: string) => void;

  audioTrack: PublicMediaAsset | null;
  audioEnabled: boolean;
  audioStartMuted: boolean;
}

export function ReaderControls(props: ReaderControlsProps) {
  const hidden = props.chromeVisible ? '' : 'sv-chrome--hidden';
  const modes: ReaderMode[] = ['single', 'double', 'scroll', 'cinematic'];

  return (
    <>
      {/* Top bar — identity + view controls */}
      <div
        className={`sv-chrome pointer-events-auto absolute inset-x-0 top-0 z-40 flex items-center justify-between gap-4 border-b border-rule bg-[color:var(--sv-reader-chrome)] px-4 py-3 ${hidden}`}
      >
        <div className="flex min-w-0 items-center gap-4">
          <button
            type="button"
            onClick={props.onExit}
            className="font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim hover:text-parchment"
          >
            ← Exit
          </button>
          <div className="min-w-0">
            <p className="truncate font-serif text-sm text-parchment">
              {props.workTitle}
            </p>
            <p className="truncate font-mono text-[0.54rem] uppercase tracking-widest text-parchment-shadow">
              {props.chapterTitle}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {modes.map((mode) => (
            <IconButton
              key={mode}
              label={READER_MODE_LABELS[mode]}
              active={props.mode === mode}
              onClick={() => props.onMode(mode)}
            >
              <Icon name={MODE_ICON[mode]} size={16} />
            </IconButton>
          ))}
          <span className="mx-1 h-5 w-px bg-rule" />
          <IconButton
            label={props.hotspotsVisible ? 'Hide annotations' : 'Show annotations'}
            active={props.hotspotsVisible}
            onClick={props.onToggleHotspots}
          >
            <Icon name={props.hotspotsVisible ? 'eye' : 'eye-off'} size={16} />
          </IconButton>
          <IconButton
            label={props.isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
            onClick={props.onToggleFullscreen}
          >
            <Icon name={props.isFullscreen ? 'exit-fullscreen' : 'fullscreen'} size={16} />
          </IconButton>
          <IconButton label="Hide interface" onClick={props.onHideChrome}>
            <Icon name="eye-off" size={16} />
          </IconButton>
        </div>
      </div>

      {/* Bottom bar — navigation + zoom + music */}
      <div
        className={`sv-chrome pointer-events-auto absolute inset-x-0 bottom-0 z-40 border-t border-rule bg-[color:var(--sv-reader-chrome)] ${hidden}`}
      >
        <div className="h-0.5 w-full bg-ink-700">
          <div
            className="h-full bg-accent transition-[width] duration-300"
            style={{ width: `${Math.round(props.progress * 100)}%` }}
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
          {/* selectors */}
          <div className="flex items-center gap-2">
            <select
              className="field-select bg-ink-700 text-[0.7rem]"
              value={props.volumeId}
              onChange={(e) => {
                const volume = props.volumes.find((v) => v.id === e.target.value);
                if (volume) props.onSelectVolume(volume);
              }}
              aria-label="Select volume"
            >
              {props.volumes.map((volume) => (
                <option key={volume.id} value={volume.id}>
                  Vol. {volume.volume_number} — {volume.title}
                </option>
              ))}
            </select>
            <select
              className="field-select bg-ink-700 text-[0.7rem]"
              value={props.chapterId}
              onChange={(e) => props.onSelectChapter(e.target.value)}
              aria-label="Select chapter"
            >
              {props.chapters.map((chapter) => (
                <option key={chapter.id} value={chapter.id}>
                  {String(chapter.chapter_number).padStart(2, '0')} · {chapter.title}
                </option>
              ))}
            </select>
          </div>

          {/* pager */}
          <div className="flex items-center gap-3">
            <IconButton label="Previous" onClick={props.onPrev}>
              <Icon name="prev" size={16} />
            </IconButton>
            <span className="min-w-[5rem] text-center font-mono text-[0.6rem] uppercase tracking-widest text-parchment-dim">
              {props.pageLabel}
            </span>
            <IconButton label="Next" onClick={props.onNext}>
              <Icon name="next" size={16} />
            </IconButton>
          </div>

          {/* zoom + fit + music */}
          <div className="flex items-center gap-1.5">
            <IconButton label="Fit width" active={props.fit === 'width'} onClick={() => props.onSetFit('width')}>
              <Icon name="fit-width" size={16} />
            </IconButton>
            <IconButton label="Fit height" active={props.fit === 'height'} onClick={() => props.onSetFit('height')}>
              <Icon name="fit-height" size={16} />
            </IconButton>
            <IconButton label="Zoom out" onClick={() => props.onZoom(-0.15)}>
              <Icon name="zoom-out" size={16} />
            </IconButton>
            <IconButton label="Zoom in" onClick={() => props.onZoom(0.15)}>
              <Icon name="zoom-in" size={16} />
            </IconButton>
            <span className="mx-1 h-5 w-px bg-rule" />
            <AudioPlayer
              track={props.audioTrack}
              enabled={props.audioEnabled}
              startMuted={props.audioStartMuted}
            />
          </div>
        </div>
      </div>
    </>
  );
}
