// ─────────────────────────────────────────────────────────────────────────────
// 資料載入層：astro 只讀專案根的 ../data（不改它）。
// 用 import.meta.glob（相對 astro/src）在 build 時把 data/ 載入。
// schema 為單一事實：../../schemas/*.schema.json。
// ─────────────────────────────────────────────────────────────────────────────

// ── 型別（對齊 schemas/） ───────────────────────────────────────────────────
export type Status = 'OK' | 'MUMBLE' | 'CORRUPT' | 'DOWN';

export interface BoardCell {
  team: string;
  service: string;
  status: Status;
  stolen: boolean;
}
export interface AttackEvent {
  model: string;
  service: string;
  method: string;
  victim: string;
}
export interface DefenseEvent {
  service: string;
  action: string;
  version_bump?: string;
}
export interface Round {
  round: number;
  board: BoardCell[];
  attack_events: AttackEvent[];
  defense_events: DefenseEvent[];
}
export interface RunFingerprint {
  image_hash?: string;
  service_commit?: string;
  forcad: { round_time: number; flag_lifetime: number };
  defender: { model: string; recipe: string };
  attackers: { model: string; cli?: string }[];
}
export interface RunDefense {
  flags_held_pct: number;
  sla_uptime_pct: number;
  patch_effective?: Record<string, boolean>;
  self_own_count?: number;
  nopatch_baseline_flags_lost?: number;
}
export interface Run {
  run_id: string;
  kind?: 'normal' | 'portability';
  fingerprint: RunFingerprint;
  defense: RunDefense;
  attack_intel: { model: string; service: string; method: string; round: number }[];
  timeseries: Round[];
}

export interface TrajectoryVersion {
  version: string;
  run_id: string;
  flags_held_pct: number;
  diff_summary: string;
}
export interface TrajectoryModel {
  model: string;
  versions: TrajectoryVersion[];
}
export interface Trajectory {
  models: TrajectoryModel[];
}

export interface AttackIntel {
  methods: {
    model: string;
    service: string;
    method: string;
    first_round: number;
    runs?: string[];
  }[];
  leaderboard: { model: string; flags_stolen: number; services?: string[] }[];
}

export interface RecipeVersion {
  model: string;
  version: string;
  prompt: string;
  playbook: string;
}

// ── 靜態載入（build 時固化） ────────────────────────────────────────────────
const runModules = import.meta.glob<Run>('../../../data/runs/*.json', {
  eager: true,
  import: 'default',
});
const trajectoryRaw = import.meta.glob<Trajectory>('../../../data/recipe/trajectory.json', {
  eager: true,
  import: 'default',
});
const attackIntelRaw = import.meta.glob<AttackIntel>('../../../data/attack_intel.json', {
  eager: true,
  import: 'default',
});
const promptModules = import.meta.glob<string>('../../../data/recipe/*/*/PROMPT.md', {
  eager: true,
  import: 'default',
  query: '?raw',
});
const playbookModules = import.meta.glob<string>('../../../data/recipe/*/*/playbook.md', {
  eager: true,
  import: 'default',
  query: '?raw',
});

// ── 取用 helper ──────────────────────────────────────────────────────────────
export function getRuns(): Run[] {
  return Object.values(runModules).sort((a, b) => b.run_id.localeCompare(a.run_id));
}
export function getRun(run_id: string): Run | undefined {
  return getRuns().find((r) => r.run_id === run_id);
}
/** 該 run_id 是否有匯出檔（決定 trajectory 是否給回放連結）。 */
export function runExists(run_id: string): boolean {
  return getRuns().some((r) => r.run_id === run_id);
}

export function getTrajectory(): Trajectory {
  const v = Object.values(trajectoryRaw)[0];
  return v ?? { models: [] };
}
export function getAttackIntel(): AttackIntel {
  const v = Object.values(attackIntelRaw)[0];
  return v ?? { methods: [], leaderboard: [] };
}

/** 解析 recipe/<model>/<version>/ 的 PROMPT.md + playbook.md。 */
export function getRecipes(): RecipeVersion[] {
  const byKey = new Map<string, RecipeVersion>();
  const pathRe = /\/recipe\/([^/]+)\/([^/]+)\/(PROMPT|playbook)\.md$/;

  const fill = (mods: Record<string, string>, field: 'prompt' | 'playbook') => {
    for (const [path, content] of Object.entries(mods)) {
      const m = path.match(pathRe);
      if (!m) continue;
      const [, model, version] = m;
      const key = `${model}::${version}`;
      const rec =
        byKey.get(key) ?? { model, version, prompt: '', playbook: '' };
      rec[field] = content;
      byKey.set(key, rec);
    }
  };
  fill(promptModules, 'prompt');
  fill(playbookModules, 'playbook');

  return [...byKey.values()].sort((a, b) =>
    a.model === b.model
      ? a.version.localeCompare(b.version, undefined, { numeric: true })
      : a.model.localeCompare(b.model),
  );
}

export function getModels(): string[] {
  const set = new Set<string>();
  for (const r of getRecipes()) set.add(r.model);
  for (const m of getTrajectory().models) set.add(m.model);
  return [...set];
}

export function getRecipesByModel(model: string): RecipeVersion[] {
  return getRecipes().filter((r) => r.model === model);
}

export function latestRecipe(model: string): RecipeVersion | undefined {
  const list = getRecipesByModel(model);
  return list[list.length - 1];
}

// 顯示名稱（資料是 slug，UI 用較友善的標籤）。
const MODEL_LABELS: Record<string, string> = {
  'claude-fable-5': 'Claude Fable 5',
  'gpt-5.1': 'GPT-5.1',
  'gemini-3': 'Gemini 3',
};
export function modelLabel(slug: string): string {
  return MODEL_LABELS[slug] ?? slug;
}

const SERVICE_LABELS: Record<string, string> = {
  notes: 'notes',
  filelocker: 'filelocker',
  vault: 'vault',
};
export const SERVICES = ['notes', 'filelocker', 'vault'];
export function serviceLabel(s: string): string {
  return SERVICE_LABELS[s] ?? s;
}

export function pct(n: number): string {
  // 資料用 0..1 小數；顯示成百分比整數。
  return `${Math.round(n * 100)}%`;
}
