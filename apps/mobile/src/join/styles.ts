import { StyleSheet } from 'react-native';
import { theme } from '../theme';

export const styles = StyleSheet.create({
  stack: { gap: 16 }, row: { flexDirection: 'row', gap: 12, alignItems: 'center', flexWrap: 'wrap' },
  heading: { fontFamily: theme.fontFamily, fontSize: 22, fontWeight: '700', color: theme.colors.graphite },
  text: { fontFamily: theme.fontFamily, fontSize: 16, color: theme.colors.graphite },
  note: { fontFamily: theme.fontFamily, fontSize: 14, lineHeight: 21, color: theme.colors.muted },
  success: { fontFamily: theme.fontFamily, fontSize: 15, color: theme.colors.green },
  choice: { padding: 14, minHeight: 52, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.border, gap: 8, backgroundColor: theme.colors.white },
  selected: { borderColor: theme.colors.green, backgroundColor: theme.colors.lightGreen },
  code: { fontFamily: theme.fontFamily, fontSize: 24, fontWeight: '800', letterSpacing: 2, color: theme.colors.green },
});
