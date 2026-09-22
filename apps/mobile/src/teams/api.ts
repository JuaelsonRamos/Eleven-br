import { authenticated } from '../auth/api';

export type TeamInput = { name: string; city: string; state: string; modalities: string[] };
export type PublicTeam = TeamInput & { code: string };
export type Team = PublicTeam & {
  id: string; status: string; plan: 'free' | 'pro'; crest_url: string | null;
  my_role: 'president' | 'admin' | 'member'; can_edit: boolean;
};
export type Choice = { value: string; label: string };
export type Options = { modalities: Choice[]; states: Choice[] };
export const modalityLabels = (values: string[], choices: Choice[]) => values
  .map(value => choices.find(item => item.value === value)?.label ?? value).join(' • ');
export const roles = { president: 'Presidente', admin: 'Administrador', member: 'Jogador' };
export const listTeams = () => authenticated<Team[]>('/v1/teams');
export const getTeam = (id: string) => authenticated<Team>(`/v1/teams/${encodeURIComponent(id)}`);
export const getOptions = () => authenticated<Options>('/v1/teams/options');
export const findSimilar = (data: TeamInput) => authenticated<PublicTeam[]>('/v1/teams/similar', data, 'POST');
export const saveTeam = (data: TeamInput, id?: string) => authenticated<Team>(
  id ? `/v1/teams/${encodeURIComponent(id)}` : '/v1/teams', data, id ? 'PUT' : 'POST',
);
