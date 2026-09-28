import { useRef, useState } from 'react';
import { Text } from 'react-native';
import * as api from '../auth/api';
import { AuthLayout, Field, FormError, TextAction, authStyles } from '../components/AuthLayout';
import { Button } from '../components/ui';

export function PasswordRecovery({ onBack }: { onBack: () => void }) {
  const [email, setEmail] = useState(''), [code, setCode] = useState('');
  const [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState('');
  const [ticket, setTicket] = useState<api.RecoveryTicket | null>(null);
  const [done, setDone] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null), locked = useRef(false);
  async function submit() {
    if (locked.current) return;
    if (ticket && (password.length < 8 || password !== confirmation)) { setError('Use ao menos 8 caracteres e confirme a mesma senha.'); return; }
    locked.current = true; setBusy(true); setError(null);
    try {
      if (!ticket) setTicket(await api.recoverPassword(email));
      else { await api.resetPassword(ticket, code, password, confirmation); setPassword(''); setConfirmation(''); setTicket(null); setDone(true); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível recuperar a senha.'); }
    finally { locked.current = false; setBusy(false); }
  }
  return <AuthLayout title={done ? 'Senha atualizada' : 'Recuperar senha'} description={done ? 'Entre novamente com sua nova senha.' : 'Use o e-mail verificado da sua conta.'}>
    {!done && <>
      {!ticket ? <Field label="E-mail da conta" value={email} onChangeText={setEmail} keyboardType="email-address" autoComplete="email" maxLength={254} editable={!busy} /> : <>
        <Text style={authStyles.note}>{ticket.message} O código vale por 10 minutos.</Text>
        <Field label="Código de recuperação" value={code} onChangeText={value => setCode(value.replace(/\D/g, '').slice(0, 6))} maxLength={6} keyboardType="number-pad" autoComplete="one-time-code" editable={!busy} />
        {__DEV__ && ticket.development_code && <Text selectable style={authStyles.note}>Código de desenvolvimento: {ticket.development_code}</Text>}
        <Field label="Nova senha" password value={password} onChangeText={setPassword} maxLength={128} autoComplete="new-password" editable={!busy} />
        <Field label="Confirmar nova senha" password value={confirmation} onChangeText={setConfirmation} maxLength={128} autoComplete="new-password" editable={!busy} />
      </>}
      <FormError message={error} />
      <Button label={busy ? 'Aguarde…' : ticket ? 'Salvar nova senha' : 'Enviar código'} disabled={busy || (!ticket ? !email.trim() : code.length !== 6)} onPress={() => void submit()} />
      {ticket && <TextAction label="Solicitar outro código" disabled={busy} onPress={() => { setTicket(null); setCode(''); setError(null); }} />}
    </>}
    <TextAction label="Voltar ao login" disabled={busy} onPress={onBack} />
  </AuthLayout>;
}
