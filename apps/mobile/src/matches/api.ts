import { authenticated } from '../auth/api';
export type Match = { id: string; formation_id: string; home_formation_team_id: string; away_formation_team_id: string;
  home_score: number; away_score: number; version: number; status: 'SCHEDULED' | 'IN_PROGRESS' | 'FINISHED' | 'CANCELLED';
  corrected_at: string | null; updated_at: string };
const path = (team: string, event: string) => `/v1/teams/${encodeURIComponent(team)}/events/${encodeURIComponent(event)}/matches`;
export const getMatches = (team: string, event: string) => authenticated<Match[]>(path(team, event));
export const createMatch = (team: string, event: string, formation: string, version: number, home: string, away: string) =>
  authenticated<Match>(path(team, event), { formation_id: formation, expected_formation_version: version,
    home_formation_team_id: home, away_formation_team_id: away }, 'POST');
export const changeMatch = (team: string, event: string, match: Match, action: 'start' | 'score' | 'finish' | 'cancel',
  confirm = false, home = match.home_score, away = match.away_score) => authenticated<Match>(`${path(team, event)}/${match.id}/${action}`,
  { expected_version: match.version, confirm, ...(action === 'score' ? { home_score: home, away_score: away } : {}) }, action === 'score' ? 'PUT' : 'POST');
