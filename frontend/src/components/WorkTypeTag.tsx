import { WORK_TYPE_LABELS, type WorkType } from '@/types/manuscript';

// Visual product lines (illustrated formats) take a faint brass tint so the
// graphic-novel and art-book lines read distinctly from prose titles.
const VISUAL_TYPES: ReadonlySet<WorkType> = new Set(['graphic_novel', 'art_book']);

interface Props {
  workType: WorkType;
}

export function WorkTypeTag({ workType }: Props) {
  const visual = VISUAL_TYPES.has(workType);
  const tone = visual
    ? 'border-accent/50 text-accent'
    : 'border-rule text-parchment-dim';
  return (
    <span
      className={`inline-flex items-center border ${tone} px-2 py-0.5 font-mono text-[0.6rem] uppercase tracking-widest`}
    >
      {WORK_TYPE_LABELS[workType]}
    </span>
  );
}
