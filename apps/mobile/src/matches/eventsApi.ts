import { authenticated } from '../auth/api';
import type { Match } from './api';

export type IncidentType = 'GOAL' | 'YELLOW_CARD' | 'RED_CARD';
export type MatchParticipant = { id: string; name: string; is_guest: boolean; squad_id: string; squad_name: string };
export type MatchIncident = { id: string; type: IncidentType; participant_id: string; assist_participant_id: string | null;
  squad_id: string; created_at: string; updated_at: string };
export type MatchEventsPage = { match: Match; can_manage: boolean; participants: MatchParticipant[]; items: MatchIncident[];
  goals: { squad_id: string; name: string; score: number; identified: number; missing: number; excess: number }[] };
export type IncidentDraft = { type: IncidentType; participant_id: string; assist_participant_id: string | null };
const path = (team: string, event: string, match: string) =>
  `/v1/teams/${encodeURIComponent(team)}/events/${encodeURIComponent(event)}/matches/${encodeURIComponent(match)}/events`;
export const getMatchEvents = (team: string, event: string, match: string) => authenticated<MatchEventsPage>(path(team, event, match));
export const saveMatchEvent = (team: string, event: string, match: Match, draft: IncidentDraft, id?: string) =>
  authenticated<MatchEventsPage>(`${path(team, event, match.id)}${id ? `/${encodeURIComponent(id)}` : ''}`,
    { ...draft, expected_version: match.version }, id ? 'PUT' : 'POST');
export const removeMatchEvent = (team: string, event: string, match: Match, id: string) =>
  authenticated<MatchEventsPage>(`${path(team, event, match.id)}/${encodeURIComponent(id)}/remove`,
    { expected_version: match.version, confirm: true }, 'POST');
export const participantLabel = (person: MatchParticipant) => `${person.is_guest ? 'Convidado: ' : ''}${person.name}`;
export const incidentLabels = { GOAL: 'Gol', YELLOW_CARD: 'Cartão amarelo', RED_CARD: 'Cartão vermelho' };
