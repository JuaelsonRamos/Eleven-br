import { useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { Badge, Button, Card, FilterChip } from '../components/ui';
import { FormError, TextAction } from '../components/AuthLayout';
import { ApiError } from '../auth/api';
import { HelpShortcut } from '../help/HelpShortcut';
import { roles, transferPresidency, type Team } from '../teams/api';
import { permissionAreas, saveRole, type RosterPage, type RosterPerson } from './api';
import { rosterStyles as s } from './styles';

const areaLabel = (value: string) => permissionAreas.find(area => area.value === value)?.label ?? value;

/** President-only controls. The API revalidates role, plan, eligibility and versions. */
export function TeamRolePanel({ team, page, player, onChanged, onTransferred, onDenied }: {
  team: Team; page: RosterPage; player: RosterPerson;
  onChanged: (player: RosterPerson, message: string) => void;
  onTransferred: (team: Team, message: string) => void;
  onDenied: () => void;
}) {
  const [step, setStep] = useState<'view' | 'admin' | 'transfer'>('view');
  const [areas, setAreas] = useState<string[]>([]);
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  const pro = page.plan !== 'free';
  const eligible = player.status === 'active' && player.account_linked;
  const full = player.role !== 'admin' && page.admin_count >= page.admin_limit;
  async function run(action: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(null);
    try { await action(); }
    catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível concluir.');
      if (cause instanceof ApiError && (cause.status === 403 || cause.status === 404)) onDenied();
    } finally { lock.current = false; setBusy(false); }
  }
  function open(next: 'view' | 'admin' | 'transfer') {
    setAreas(player.role === 'admin' ? player.permissions : []); setError(null); setStep(next);
  }
  return <Card><View style={s.stack}>
    <Text accessibilityRole="header" style={s.label}>Função no time</Text>
    <View style={s.row}>
      <Badge label={roles[player.role]} tone={player.role === 'admin' ? 'exempt' : 'neutral'} />
      {player.role === 'admin' && player.permissions.map(value => <Badge key={value} label={areaLabel(value)} tone="neutral" />)}
    </View>
    {step === 'admin' ? <>
      <Text style={s.note}>Escolha as áreas que {player.name} poderá gerenciar neste time.</Text>
      <View style={s.row}>{permissionAreas.map(area => <FilterChip key={area.value} role="checkbox" label={area.label} selected={areas.includes(area.value)} disabled={busy}
        onPress={() => setAreas(current => current.includes(area.value) ? current.filter(value => value !== area.value) : [...current, area.value])} />)}</View>
      <FormError message={error} />
      <Button label={busy ? 'Salvando…' : 'Salvar administração'} disabled={busy || !areas.length}
        onPress={() => void run(async () => onChanged(await saveRole(team.id, player, 'admin', areas), 'Administração salva.'))} />
      <TextAction label="Cancelar" disabled={busy} onPress={() => open('view')} />
    </> : step === 'transfer' ? <>
      <Text accessibilityRole="header" style={s.heading}>Transferir a Presidência para {player.name}?</Text>
      <Text style={s.note}>Após confirmar, {player.name} passará a ser o Presidente deste time.</Text>
      <Text style={s.note}>Você continuará no time como jogador, sem os poderes de Presidente. Seus dados, estatísticas e histórico serão preservados.</Text>
      <FormError message={error} />
      <Button variant="danger" label={busy ? 'Transferindo…' : 'Confirmar transferência'} disabled={busy}
        onPress={() => void run(async () => onTransferred(await transferPresidency(team.id, player.membership_id), `Presidência transferida para ${player.name}.`))} />
      <TextAction label="Cancelar" disabled={busy} onPress={() => open('view')} />
    </> : <>
      {!pro ? <Text style={s.note}>Administradores são um recurso ELEVEN PRO. No Free, somente o Presidente administra o time.</Text>
        : !eligible ? <Text style={s.note}>Somente jogadores ativos e com conta no ELEVEN BR podem administrar o time ou assumir a Presidência.</Text>
        : full ? <Text style={s.note}>Limite de {page.admin_limit} administradores atingido. Remova a administração de alguém para liberar uma vaga.</Text> : null}
      <FormError message={error} />
      {pro && eligible && !full && <Button label={player.role === 'admin' ? 'Editar administração' : 'Tornar administrador'} disabled={busy} onPress={() => open('admin')} />}
      {player.role === 'admin' && <TextAction label="Remover administração" disabled={busy}
        onPress={() => void run(async () => onChanged(await saveRole(team.id, player, 'member', []), 'Administração removida.'))} />}
      {eligible && <Button variant="secondary" label="Transferir Presidência" disabled={busy} onPress={() => open('transfer')} />}
      <HelpShortcut topic="administrators" label="Como funcionam administradores e Presidência?" />
    </>}
  </View></Card>;
}
