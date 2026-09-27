import { brand, designTokens } from '@eleven/shared';
import { Platform } from 'react-native';

export const theme = {
  fontFamily: Platform.OS === 'web' ? 'system-ui, -apple-system, Segoe UI, sans-serif' : undefined,
  colors: {
    ...brand.colors,
    ...designTokens.colors,
    muted: designTokens.colors.textSecondary,
    error: designTokens.colors.danger,
  },
  space: designTokens.space,
  radii: designTokens.radii,
  type: designTokens.type,
  icon: designTokens.icon,
  touch: designTokens.touch,
  radius: designTokens.radii.lg,
  maxWidth: 760,
  formWidth: 520,
};
