import { useEffect, useRef, useState } from 'react';
import type { PublicMediaAsset } from '../types/reader';
import { mediaUrl } from '../api/publicClient';
import { IconButton } from '../components/IconButton';
import { Icon } from './icons';

/**
 * Background music for the reader. Plays the most specific available track
 * (page > chapter > volume > work). Never autoplays before the user has
 * entered the experience, and degrades gracefully when playback is blocked or
 * the file is missing.
 */
export function AudioPlayer({
  track,
  enabled,
  startMuted,
}: {
  track: PublicMediaAsset | null;
  enabled: boolean;
  startMuted: boolean;
}) {
  const ref = useRef<HTMLAudioElement | null>(null);
  const userPaused = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(startMuted);
  const [volume, setVolume] = useState(0.7);
  const [blocked, setBlocked] = useState(false);
  const [errored, setErrored] = useState(false);

  const tryPlay = async () => {
    const el = ref.current;
    if (!el) return;
    try {
      await el.play();
      setBlocked(false);
    } catch {
      // Autoplay/playback blocked by the browser — surface a quiet hint.
      setBlocked(true);
      setPlaying(false);
    }
  };

  // Load a new track when it changes.
  useEffect(() => {
    const el = ref.current;
    if (!el || !track) {
      setPlaying(false);
      return;
    }
    setErrored(false);
    el.src = mediaUrl(track.file_path) ?? '';
    el.loop = track.loop;
    el.load();
    userPaused.current = false;
    if (enabled) void tryPlay();
    // Intentionally keyed on the track id only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [track?.id]);

  // Start when the user enters the experience.
  useEffect(() => {
    if (enabled && track && !userPaused.current) void tryPlay();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // Keep element volume/mute in sync.
  useEffect(() => {
    const el = ref.current;
    if (el) {
      el.muted = muted;
      el.volume = volume;
    }
  }, [muted, volume]);

  const toggle = () => {
    const el = ref.current;
    if (!el || !track) return;
    if (el.paused) {
      userPaused.current = false;
      void tryPlay();
    } else {
      el.pause();
      userPaused.current = true;
    }
  };

  if (!track) return null;

  const label = errored
    ? 'Track unavailable'
    : blocked
      ? 'Press play for sound'
      : track.title;

  return (
    <div className="flex items-center gap-1.5">
      <audio
        ref={ref}
        preload="none"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onError={() => {
          setErrored(true);
          setPlaying(false);
        }}
      />
      <IconButton
        label={playing ? 'Pause music' : 'Play music'}
        onClick={toggle}
        disabled={errored}
        active={playing}
      >
        <Icon name={playing ? 'pause' : 'play'} size={15} />
      </IconButton>
      <IconButton
        label={muted ? 'Unmute' : 'Mute'}
        onClick={() => setMuted((m) => !m)}
        active={muted}
        disabled={errored}
      >
        <Icon name={muted ? 'mute' : 'sound'} size={15} />
      </IconButton>
      <input
        type="range"
        className="sv-range w-16"
        min={0}
        max={1}
        step={0.01}
        value={volume}
        onChange={(e) => {
          setVolume(Number(e.target.value));
          if (muted) setMuted(false);
        }}
        aria-label="Music volume"
        disabled={errored}
      />
      <span className="hidden max-w-[10rem] truncate font-mono text-[0.54rem] uppercase tracking-widest text-parchment-shadow lg:inline">
        {label}
        {track.loop && !errored ? ' · loop' : ''}
      </span>
    </div>
  );
}
