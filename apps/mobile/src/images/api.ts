import { Platform } from 'react-native';
import type { ImagePickerAsset } from 'expo-image-picker';
import { API_URL, authenticated, type Profile } from '../auth/api';
import type { Team } from '../teams/api';

export type ImageChoice = ImagePickerAsset | null | undefined;
export const imageUrl = (url: string) => url.startsWith('/v1/media/') ? `${API_URL}${url}` : url;

function multipart(asset: ImagePickerAsset) {
  const form = new FormData();
  if (Platform.OS === 'web') {
    if (!asset.file) throw new Error('Selecione a imagem novamente.');
    form.append('file', asset.file, asset.fileName || 'image');
  } else {
    // React Native's FormData accepts a file URI; the browser uses an actual File.
    form.append('file', { uri: asset.uri, name: asset.fileName || 'image.jpg',
      type: asset.mimeType || 'image/jpeg' } as unknown as Blob);
  }
  return form;
}

export const savePhoto = (choice: Exclude<ImageChoice, undefined>) => authenticated<Profile>(
  choice ? '/v1/me/photo' : '/v1/me/photo/remove', choice ? multipart(choice) : {}, 'POST',
);
export const saveCrest = (teamId: string, choice: Exclude<ImageChoice, undefined>) => authenticated<Team>(
  `/v1/teams/${encodeURIComponent(teamId)}/crest${choice ? '' : '/remove'}`, choice ? multipart(choice) : {}, 'POST',
);
