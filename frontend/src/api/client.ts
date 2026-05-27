const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

// Time-range filter shared by every insights call.
export type TimeRange = 'day' | 'week' | 'month' | 'year' | 'all';

function rangeQs(range: TimeRange | undefined): string {
  return range && range !== 'all' ? `range=${range}` : '';
}

function buildQs(...parts: (string | undefined)[]): string {
  const kept = parts.filter((p): p is string => !!p);
  return kept.length ? `?${kept.join('&')}` : '';
}

// Players
export function createPlayer(provider: string, username: string) {
  return request<Player>('/players', {
    method: 'POST',
    body: JSON.stringify({ provider, username }),
  });
}

export function getPlayer(id: string) {
  return request<Player>(`/players/${id}`);
}

export function startImport(playerId: string) {
  return request<{ job_id: string }>(`/players/${playerId}/import`, {
    method: 'POST',
  });
}

export function getImportStatus(playerId: string) {
  return request<ImportStatus | null>(`/players/${playerId}/import/status`);
}

// Games
export function listGames(playerId: string, params?: GameListParams) {
  const search = new URLSearchParams();
  if (params?.limit != null) search.set('limit', String(params.limit));
  if (params?.offset != null) search.set('offset', String(params.offset));
  if (params?.time_class) search.set('time_class', params.time_class);
  if (params?.user_color) search.set('user_color', params.user_color);
  if (params?.user_result) search.set('user_result', params.user_result);
  if (params?.opening_name) search.set('opening_name', params.opening_name);
  if (params?.opening_search) search.set('opening_search', params.opening_search);
  if (params?.eco) search.set('eco', params.eco);
  if (params?.opp_rating_min != null) search.set('opp_rating_min', String(params.opp_rating_min));
  if (params?.opp_rating_max != null) search.set('opp_rating_max', String(params.opp_rating_max));
  if (params?.user_rating_min != null) search.set('user_rating_min', String(params.user_rating_min));
  if (params?.user_rating_max != null) search.set('user_rating_max', String(params.user_rating_max));
  if (params?.played_from) search.set('played_from', params.played_from);
  if (params?.played_to) search.set('played_to', params.played_to);
  if (params?.analyzed != null) search.set('analyzed', String(params.analyzed));
  if (params?.sort) search.set('sort', params.sort);
  if (params?.order) search.set('order', params.order);
  const qs = search.toString();
  return request<GameListResponse>(`/players/${playerId}/games${qs ? '?' + qs : ''}`);
}

export function getGame(gameId: string) {
  return request<GameDetail>(`/games/${gameId}`);
}

// Insights
export function getOpeningTree(playerId: string, minVisits = 5, maxPly = 24, range?: TimeRange) {
  const qs = buildQs(`min_visits=${minVisits}`, `max_ply=${maxPly}`, rangeQs(range));
  return request<{ nodes: OpeningTreeNode[] }>(`/players/${playerId}/insights/opening-tree${qs}`);
}

export function getPhasePerformance(playerId: string, range?: TimeRange) {
  const qs = buildQs(rangeQs(range));
  return request<PhasePerformance[]>(`/players/${playerId}/insights/phase-performance${qs}`);
}

export function getTimePressure(playerId: string, timeClass = 'blitz', range?: TimeRange) {
  const qs = buildQs(`time_class=${timeClass}`, rangeQs(range));
  return request<TimePressureBucket[]>(`/players/${playerId}/insights/time-pressure${qs}`);
}

export function getAccuracyTrend(playerId: string, timeClass?: string, range?: TimeRange) {
  const qs = buildQs(timeClass ? `time_class=${timeClass}` : undefined, rangeQs(range));
  return request<AccuracyPoint[]>(`/players/${playerId}/insights/accuracy-trend${qs}`);
}

export function getOpeningStats(playerId: string, minGames = 3, color?: string, range?: TimeRange) {
  const qs = buildQs(
    `min_games=${minGames}`,
    color ? `color=${color}` : undefined,
    rangeQs(range),
  );
  return request<OpeningStat[]>(`/players/${playerId}/insights/opening-stats${qs}`);
}

export function getRatingPerformance(playerId: string, range?: TimeRange) {
  const qs = buildQs(rangeQs(range));
  return request<RatingBucket[]>(`/players/${playerId}/insights/rating-performance${qs}`);
}

export function getRecommendations(playerId: string, range?: TimeRange) {
  const qs = buildQs(rangeQs(range));
  return request<RecommendationsResponse>(
    `/players/${playerId}/insights/recommendations${qs}`,
  );
}

export function getMotifs(playerId: string, range?: TimeRange) {
  const qs = buildQs(rangeQs(range));
  return request<MotifSummary[]>(`/players/${playerId}/insights/motifs${qs}`);
}

export function getMotifExamples(
  playerId: string,
  motif: string,
  limit = 20,
  range?: TimeRange,
) {
  const qs = buildQs(`limit=${limit}`, rangeQs(range));
  return request<MotifExample[]>(
    `/players/${playerId}/insights/motifs/${motif}${qs}`,
  );
}

// Health
export function getHealth() {
  return request<HealthStatus>('/health');
}

// Types
export interface Player {
  id: string;
  provider: string;
  username: string;
  display_name: string | null;
  created_at: string;
  last_imported_at: string | null;
  total_games_imported: number;
}

export interface ImportStatus {
  id: string;
  status: string;
  total_games: number;
  imported_games: number;
  analyzed_positions: number;
  total_positions: number;
  analyzed_games: number;
  cache_hits: number;
  cloud_hits: number;
  tablebase_hits: number;
  engine_hits: number;
  error: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface GameListParams {
  limit?: number;
  offset?: number;
  time_class?: string;
  user_color?: string;
  user_result?: string;
  opening_name?: string;
  opening_search?: string;
  eco?: string;
  opp_rating_min?: number;
  opp_rating_max?: number;
  user_rating_min?: number;
  user_rating_max?: number;
  played_from?: string;
  played_to?: string;
  analyzed?: boolean;
  sort?: 'played_at' | 'opp_rating' | 'user_rating' | 'ply_count';
  order?: 'asc' | 'desc';
}

export interface GameListResponse {
  total: number;
  offset: number;
  limit: number;
  games: GameListItem[];
}

export interface GameListItem {
  id: string;
  white_username: string;
  black_username: string;
  white_rating: number | null;
  black_rating: number | null;
  user_color: string;
  result: string;
  user_result: string;
  time_control: string;
  time_class: string;
  eco: string | null;
  opening_name: string | null;
  played_at: string;
  ply_count: number;
  analyzed_at: string | null;
}

export interface GameMove {
  ply: number;
  san: string;
  uci: string;
  fen_before: string | null;
  fen_after: string | null;
  clock_remaining_ms: number | null;
  eval_before_cp: number | null;
  eval_after_cp: number | null;
  cp_loss: number | null;
  classification: string | null;
  phase: string | null;
  is_user_move: boolean;
}

export interface GameDetail {
  id: string;
  white_username: string;
  black_username: string;
  white_rating: number | null;
  black_rating: number | null;
  user_color: string;
  result: string;
  user_result: string;
  time_control: string;
  time_class: string;
  eco: string | null;
  opening_name: string | null;
  played_at: string;
  ply_count: number;
  pgn: string;
  moves: GameMove[];
}

export interface OpeningTreeNode {
  fen_key: string;
  san: string;
  visit_count: number;
  avg_cp_loss: number;
  total_cp_loss: number;
  children: OpeningTreeNode[];
}

export interface PhasePerformance {
  phase: string;
  color: string | null;
  sample_size: number;
  avg_cpl: number;
  blunder_rate: number;
  mistake_rate: number;
  inaccuracy_rate: number;
}

export interface TimePressureBucket {
  bucket: string;
  sample_size: number;
  avg_cpl: number;
  blunder_rate: number;
}

export interface AccuracyPoint {
  game_id: string;
  played_at: string;
  time_class: string;
  user_result: string;
  opening_name: string | null;
  avg_cpl: number;
  accuracy: number;
}

export interface OpeningStat {
  eco: string | null;
  opening_name: string;
  color: string;
  games: number;
  wins: number;
  draws: number;
  losses: number;
  win_rate: number;
  avg_cpl: number;
}

export interface RatingBucket {
  bucket: string;
  low?: number;
  high?: number;
  games: number;
  wins: number;
  draws: number;
  losses: number;
  win_rate: number;
  avg_cpl: number;
}

export interface HealthStatus {
  status: string;
  db: boolean;
  engine: string;
  queue: boolean;
}

export interface RecommendationAction {
  kind: string;
  label: string;
  href?: string;
  external?: boolean;
}

export type RecommendationKind =
  | 'opening_leak'
  | 'phase_weakness'
  | 'time_pressure'
  | 'rating_wall'
  | 'color_asymmetry'
  | 'missed_wins'
  | 'anti_repertoire'
  | 'blunder_pattern'
  | 'time_of_day'
  | 'tilt';

export type TrendDirection = 'improving' | 'worsening' | 'stable';

export interface RecommendationTrend {
  direction: TrendDirection;
  current: number;
  prior: number;
  delta: number;
  note?: string;
}

export interface Recommendation {
  id: string;
  kind: RecommendationKind;
  title: string;
  summary: string;
  score: number;
  severity: number;
  volume: number;
  evidence: Record<string, unknown>;
  actions: RecommendationAction[];
  trend?: RecommendationTrend;
}

export interface RecommendationsBaseline {
  games: number;
  accuracy: number;
  avg_cpl: number;
  blunder_rate: number;
  user_moves: number;
}

export interface RecommendationsResponse {
  baseline: RecommendationsBaseline;
  recommendations: Recommendation[];
  message?: string;
  totals?: { candidates: number; returned: number };
}

export interface MotifSummary {
  motif: string;
  count: number;
  games: number;
  blunders: number;
  mistakes: number;
}

export interface MotifExample {
  tactic_id: string;
  game_id: string;
  move_id: string;
  ply: number;
  san: string;
  classification: string | null;
  cp_loss: number | null;
  opening_name: string | null;
  user_result: string;
  played_at: string;
}
