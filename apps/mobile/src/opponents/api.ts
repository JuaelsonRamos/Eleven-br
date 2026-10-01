import { authenticated } from '../auth/api';

export type Category = 'male' | 'female' | 'mixed' | 'all';
export type PublicTeam = { id: string; name: string; code: string; city: string; state: string; modalities: string[]; crest_url: string | null; category: Exclude<Category, 'all'> | null };
export type Reliability = { validated_fixtures: number; reviews: number; attended: number; punctual: number; kept_agreement: number; label: string | null };
/** Free: one challenge sent per month; PRO: unlimited (limit null). Searching is always free. */
export type Credits = { limit: number | null; used: number; remaining: number | null; competence: string };
export type Central = { team: PublicTeam; accepts_challenges: boolean; can_manage: boolean; plan: 'free' | 'pro'; credits: Credits; pending_received: number };
/** Optional location filter: UF and, inside it, an official municipality (never typed text). */
export type Filters = { modality: string; category: Category; state?: string; municipality?: { code: number; name: string } | null };
export type Result = { team: PublicTeam; tier: 'city' | 'state' | 'other'; category_known: boolean; reliability: Reliability; pending_challenge: boolean };
export type Results = { filters: { modality: string; category: Category; state: string | null; municipality: number | null }; location: { city: string; state: string }; items: Result[]; has_more: boolean };
export type ChallengeStatus = 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'CANCELLED' | 'EXPIRED';
export type Challenge = {
  id: string; direction: 'sent' | 'received'; opponent: PublicTeam; modality: string; date: string; time: string; location: string; notes: string | null;
  venue: 'HOME' | 'AWAY'; status: ChallengeStatus; created_at: string; resolved_at: string | null; fixture_id: string | null; can_respond: boolean; can_cancel: boolean;
};
export type ResultStatus = 'NONE' | 'PENDING' | 'VALIDATED' | 'DISPUTED';
export type Fixture = {
  id: string; side: 'HOME' | 'AWAY'; opponent: PublicTeam; home_team: { id: string; name: string; crest_url: string | null }; away_team: { id: string; name: string; crest_url: string | null };
  status: 'SCHEDULED' | 'CANCELLED' | 'WITHDRAWN';
  modality: string; date: string; time: string; location: string; result_status: ResultStatus; home_score: number | null; away_score: number | null;
};
export type Score = { home_score: number; away_score: number; kind: 'REPORTED' | 'CONFIRMED'; created_at: string };
export type Review = { attended: boolean; punctual: boolean; kept_agreement: boolean; created_at: string };
export type Pair<T> = { mine: T | null; theirs: T | null };
export type FixtureDetail = Fixture & {
  version: number; command_id: string; can_change: boolean; proposals: FixtureProposal[];
  notes: string | null; challenge_id: string; event_id: string | null; started: boolean; scores: Pair<Score>; reviews: Pair<Review>;
  can_manage: boolean; can_report: boolean; can_confirm: boolean; can_review: boolean;
};
export type FixtureProposal = { id: string; team_id: string; kind: 'CHANGE' | 'CANCEL' | 'WITHDRAW'; status: 'PENDING' | 'ACCEPTED' | 'REJECTED' | 'SUPERSEDED'; reason: string | null; before: { date: string; time: string; location: string }; proposed: Partial<{ date: string; time: string; location: string }>; created_at: string; resolved_at: string | null };
export type ProposalInput = { command_id: string; expected_version: number; kind: FixtureProposal['kind']; reason: string | null; confirm: boolean; date?: string; time?: string; location?: string };
export const proposeChange = (team: string, fixture: string, data: ProposalInput) => authenticated<FixtureDetail>(`${base(team)}/fixtures/${part(fixture)}/proposals`, data, 'POST');
export const decideChange = (team: string, fixture: string, proposal: string, decision: 'ACCEPTED' | 'REJECTED') => authenticated<FixtureDetail>(`${base(team)}/fixtures/${part(fixture)}/proposals/${part(proposal)}/decision`, { decision }, 'POST');
export const fixtureStatus = { SCHEDULED: 'AGENDADO', CANCELLED: 'CANCELADO POR ACORDO', WITHDRAWN: 'DESISTÊNCIA' };
export type Profile = {
  team: PublicTeam; accepts_challenges: boolean; reliability: Reliability; compatible_modalities: string[]; pending_challenge: boolean; can_challenge: boolean; credits: Credits;
  history: { challenges: Challenge[]; fixtures: (Fixture & { reviews: Pair<Review> })[] }; command_id: string;
};
export type ChallengeInput = { command_id: string; opponent_team_id: string; modality: string; date: string; time: string; location: string; venue: 'HOME' | 'AWAY'; notes: string | null };
export type ScoreInput = { home_score: number; away_score: number };
export type ReviewInput = { attended: boolean; punctual: boolean; kept_agreement: boolean };

const base = (team: string) => `/v1/teams/${encodeURIComponent(team)}/opponents`;
const part = encodeURIComponent;
export const getCentral = (team: string) => authenticated<Central>(base(team));
export const saveSettings = (team: string, accepts: boolean) => authenticated<Central>(`${base(team)}/settings`, { accepts_challenges: accepts }, 'PUT');
export function searchOpponents(team: string, filters: Filters, offset = 0) {
  const params = new URLSearchParams({ modality: filters.modality, category: filters.category, offset: String(offset) });
  if (filters.state) params.set('state', filters.state);
  if (filters.state && filters.municipality) params.set('municipality', String(filters.municipality.code));
  return authenticated<Results>(`${base(team)}/search?${params.toString()}`);
}
export const getProfile = (team: string, other: string) => authenticated<Profile>(`${base(team)}/teams/${part(other)}`);
export const listChallenges = (team: string, direction: 'received' | 'sent', offset = 0) =>
  authenticated<{ items: Challenge[]; has_more: boolean; can_manage: boolean }>(`${base(team)}/challenges?direction=${direction}&offset=${offset}`);
export const sendChallenge = (team: string, data: ChallengeInput) => authenticated<Challenge>(`${base(team)}/challenges`, data, 'POST');
export const decide = (team: string, challenge: string, decision: 'accept' | 'reject' | 'cancel') => authenticated<Challenge>(`${base(team)}/challenges/${part(challenge)}/${decision}`, {}, 'POST');
export const listFixtures = (team: string, offset = 0) => authenticated<{ items: Fixture[]; has_more: boolean }>(`${base(team)}/fixtures?offset=${offset}`);
export const getFixture = (team: string, fixture: string) => authenticated<FixtureDetail>(`${base(team)}/fixtures/${part(fixture)}`);
export const submitScore = (team: string, fixture: string, action: 'score' | 'confirm', data: ScoreInput) => authenticated<FixtureDetail>(`${base(team)}/fixtures/${part(fixture)}/${action}`, data, 'POST');
export const sendReview = (team: string, fixture: string, data: ReviewInput) => authenticated<FixtureDetail>(`${base(team)}/fixtures/${part(fixture)}/review`, data, 'POST');

export const categories: Record<Category, string> = { female: 'Feminino', male: 'Masculino', mixed: 'Misto', all: 'Todas as categorias' };
export const tiers: Record<Result['tier'], string> = { city: 'Times próximos: sua cidade', state: 'Busca ampliada: seu estado', other: 'Busca ampliada: outros estados' };
export const challengeLabels: Record<ChallengeStatus, string> = { PENDING: 'PENDENTE', ACCEPTED: 'ACEITO', REJECTED: 'RECUSADO', CANCELLED: 'CANCELADO', EXPIRED: 'EXPIRADO' };
export const resultLabels: Record<ResultStatus, string> = { NONE: 'AGUARDANDO PLACAR', PENDING: 'AGUARDANDO CONFIRMAÇÃO', VALIDATED: 'RESULTADO VALIDADO', DISPUTED: 'EM DIVERGÊNCIA' };
export const when = (date: string, time: string) => `${date.split('-').reverse().join('/')} • ${time.slice(0, 5)}`;
export const scoreLine = (item: Fixture, score: { home_score: number; away_score: number }) => `${item.home_team.name} ${score.home_score} x ${score.away_score} ${item.away_team.name}`;
export const message = (cause: unknown, fallback: string) => cause instanceof Error ? cause.message : fallback;
