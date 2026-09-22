import { useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { Field, FormError, TextAction } from '../components/AuthLayout';
import { Button, Card } from '../components/ui';
import { ApiError } from '../auth/api';
import { savePerson, similarPlayers, type RosterPerson, type PlayerInput, type SimilarPlayer } from './api';
import { rosterStyles as styles } from './styles';

export function PlayerForm({ teamId, player, onSaved, onCancel, onDenied }: {
  teamId: string; player?: RosterPerson; onSaved: (person: RosterPerson) => void;
  onCancel: () => void; onDenied: () => void;
}) {
  const [name, setName] = useState(player?.name ?? '');
  const [nickname, setNickname] = useState(player?.nickname ?? '');
  const [phone, setPhone] = useState(player?.phone ?? '');
  const [email, setEmail] = useState(player?.email ?? '');
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [matches, setMatches] = useState<SimilarPlayer[] | null>(null);
  const linked = player?.account_linked ?? false;
  function changed(setter: (value: string) => void, value: string) { setter(value); setMatches(null); setError(null); }

  async function submit(confirmed = false) {
    if (locked.current) return;
    if (!linked && !name.trim()) { setError('Informe o nome do jogador.'); return; }
    const data: PlayerInput = linked ? { nickname: nickname.trim() || null } : {
      name: name.trim(), nickname: nickname.trim() || null, phone: phone.trim() || null, email: email.trim() || null,
    };
    locked.current = true; setBusy(true); setError(null);
    try {
      if (!linked && !confirmed) {
        const found = await similarPlayers(teamId, data, player?.membership_id);
        if (found.length) { setMatches(found); return; }
      }
      onSaved(await savePerson(teamId, { ...data, confirm_duplicate: confirmed }, player?.membership_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível salvar o jogador.');
      if (cause instanceof ApiError && (cause.status === 403 || cause.status === 404)) onDenied();
      // Recheck if another manager added a matching player between check and save.
      if (!linked && cause instanceof ApiError && cause.status === 409 && !confirmed) {
        try { const found = await similarPlayers(teamId, data, player?.membership_id); if (found.length) setMatches(found); } catch { /* Keep original actionable error. */ }
      }
    } finally { locked.current = false; setBusy(false); }
  }

  return <View style={styles.stack}>
    <Text accessibilityRole="header" style={styles.heading}>{player ? 'Editar jogador' : 'Adicionar jogador'}</Text>
    {linked ? <Text style={styles.note}>Nome e contatos da conta são controlados pelo próprio jogador. Aqui você pode editar o apelido neste time.</Text> : <Field label="Nome do jogador" value={name} onChangeText={value => changed(setName, value)} maxLength={80} autoCapitalize="words" editable={!busy} />}
    <Field label="Apelido (opcional)" value={nickname} onChangeText={value => changed(setNickname, value)} maxLength={80} editable={!busy} />
    {!linked && <>
      <Field label="Telefone (opcional)" value={phone} onChangeText={value => changed(setPhone, value)} keyboardType="phone-pad" maxLength={80} editable={!busy} />
      <Field label="E-mail (opcional)" value={email} onChangeText={value => changed(setEmail, value)} keyboardType="email-address" maxLength={254} editable={!busy} />
    </>}
    <Text style={styles.note}>Foto opcional. O envio de imagens estará disponível em uma próxima etapa.</Text>
    <FormError message={error} />
    {matches ? <Card><View style={styles.stack}>
      <Text accessibilityRole="alert" style={styles.label}>Encontramos um jogador parecido neste elenco.</Text>
      {matches.map(match => <Text key={match.membership_id} style={styles.note}>{match.name} · {match.status === 'active' ? 'Ativo' : 'Inativo'} · Coincidência: {match.reasons.join(', ')}</Text>)}
      <Text style={styles.note}>Confira nome e contatos. Continuar cria ou mantém um cadastro separado, sem vincular contas.</Text>
      <Button label={busy ? 'Salvando…' : player ? 'Salvar mesmo assim' : 'Adicionar mesmo assim'} disabled={busy} onPress={() => void submit(true)} />
      <TextAction label="Cancelar" onPress={() => setMatches(null)} disabled={busy} />
    </View></Card> : <Button label={busy ? 'Salvando…' : 'Salvar jogador'} disabled={busy} onPress={() => void submit()} />}
    <TextAction label="Voltar ao elenco" onPress={onCancel} disabled={busy} />
  </View>;
}
