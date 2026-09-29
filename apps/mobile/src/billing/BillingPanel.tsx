import { useEffect, useRef, useState } from 'react';
import { Image, Linking, StyleSheet, Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Field, FormError } from '../components/AuthLayout';
import { Badge, Button, Card, FilterChip, LoadingState, SecondaryButton } from '../components/ui';
import { useAuth } from '../auth/AuthContext';
import { useTeams } from '../teams/TeamContext';
import { theme } from '../theme';
import * as api from './api';

const statuses: Record<string, string> = { FREE: 'Plano gratuito', PENDING: 'Aguardando pagamento', ACTIVE: 'Assinatura ativa', OVERDUE: 'Pagamento pendente', CANCELLED: 'Assinatura cancelada', SUSPENDED: 'Recursos Pro suspensos', ADMIN_GRANTED: 'Pro administrativo' };
export function BillingPanel({ teamId }: { teamId: string }) {
  const { profile } = useAuth();
  const { selected, reload } = useTeams();
  const [data, setData] = useState<api.Billing | null>(null), [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false), [form, setForm] = useState(false), [cancel, setCancel] = useState(false);
  const [method, setMethod] = useState<'PIX' | 'CREDIT_CARD'>('PIX');
  const [name, setName] = useState(profile?.display_name ?? ''), [email, setEmail] = useState(profile?.email ?? ''), [document, setDocument] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const alive = useRef(true), lock = useRef(false), command = useRef('');
  useEffect(() => { alive.current = true; void api.getBilling(teamId).then(value => { if (alive.current) setData(value); }).catch(cause => { if (alive.current) setError(cause.message); }); return () => { alive.current = false; }; }, [teamId]);
  async function run(action: () => Promise<api.Billing>) {
    if (lock.current) return; lock.current = true; setBusy(true); setError(null); setNotice(null);
    try { const value = await action(); if (alive.current) { setData(value); setForm(false); setCancel(false); if (selected?.id === teamId && selected.plan !== value.plan) void reload(); } }
    catch (cause) { if (alive.current) setError(cause instanceof Error ? cause.message : 'Não foi possível concluir.'); }
    finally { lock.current = false; if (alive.current) setBusy(false); }
  }
  if (!data) return <><FormError message={error} />{error ? <Button label="Tentar novamente" onPress={() => void run(() => api.getBilling(teamId))} /> : <LoadingState />}</>;
  return <View style={s.stack}>
    <Text style={s.title}>ELEVEN PRO</Text>
    <Card><Badge label={data.plan === 'pro' ? 'ELEVEN PRO ATIVO' : 'FREE'} />
      <Text style={s.title}>R$ 30<Text style={s.body}> / mês por time</Text></Text>
      <Text style={s.body}>{statuses[data.status] ?? data.status}</Text>
      {data.expires_at && <Text style={s.note}>Período pago até {data.expires_at.slice(0, 10).split('-').reverse().join('/')}</Text>}
      {data.next_due_date && <Text style={s.note}>Próxima cobrança: {data.next_due_date.split('-').reverse().join('/')}</Text>}
      <Text style={s.body}>Escalações visuais · Até 100 jogadores ativos · Até 5 administradores com permissões por área</Text>
      <Text style={s.note}>Free · R$ 0. Até 24 jogadores e administração pelo Presidente.</Text>
    </Card>
    <FormError message={error} />
    {(data.warning || data.notice || notice) && <Text accessibilityRole="alert" style={s.body}>{data.warning || data.notice || notice}</Text>}
    {!data.can_manage ? <Text style={s.note}>Somente o Presidente pode contratar ou cancelar o Pro deste time.</Text> : <>
      {data.status !== 'ADMIN_GRANTED' && !data.can_cancel && !form && <Button label="ASSINAR ELEVEN PRO" onPress={() => { command.current = data.command_id; setForm(true); }} disabled={busy} />}
      {form && <Card><Text style={s.heading}>Como deseja pagar?</Text>
        <View style={s.row}><FilterChip label="PIX" selected={method === 'PIX'} onPress={() => setMethod('PIX')} disabled={busy} /><FilterChip label="Cartão de crédito" selected={method === 'CREDIT_CARD'} onPress={() => setMethod('CREDIT_CARD')} disabled={busy} /></View>
        <Field label="Nome do responsável pelo pagamento" value={name} onChangeText={setName} editable={!busy} />
        <Field label="E-mail de cobrança" value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" editable={!busy} />
        <Field label="CPF ou CNPJ do pagador" value={document} onChangeText={value => setDocument(value.replace(/\D/g, ''))} keyboardType="number-pad" maxLength={14} editable={!busy} />
        <Text style={s.note}>{method === 'PIX' ? 'Uma cobrança Pix de R$ 30 será gerada a cada mês. Você paga manualmente; não há débito automático.' : 'Assinatura mensal de R$ 30. Você informará o cartão na página segura do Asaas, responsável pelas cobranças recorrentes.'}</Text>
        <Button label={method === 'PIX' ? 'Confirmar assinatura e gerar Pix' : 'Confirmar e continuar no Asaas'} disabled={busy || !name.trim() || !email.trim() || ![11, 14].includes(document.length)} onPress={() => void run(() => api.checkout(teamId, { command_id: command.current, method, name, email, cpf_cnpj: document }))} />
        <SecondaryButton label="Voltar" disabled={busy} onPress={() => setForm(false)} />
      </Card>}
      {data.pix && <Card><Text style={s.heading}>Pix · R$ {data.pix.amount.replace('.', ',')}</Text><Text style={s.body}>Aguardando pagamento</Text>
        <Image source={{ uri: `data:image/png;base64,${data.pix.image}` }} style={s.qr} accessibilityLabel="QR Code Pix da assinatura" />
        <Text selectable style={s.code}>{data.pix.payload}</Text>
        <Button label="Copiar código Pix" onPress={() => { void Clipboard.setStringAsync(data.pix!.payload).then(() => setNotice('Código Pix copiado.')).catch(() => setError('Selecione o código e copie manualmente.')); }} />
      </Card>}
      {data.checkout_url && <Button label="Abrir pagamento seguro no Asaas" disabled={busy} onPress={() => { void Linking.openURL(data.checkout_url!).catch(() => setError('Não foi possível abrir o Asaas.')); }} />}
      <SecondaryButton label="Atualizar assinatura" disabled={busy} onPress={() => void run(() => api.refreshBilling(teamId))} />
      {data.can_cancel && !cancel && <SecondaryButton label="Cancelar assinatura" disabled={busy} onPress={() => setCancel(true)} />}
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
