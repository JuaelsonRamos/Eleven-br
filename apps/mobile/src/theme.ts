import { brand } from '@eleven/shared';
import { Platform } from 'react-native';

export const theme = {
  fontFamily: Platform.OS === 'web' ? 'system-ui, -apple-system, Segoe UI, sans-serif' : undefined,
  colors: {
    ...brand.colors,
    background: '#F6F8F7',
    muted: '#53665E',
    border: '#D9E4DF',
    error: '#A12828',
  },
  radius: 20,
  maxWidth: 760,
};
