import { useEffect, useRef, useState } from 'react';
import { Platform, Text, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Avatar, TeamBadge } from '../components/ui';
import { FormError, TextAction, authStyles } from '../components/AuthLayout';
import type { ImageChoice } from './api';

export function ImageSelector({ kind, name, current, choice, onChange, disabled = false }: {
  kind: 'photo' | 'crest'; name: string; current: string | null; choice: ImageChoice;
  onChange: (choice: ImageChoice) => void; disabled?: boolean;
}) {
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const locked = useRef(false);
  // Web picker owns a temporary blob URL. Release previews on replace/unmount.
  useEffect(() => {
    const uri = choice?.uri;
    return () => { if (Platform.OS === 'web' && uri?.startsWith('blob:')) URL.revokeObjectURL(uri); };
  }, [choice?.uri]);
  const label = kind === 'photo' ? 'foto' : 'escudo';
  const uri = choice === undefined ? current : choice?.uri ?? null;
  async function select() {
    if (locked.current) return;
    locked.current = true; setPicking(true); setError(null);
    try {
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], allowsEditing: false,
        quality: 1, preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Compatible });
      if (result.canceled) return;
      const asset = result.assets[0];
      if (!asset) return;
      if ((asset.fileSize ?? asset.file?.size ?? 0) > 5 * 1024 * 1024) {
        if (Platform.OS === 'web' && asset.uri.startsWith('blob:')) URL.revokeObjectURL(asset.uri);
        setError('A imagem deve ter no máximo 5 MB.'); return;
      }
      if (asset.mimeType && !['image/jpeg', 'image/png', 'image/webp'].includes(asset.mimeType)) {
        if (Platform.OS === 'web' && asset.uri.startsWith('blob:')) URL.revokeObjectURL(asset.uri);
        setError('Selecione uma imagem JPEG, PNG ou WebP.'); return;
      }
      onChange(asset);
    } catch { setError('Não foi possível selecionar a imagem. Confira o acesso às fotos e tente novamente.'); }
    finally { locked.current = false; setPicking(false); }
  }
  return <View style={{ gap: 8 }}>
    {kind === 'photo' ? <Avatar name={name} photoUrl={uri} size={112} /> : <TeamBadge name={name} crestUrl={uri} size={112} />}
    <TextAction label={`Alterar ${label}`} disabled={disabled || picking} onPress={() => void select()} />
    {uri && <TextAction label={`Remover ${label}`} disabled={disabled || picking} onPress={() => { setError(null); onChange(null); }} />}
    {choice !== undefined && <><Text style={authStyles.note}>{choice ? 'Confira a prévia e salve para confirmar.' : 'Salve para confirmar a remoção.'}</Text>
      <TextAction label={`Desfazer alteração de ${label}`} disabled={disabled || picking} onPress={() => { setError(null); onChange(undefined); }} /></>}
    <Text style={authStyles.note}>Opcional • JPEG, PNG ou WebP • até 5 MB</Text>
    <FormError message={error} />
  </View>;
}
