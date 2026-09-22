import { StyleSheet } from 'react-native';
import { theme } from '../theme';

export const styles = StyleSheet.create({
  stack: { gap: 16 }, row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  title: { fontFamily: theme.fontFamily, fontSize: 28, fontWeight: '800', color: theme.colors.graphite },
  heading: { fontFamily: theme.fontFamily, fontSize: 19, fontWeight: '700', color: theme.colors.graphite },
  text: { fontFamily: theme.fontFamily, fontSize: 16, lineHeight: 24, color: theme.colors.graphite },
  note: { fontFamily: theme.fontFamily, fontSize: 14, lineHeight: 21, color: theme.colors.muted },
  chip: { minHeight: 48, paddingHorizontal: 14, paddingVertical: 12, borderRadius: 12, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.white },
  selected: { borderColor: theme.colors.green, backgroundColor: theme.colors.lightGreen },
  success: { fontFamily: theme.fontFamily, fontSize: 15, color: theme.colors.green },
});
