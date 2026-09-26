import { authenticated } from '../auth/api';

export type Period = 'all' | 'month' | 'last30' | 'year';
export type Totals = { matches: number; goals: number; assists: number; yellow_cards: number; red_cards: number };
export type Person = {
  id: string; kind: 'member' | 'guest'; name: string; player_id: string | null;
  photo_url: string | null; inactive: boolean; event_date: string | null; totals: Totals;
  goals_position: number | null; assists_position: number | null;
};
export type Page = {
  summary: Totals; players: Person[]; scorers: Person[]; assistants: Person[]; discipline: Person[];
  modalities: string[]; period: Period; modality: string | null;
};
export type History = {
  match_id: string; event_id: string; date: string; title: string; modality: string;
  home_number: number; away_number: number; home_score: number; away_score: number;
  goals: number; assists: number; yellow_cards: number; red_cards: number;
};
export type Profile = { person: Person; goals_per_match: number; assists_per_match: number; history: History[]; has_more: boolean };
export const periods: { value: Period; label: string }[] = [
  { value: 'all', label: 'Todos' }, { value: 'month', label: 'Este mês' },
  { value: 'last30', label: 'Últimos 30 dias' }, { value: 'year', label: 'Este ano' },
];
const root = (team: string) => `/v1/teams/${encodeURIComponent(team)}/statistics`;
const query = (period: Period, modality: string) => `period=${period}${modality ? `&modality=${encodeURIComponent(modality)}` : ''}`;
export const overview = (team: string, period: Period, modality: string) => authenticated<Page>(`${root(team)}?${query(period, modality)}`);
export const profile = (team: string, person: Person, period: Period, modality: string, offset = 0) =>
  authenticated<Profile>(`${root(team)}/${person.kind === 'member' ? 'players' : 'guests'}/${encodeURIComponent(person.id)}?${query(period, modality)}&offset=${offset}`);
