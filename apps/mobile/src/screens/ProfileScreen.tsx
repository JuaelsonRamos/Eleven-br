import { useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { useAuth } from '../auth/AuthContext';
import { AuthLayout, FormError, authStyles } from '../components/AuthLayout';
import { Badge, Button } from '../components/ui';
import { ImageSelector } from '../images/ImageSelector';
import { savePhoto, type ImageChoice } from '../images/api';

export function ProfileScreen() {
  const { profile, signOut, updateProfile } = useAuth();
  const [choice, setChoice] = useState<ImageChoice>(undefined);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save() {
    if (savingRef.current || choice === undefined) return;
    savingRef.current = true; setSaving(true); setError(null); setSuccess(null);
    try { updateProfile(await savePhoto(choice)); setChoice(undefined); setSuccess(choice ? 'Foto atualizada.' : 'Foto removida.'); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Não foi possível salvar a foto.'); }
    finally { savingRef.current = false; setSaving(false); }
  }
  async function exit() {
    setBusy(true); setError(null);
    try { await signOut(); }
    catch { setError('Não foi possível encerrar sua sessão. Confira a conexão e tente novamente.'); }
    finally { setBusy(false); }
  }
  return <AuthLayout title="Perfil" description="Sua identidade dentro de campo.">
    <View style={authStyles.center}>
      <ImageSelector kind="photo" name={profile?.display_name || 'Jogador'} current={profile?.photo_url || null} choice={choice}
        disabled={busy || saving} onChange={value => { setChoice(value); setError(null); setSuccess(null); }} />
      <Text accessibilityRole="header" style={authStyles.note}>{profile?.display_name}</Text>
      <Text style={authStyles.note}>{profile?.email || profile?.phone}</Text>
      <Badge label="CONTATO VERIFICADO" />
    </View>
    <FormError message={error} />
    {success && <Text accessibilityLiveRegion="polite" style={authStyles.note}>{success}</Text>}
    {choice !== undefined && <Button label={saving ? 'Salvando…' : 'Salvar foto'} disabled={busy || saving} onPress={() => void save()} />}
    <Button label={busy ? 'Saindo…' : 'Sair da conta'} disabled={busy || saving} onPress={() => void exit()} />
  </AuthLayout>;
}
