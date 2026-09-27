import { StyleSheet } from 'react-native';
import { theme } from '../theme';

export const s = StyleSheet.create({
  summary: { backgroundColor: theme.colors.primaryDark, padding: theme.space.xl, borderRadius: theme.radii.lg, gap: theme.space.lg },
  summaryLabel: { color: theme.colors.onDarkMuted, fontFamily: theme.fontFamily, fontSize: theme.type.small },
  balance: { color: theme.colors.white, fontFamily: theme.fontFamily, fontSize: theme.type.display, fontWeight: '800' },
  summaryItem: { flexGrow: 1, flexBasis: 100, gap: theme.space.sm },
  summaryValue: { color: theme.colors.white, fontFamily: theme.fontFamily, fontSize: theme.type.heading, fontWeight: '700' },
  identity: { flex: 1, minWidth: 0, gap: theme.space.xs },
  monthRow: { flexDirection: 'row', alignItems: 'center', gap: theme.space.sm },
  month: { flex: 1, textAlign: 'center', fontFamily: theme.fontFamily, fontSize: theme.type.body, fontWeight: '700', color: theme.colors.graphite },
  stack: { gap: 16 }, row: { flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' },
  title: { fontFamily: theme.fontFamily, fontSize: 26, fontWeight: '800', color: theme.colors.green },
  heading: { fontFamily: theme.fontFamily, fontSize: 20, fontWeight: '700', color: theme.colors.graphite },
  text: { fontFamily: theme.fontFamily, fontSize: 16, lineHeight: 23, color: theme.colors.graphite },
  note: { fontFamily: theme.fontFamily, fontSize: 14, lineHeight: 21, color: theme.colors.muted },
  success: { fontFamily: theme.fontFamily, fontSize: 15, color: theme.colors.green },
  choice: { minHeight: 48, justifyContent: 'center', padding: 12, borderWidth: 1, borderColor: theme.colors.border, borderRadius: 12, backgroundColor: theme.colors.white },
  selected: { borderColor: theme.colors.green, backgroundColor: theme.colors.lightGreen },
  divider: { backgroundColor: theme.colors.surface, borderRadius: theme.radii.md, padding: theme.space.lg, gap: theme.space.sm },
});
