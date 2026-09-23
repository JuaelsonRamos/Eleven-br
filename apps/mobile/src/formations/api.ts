import { authenticated } from '../auth/api';

export type Candidate = { kind: 'member' | 'guest'; source_id: string; name: string };
export type Choice = Omit<Candidate, 'name'> & { goalkeeper: boolean };
export type Participant = { id: string; membership_id: string | null; guest_id: string | null; name: string; goalkeeper: boolean };
export type Formation = { id: string; version: number; method: string; team_count: number; updated_at: string;
  squads: { id: string; number: number; name: string; participants: Participant[] }[]; excluded: Participant[] };
export type FormationPage = { can_manage: boolean; participants: Candidate[]; fingerprint: string;
  participants_changed: boolean; formation: Formation | null };
export type DrawInput = { team_count: number; participants: Choice[]; expected_fingerprint: string;
  expected_version: number | null; confirm_replace: boolean };
const path = (team: string, event: string) => `/v1/teams/${encodeURIComponent(team)}/events/${encodeURIComponent(event)}/formation`;
export const getFormation = (team: string, event: string) => authenticated<FormationPage>(path(team, event));
export const drawFormation = (team: string, event: string, input: DrawInput) => authenticated<FormationPage>(`${path(team, event)}/draw`, input, 'POST');
export const moveParticipant = (team: string, event: string, formation: Formation, person: string, squad: string) =>
  authenticated<FormationPage>(`${path(team, event)}/participants/${encodeURIComponent(person)}`,
    { formation_id: formation.id, expected_version: formation.version, squad_id: squad }, 'PUT');
export const candidateKey = (p: Candidate) => `${p.kind}:${p.source_id}`;
