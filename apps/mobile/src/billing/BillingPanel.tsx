import { useCallback, useEffect, useRef, useState } from 'react';
import { Image, Linking, StyleSheet, Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Field, FormError } from '../components/AuthLayout';
import { Badge, Button, Card, FilterChip, LoadingState, SecondaryButton } from '../components/ui';
import { useAuth } from '../auth/AuthContext';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';
import * as api from './api';

const statuses: Record<string, string> = { FREE: 'Plano gratuito', PENDING: 'Pagamento inicial pendente', ACTIVE: 'Ativo', OVERDUE: 'Pagamento pendente', CANCELLED: 'Assinatura cancelada', SUSPENDED: 'Recursos Pro suspensos', ADMIN_GRANTED: 'Pro administrativo', EXPIRED: 'Tempo para contratação expirado.', RECONCILIATION: 'Pagamento em conciliação' };
const money = (value: string) => `R$ ${Number(value).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const clock = (seconds: number) => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
function when(value: string) {
  // Preserve the provider's local calendar date instead of converting midnight to yesterday.
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}:\d{2}))?/.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}${match[4] ? ` às ${match[4]}` : ''}` : value;
}
export function BillingPanel({ teamId }: { teamId: string }) {
  const { profile } = useAuth();
  const { selected, reload } = useTeams();
  const [data, setData] = useState<api.Billing | null>(null), [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false), [form, setForm] = useState(false), [cancel, setCancel] = useState(false);
  const [method, setMethod] = useState<'PIX' | 'CREDIT_CARD'>('PIX');
  const [name, setName] = useState(profile?.display_name ?? ''), [email, setEmail] = useState(profile?.email ?? ''), [document, setDocument] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const alive = useRef(true), lock = useRef(false), command = useRef('');
  const [remaining, setRemaining] = useState<number | null>(null);
  const refreshedAt = useRef<string | null>(null);
  useEffect(() => {
    alive.current = true;
    async function load() {
      try {
        const value = await api.getBilling(teamId);
        if (!alive.current) return;
        setData(value);
        // Resume an existing payment once on entry; never create another checkout or poll.
        if (value.can_manage && value.can_cancel) {
          lock.current = true; setBusy(true);
          const payment = await api.refreshBilling(teamId);
          if (alive.current) setData(payment);
        }
      } catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : 'Não foi possível carregar a assinatura.'); }
      finally { lock.current = false; if (alive.current) setBusy(false); }
    }
    void load();
    return () => { alive.current = false; };
  }, [teamId]);
  const run = useCallback(async (action: () => Promise<api.Billing>) => {
    if (lock.current) return; lock.current = true; setBusy(true); setError(null); setNotice(null);
    try { const value = await action(); if (alive.current) { setData(value); setForm(false); setCancel(false); if (selected?.id === teamId && selected.plan !== value.plan) void reload(); } }
    catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : 'Não foi possível concluir.'); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }, [reload, selected?.id, selected?.plan, teamId]);
  useEffect(() => {
    // Any live initial attempt counts down, even when its charge is shown as OVERDUE after midnight.
    if (!data?.signup_expires_at || !data.can_manage || !data.can_cancel || data.status === 'RECONCILIATION') { setRemaining(null); return; }
    // Counts down to the backend deadline on the server clock; the device clock cannot extend it.
    const deadline = Date.parse(data.signup_expires_at);
    const offset = Date.parse(data.server_time) - Date.now();
    const tick = () => setRemaining(Math.max(0, Math.ceil((deadline - Date.now() - offset) / 1000)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [data?.signup_expires_at, data?.server_time, data?.can_manage, data?.can_cancel, data?.status]);
  useEffect(() => {
    // At zero, ask the backend once per snapshot to close the attempt; it decides, never the timer.
    if (remaining !== 0 || busy || !data || data.signup_expired || refreshedAt.current === data.server_time) return;
    refreshedAt.current = data.server_time;
    void run(() => api.refreshBilling(teamId));
  }, [remaining, busy, data, run, teamId]);
  const expired = Boolean(data?.signup_expired || remaining === 0);
  const cardAvailable = data?.available_payment_methods?.includes('CREDIT_CARD') ?? false;
  const paymentMethod = cardAvailable ? method : 'PIX';
  async function submit() {
    try { return await api.checkout(teamId, { command_id: command.current, method: cardAvailable ? method : 'PIX', name, email, cpf_cnpj: document }); }
    catch (cause) {
      // A fresh command lets the President fix data or switch method; the backend reuses any live attempt.
      const fresh = await api.getBilling(teamId).catch(() => null);
      if (fresh && alive.current) { command.current = fresh.command_id; setData(fresh); }
      throw cause;
    }
  }
  if (!data) return <><FormError message={error} />{error ? <Button label="Tentar novamente" onPress={() => void run(() => api.getBilling(teamId))} /> : <LoadingState />}</>;
  return <View style={s.stack}>
    <Text accessibilityRole="header" style={s.title}>ELEVEN BR PRO</Text>
    <Card><Badge label={data.plan === 'pro' ? 'ELEVEN PRO ATIVO' : 'FREE'} />
      <Text style={s.title}>{money(data.price)}/mês<Text style={s.body}> por time</Text></Text>
      <Text style={s.body}>{remaining === 0 ? statuses.EXPIRED : statuses[data.status] ?? data.status}</Text>
      {remaining !== null && !expired && <Text accessibilityRole="timer" style={s.heading}>Tempo para concluir esta contratação: {clock(remaining)}</Text>}
      {data.expires_at && <Text style={s.note}>{data.status === 'ADMIN_GRANTED' ? 'Concessão válida até' : 'Período pago até'} {when(data.expires_at)}</Text>}
      {data.plan === 'pro' && data.next_due_date && <Text style={s.note}>Próxima cobrança: {when(data.next_due_date)}</Text>}
      <Text style={s.body}>Escalações visuais · Até 100 jogadores ativos · Até 5 administradores com permissões por área</Text>
      <Text style={s.note}>Free · R$ 0. Até 24 jogadores e administração pelo Presidente.</Text>
    </Card>
    <FormError message={error} />
    {(data.warning || data.notice || notice) && <Text accessibilityRole="alert" style={s.body}>{data.warning || data.notice || notice}</Text>}
    {!data.can_manage ? <><Text style={s.note}>Somente o Presidente do time pode contratar ou gerenciar o ELEVEN BR PRO.</Text><SecondaryButton label="Atualizar plano" disabled={busy} onPress={() => void run(() => api.getBilling(teamId))} /></> : <>
      {data.plan === 'pro' && data.status === 'CANCELLED' && <Text style={s.note}>A renovação foi cancelada. O PRO continua até o fim do período pago; depois, você pode assinar novamente.</Text>}
      {data.plan !== 'pro' && data.status !== 'RECONCILIATION' && !data.can_cancel && !form && <Button label={data.can_retry_pix ? 'Gerar novo Pix' : 'ASSINAR ELEVEN PRO'} onPress={() => { command.current = data.command_id; setMethod('PIX'); setForm(true); }} disabled={busy} />}
      {form && <Card><Text style={s.heading}>{cardAvailable ? 'Como deseja pagar?' : 'Pagamento disponível: PIX'}</Text>
        <View style={s.row}><FilterChip label="PIX" selected={!cardAvailable || method === 'PIX'} onPress={() => setMethod('PIX')} disabled={busy} />{cardAvailable && <FilterChip label="Cartão de crédito" selected={method === 'CREDIT_CARD'} onPress={() => setMethod('CREDIT_CARD')} disabled={busy} />}</View>
        <Field label="Nome do responsável pelo pagamento" value={name} onChangeText={setName} editable={!busy} />
        <Field label="E-mail de cobrança" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" editable={!busy} />
        <Field label="CPF ou CNPJ do pagador" value={document} onChangeText={value => setDocument(value.replace(/\D/g, ''))} keyboardType="number-pad" maxLength={14} editable={!busy} />
        <Text style={s.note}>{paymentMethod === 'PIX' ? `Uma cobrança Pix de ${money(data.price)} será gerada a cada mês. Você paga manualmente; não há débito automático.` : `Assinatura mensal de ${money(data.price)}. Você informará o cartão na página segura do Asaas, responsável pelas cobranças recorrentes.`}</Text>
        <Button label={paymentMethod === 'PIX' ? 'Confirmar assinatura e gerar Pix' : 'Confirmar e continuar no Asaas'} disabled={busy || !name.trim() || !email.trim() || ![11, 14].includes(document.length)} onPress={() => void run(submit)} />
        <SecondaryButton label="Voltar" disabled={busy} onPress={() => setForm(false)} />
      </Card>}
      {data.pix && !expired && <Card><Text style={s.heading}>Pix · {money(data.pix.amount)}</Text>
        {/* The initial attempt follows only the countdown above; renewals show the charge dates. */}
        {!data.signup_expires_at && <><Text style={s.body}>Aguardando pagamento</Text>
          {data.next_due_date && <Text style={s.note}>Vencimento: {when(data.next_due_date)}</Text>}
          {data.pix.expires_at && <Text style={s.note}>Código válido até {when(data.pix.expires_at)}</Text>}</>}
        {data.pix.image && <Image source={{ uri: `data:image/png;base64,${data.pix.image}` }} style={s.qr} accessibilityLabel="QR Code Pix da assinatura" />}
        {data.pix.payload && <><Text selectable style={s.code}>{data.pix.payload}</Text>
        <Button label="Copiar código Pix" onPress={() => { void Clipboard.setStringAsync(data.pix!.payload!).then(() => { if (alive.current) setNotice('Código Pix copiado.'); }).catch(() => { if (alive.current) setError('Selecione o código e copie manualmente.'); }); }} /></>}
      </Card>}
      {cardAvailable && data.checkout_url && <Button label="Abrir pagamento seguro no Asaas" disabled={busy} onPress={() => { void Linking.openURL(data.checkout_url!).catch(() => setError('Não foi possível abrir o Asaas.')); }} />}
      {(data.checkout_url || (data.pix && !expired)) && <Text style={s.note}>Após pagar, volte ao ELEVEN BR e atualize a assinatura. O Pro será liberado somente após a confirmação do pagamento pelo backend.</Text>}
      <SecondaryButton label="Atualizar assinatura" disabled={busy} onPress={() => void run(() => api.refreshBilling(teamId))} />
      {data.can_cancel && !expired && data.status !== 'RECONCILIATION' && !cancel && <SecondaryButton label="Cancelar assinatura" disabled={busy} onPress={() => setCancel(true)} />}
      {cancel && <Card><Text style={s.heading}>Cancelar a assinatura?</Text><Text style={s.body}>Novas cobranças serão interrompidas. Seu time mantém o Pro até o fim do período já pago. Seus dados e histórico serão preservados.</Text>
        <Button label="Confirmar cancelamento" variant="danger" disabled={busy} onPress={() => void run(() => api.cancelBilling(teamId))} />
        <SecondaryButton label="Manter assinatura" disabled={busy} onPress={() => setCancel(false)} />
      </Card>}
    </>}
    {busy && <LoadingState label="Confirmando operação…" />}
  </View>;
}
const s = StyleSheet.create({
  stack: { gap: theme.space.lg }, row: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.space.sm },
  title: { fontFamily: theme.fontFamily, color: theme.colors.green, fontSize: 26, fontWeight: '800' },
  heading: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: 18, fontWeight: '700' },
  body: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: 15, lineHeight: 22 },
  note: { fontFamily: theme.fontFamily, color: theme.colors.muted, fontSize: 13, lineHeight: 20 },
  code: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: 12, flexShrink: 1 },
  qr: { width: '100%', maxWidth: 240, aspectRatio: 1, alignSelf: 'center', resizeMode: 'contain' },
});
