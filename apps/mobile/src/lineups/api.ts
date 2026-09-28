import { authenticated } from '../auth/api';
export type Slot = { slot: number; membership_id: string };
export type Lineup = { id?: string; title: string; modality: string; formation: string; event_id: string | null; version: number; positions: Slot[] };
export type Page = { enabled: boolean; can_manage: boolean; command_id: string; templates: Record<string, Record<string, string[][]>>; items: Pick<Required<Lineup>, 'id' | 'title' | 'modality' | 'formation'>[]; has_more: boolean };
const base = (team: string) => `/v1/teams/${encodeURIComponent(team)}/lineups`;
export const list = (team: string, offset = 0) => authenticated<Page>(`${base(team)}?offset=${offset}`);
export const detail = (team: string, id: string) => authenticated<Lineup>(`${base(team)}/${id}`);
export const save = (team: string, item: Lineup, command: string) => authenticated<Lineup>(item.id ? `${base(team)}/${item.id}` : base(team), { title: item.title, modality: item.modality, formation: item.formation, event_id: item.event_id, positions: item.positions, expected_version: item.version, command_id: command }, item.id ? 'PUT' : 'POST');
