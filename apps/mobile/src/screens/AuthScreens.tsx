import { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import * as api from '../auth/api';
import { AuthLayout, Field, FormError, TextAction, authStyles } from '../components/AuthLayout';
import { Avatar, Badge, Button, LoadingState } from '../components/ui';

export function AuthScreens() {
  const auth = useAuth();
  const [screen, setScreen] = useState<'welcome' | 'login' | 'register'>(auth.startAtLogin ? 'login' : 'welcome');
  const [name, setName] = useState('');
  const [contact, setContact] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [phone, setPhone] = useState(false);
  const [code, setCode] = useState('');
  const [changing, setChanging] = useState(false);
  const [wait, setWait] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setWait(auth.ticket?.resend_after || 0); setCode(''); setChanging(false); }, [auth.ticket]);
  useEffect(() => {
    if (!auth.ticket) return;
    const interval = setInterval(() => setWait(value => Math.max(0, value - 1)), 1000);
    return () => clearInterval(interval);
  }, [auth.ticket]);

  function go(next: typeof screen) {
    setScreen(next); setError(null); setPassword(''); setConfirmation('');
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(null);
    try { await action(); }
    catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Não foi possível concluir. Tente novamente.');
      if (failure instanceof api.ApiError && failure.retryAfter) setWait(failure.retryAfter);
    } finally { setBusy(false); }
  }
  async function submit() {
    if (!contact.trim() || !password) { setError('Informe seu contato e sua senha.'); return; }
    if (screen === 'register') {
      if (!name.trim()) { setError('Informe seu nome.'); return; }
      if (password.length < 8) { setError('Use uma senha com pelo menos 8 caracteres.'); return; }
      if (password !== confirmation) { setError('As senhas não coincidem.'); return; }
    }
    await perform(async () => {
      const result = screen === 'register' ? await api.register(name, contact, password, confirmation)
        : await api.login(contact, password);
      setPassword(''); setConfirmation('');
      await auth.finish(result);
    });
  }

  if (auth.booting || auth.bootError) return <AuthLayout title="Seu time. Seu jogo.">
    {auth.booting ? <LoadingState label="Preparando sua entrada…" /> : <>
      <FormError message={auth.bootError} />
      <Button label="Tentar novamente" onPress={() => void auth.restore()} />
    </>}
  </AuthLayout>;

  if (auth.profile && !auth.profile.player_id) return <AuthLayout title="Como você quer ser chamado?" description="Só falta seu nome para entrar em campo.">
    <View style={authStyles.center}><Avatar name={name || 'Jogador'} /><Text style={authStyles.note}>Foto opcional. Você poderá adicioná-la em uma próxima etapa.</Text></View>
    <Field label="Nome" value={name} onChangeText={setName} maxLength={80} autoCapitalize="words" editable={!busy} />
    <FormError message={error} />
    <Button label={busy ? 'Salvando…' : 'Continuar sem foto'} disabled={busy || !name.trim()} onPress={() => void perform(() => auth.complete(name))} />
  </AuthLayout>;

  if (auth.ticket) {
    const ticket = auth.ticket;
    return <AuthLayout title="Confirme seu contato" description={`Enviamos um código para ${ticket.masked_contact}.`}>
      <Field label="Código de 6 dígitos" value={code} onChangeText={value => setCode(value.replace(/\D/g, '').slice(0, 6))}
        keyboardType="number-pad" autoComplete="one-time-code" textContentType="oneTimeCode" maxLength={6} placeholder="000000" editable={!busy} />
      {__DEV__ && ticket.development_code && <View style={{ gap: 8 }}>
        <Badge label="AMBIENTE LOCAL" />
        <Text selectable style={authStyles.note}>Código de desenvolvimento: {ticket.development_code}</Text>
        <Text style={authStyles.note}>Nenhuma mensagem externa foi enviada.</Text>
      </View>}
      <FormError message={error} />
      <Button label={busy ? 'Aguarde…' : 'Confirmar'} disabled={busy || code.length !== 6}
        onPress={() => void perform(async () => auth.finish(await api.verify(ticket, code)))} />
      <TextAction label={wait ? `Reenviar código em ${wait}s` : 'Reenviar código'} disabled={busy || wait > 0}
        onPress={() => void perform(async () => auth.setTicket(await api.resend(ticket)))} />
      {changing ? <>
        <Field label="Novo telefone ou e-mail" value={contact} onChangeText={setContact} maxLength={254} editable={!busy} />
        <Button label={wait ? `Aguarde ${wait}s para alterar` : 'Salvar contato e reenviar'} disabled={busy || wait > 0 || !contact.trim()}
          onPress={() => void perform(async () => auth.setTicket(await api.resend(ticket, contact)))} />
      </> : <TextAction label="Alterar telefone/e-mail" disabled={busy} onPress={() => { setContact(''); setChanging(true); setError(null); }} />}
      <TextAction label="Voltar ao login" disabled={busy} onPress={() => { auth.setTicket(null); go('login'); }} />
    </AuthLayout>;
  }

  if (screen === 'welcome') return <AuthLayout title="Entre em campo." description="Seu futebol, mais organizado. Faça parte do ELEVEN BR.">
    <Button label="Criar minha conta" onPress={() => go('register')} />
    <TextAction label="Já tenho conta" onPress={() => go('login')} />
  </AuthLayout>;

  return <AuthLayout title={screen === 'register' ? 'Seu primeiro passo.' : 'Bom ter você de volta.'}
    description={screen === 'register' ? 'Crie sua conta e confirme seu contato para começar.' : 'Entre com seu telefone ou e-mail.'}>
    {screen === 'register' && <>
      <Field label="Nome" value={name} onChangeText={setName} maxLength={80} autoCapitalize="words" autoComplete="name" editable={!busy} />
      <View style={authStyles.row}>
        <TextAction label={phone ? 'Usar e-mail' : 'E-mail selecionado'} disabled={busy} onPress={() => { setPhone(false); setContact(''); }} />
        <TextAction label={phone ? 'Celular selecionado' : 'Usar celular'} disabled={busy} onPress={() => { setPhone(true); setContact(''); }} />
      </View>
    </>}
    <Field label={screen === 'login' ? 'Telefone ou e-mail' : phone ? 'Celular com DDD' : 'E-mail'} value={contact}
      onChangeText={setContact} maxLength={254} editable={!busy}
      placeholder={screen === 'register' && phone ? '(11) 99999-9999' : undefined}
      keyboardType={screen === 'register' ? phone ? 'phone-pad' : 'email-address' : 'default'}
      autoComplete={screen === 'register' ? phone ? 'tel' : 'email' : 'username'} />
    <Field label="Senha" value={password} onChangeText={setPassword} password maxLength={128} editable={!busy}
      autoComplete={screen === 'register' ? 'new-password' : 'current-password'} />
    {screen === 'register' && <>
      <Text style={authStyles.note}>Pelo menos 8 caracteres.</Text>
      <Field label="Confirmar senha" value={confirmation} onChangeText={setConfirmation} password maxLength={128} editable={!busy} autoComplete="new-password" />
    </>}
    <FormError message={error} />
    <Button label={busy ? 'Aguarde…' : screen === 'register' ? 'Criar minha conta' : 'Entrar'} disabled={busy} onPress={() => void submit()} />
    <TextAction label={screen === 'register' ? 'Já tenho conta' : 'Criar minha conta'} disabled={busy} onPress={() => go(screen === 'register' ? 'login' : 'register')} />
  </AuthLayout>;
}
