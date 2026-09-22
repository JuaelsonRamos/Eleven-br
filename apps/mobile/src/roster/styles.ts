import { StyleSheet } from 'react-native';
import { theme } from '../theme';

export const rosterStyles = StyleSheet.create({
  stack: { gap: 16 }, row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 10 },
  heading: { fontFamily: theme.fontFamily, fontSize: 24, fontWeight: '800', color: theme.colors.graphite },
  label: { fontFamily: theme.fontFamily, fontSize: 17, fontWeight: '700', color: theme.colors.graphite },
  note: { fontFamily: theme.fontFamily, fontSize: 15, lineHeight: 23, color: theme.colors.muted },
  success: { fontFamily: theme.fontFamily, fontSize: 16, color: theme.colors.green },
  filter: { minHeight: 48, padding: 14, borderWidth: 1, borderColor: theme.colors.border, borderRadius: 12, justifyContent: 'center' },
  selected: { backgroundColor: theme.colors.lightGreen, borderColor: theme.colors.green },
  photo: { width: 48, height: 48, borderRadius: 24 },
});
