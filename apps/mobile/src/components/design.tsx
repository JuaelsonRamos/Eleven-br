import { useState, type PropsWithChildren, type ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { theme } from '../theme';

export type IconName = keyof typeof Ionicons.glyphMap;
export type Tone = 'success' | 'warning' | 'danger' | 'info' | 'exempt' | 'neutral';
const tones = {
  success: [theme.colors.green, theme.colors.lightGreen], warning: [theme.colors.warning, theme.colors.warningSurface],
  danger: [theme.colors.danger, theme.colors.dangerSurface], info: [theme.colors.info, theme.colors.infoSurface],
  exempt: [theme.colors.exempt, theme.colors.exemptSurface], neutral: [theme.colors.muted, theme.colors.surfaceMuted],
} as const;

export function StatusBadge({ label, tone = 'neutral' }: { label: string; tone?: Tone }) {
  return <View style={[ds.badge, { backgroundColor: tones[tone][1] }]}><Text style={[ds.badgeText, { color: tones[tone][0] }]}>{label}</Text></View>;
}
export function SectionHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return <View style={ds.section}><View style={ds.grow}><Text accessibilityRole="header" style={ds.heading}>{title}</Text>{subtitle && <Text style={ds.note}>{subtitle}</Text>}</View>{action}</View>;
}
export function StatCard({ label, value, tone = 'success', icon }: { label: string; value: string | number; tone?: Tone; icon?: IconName }) {
  return <View accessible accessibilityLabel={`${label}: ${value}`} style={ds.stat}>{icon && <Ionicons accessible={false} aria-hidden name={icon} size={theme.icon.small} color={tones[tone][0]} />}<Text style={[ds.value, { color: tones[tone][0], fontSize: typeof value === 'string' ? theme.type.heading : theme.type.title }]}>{value}</Text><Text style={ds.note}>{label}</Text></View>;
}
export function FilterChip({ label, selected = false, onPress, disabled = false, role = 'button', accessibilityLabel }: { label: string; selected?: boolean; onPress: () => void; disabled?: boolean; role?: 'button' | 'radio' | 'checkbox'; accessibilityLabel?: string }) {
  const [focused, setFocused] = useState(false);
  return <Pressable accessibilityRole={role} accessibilityLabel={accessibilityLabel ?? label} accessibilityState={{ selected, checked: role !== 'button' ? selected : undefined, disabled }} aria-checked={role !== 'button' ? selected : undefined} disabled={disabled} onPress={onPress} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} style={({ pressed }) => [ds.chip, selected && ds.chipSelected, focused && ds.focus, (pressed || disabled) && ds.dimmed]}><Text style={[ds.chipText, selected && ds.onPrimary]}>{label}</Text></Pressable>;
}
export function IconButton({ label, icon, onPress, disabled = false }: { label: string; icon: IconName; onPress: () => void; disabled?: boolean }) {
  const [focused, setFocused] = useState(false);
  return <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} style={({ pressed }) => [ds.iconButton, focused && ds.focus, (pressed || disabled) && ds.dimmed]}><Ionicons accessible={false} aria-hidden name={icon} size={theme.icon.medium} color={theme.colors.green} /></Pressable>;
}
export function ListItem({ title, subtitle, leading, trailing, onPress, accessibilityLabel, disabled = false, children }: PropsWithChildren<{ title: string; subtitle?: string; leading?: ReactNode; trailing?: ReactNode; onPress: () => void; accessibilityLabel?: string; disabled?: boolean }>) {
  const [focused, setFocused] = useState(false);
  return <Pressable accessibilityRole="button" accessibilityLabel={accessibilityLabel ?? title} accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} style={({ pressed }) => [ds.listItem, focused && ds.focus, (pressed || disabled) && ds.dimmed]}>
    <View style={ds.listRow}>{leading}<View style={ds.grow}><Text style={ds.listTitle}>{title}</Text>{subtitle && <Text style={ds.note}>{subtitle}</Text>}</View><Ionicons accessible={false} aria-hidden name="chevron-forward" size={theme.icon.small} color={theme.colors.muted} /></View>
    {(trailing || children) && <View style={ds.listFooter}>{trailing}{children}</View>}
  </Pressable>;
}
export function QuickAction({ label, icon, onPress, description }: { label: string; icon: IconName; onPress: () => void; description: string }) {
  const [focused, setFocused] = useState(false);
  return <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} style={({ pressed }) => [ds.quick, focused && ds.focus, pressed && ds.dimmed]}><View style={ds.quickIcon}><Ionicons accessible={false} aria-hidden name={icon} size={theme.icon.medium} color={theme.colors.green} /></View><Text style={ds.listTitle}>{label}</Text><Text style={ds.note}>{description}</Text></Pressable>;
}
export function Feedback({ message, tone = 'success' }: { message: string | null; tone?: Tone }) {
  return message ? <View accessibilityLiveRegion="polite" style={[ds.feedback, { backgroundColor: tones[tone][1] }]}><Ionicons accessible={false} aria-hidden name={tone === 'danger' ? 'alert-circle-outline' : 'checkmark-circle-outline'} size={theme.icon.medium} color={tones[tone][0]} /><Text style={[ds.feedbackText, { color: tones[tone][0] }]}>{message}</Text></View> : null;
}
export function FormSurface({ children, style }: PropsWithChildren<{ style?: StyleProp<ViewStyle> }>) {
  return <View style={[ds.form, style]}>{children}</View>;
}
export const ds = StyleSheet.create({
  grow: { flex: 1, minWidth: 0, gap: theme.space.xs },
  section: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.space.md, alignItems: 'center' },
  heading: { fontFamily: theme.fontFamily, fontSize: theme.type.heading, fontWeight: '800', color: theme.colors.graphite },
  note: { fontFamily: theme.fontFamily, fontSize: theme.type.small, lineHeight: 21, color: theme.colors.muted },
  badge: { alignSelf: 'flex-start', borderRadius: theme.radii.pill, paddingVertical: 5, paddingHorizontal: 10, maxWidth: '100%' },
  badgeText: { fontFamily: theme.fontFamily, fontSize: theme.type.caption, fontWeight: '700' },
  stat: { alignSelf: 'stretch', flexGrow: 1, flexBasis: 120, minWidth: 0, padding: theme.space.lg, gap: theme.space.sm, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface },
  value: { fontFamily: theme.fontFamily, fontSize: theme.type.title, fontWeight: '800', flexShrink: 1 },
  chip: { maxWidth: '100%', minHeight: theme.touch, paddingHorizontal: theme.space.lg, paddingVertical: theme.space.md, borderRadius: theme.radii.pill, backgroundColor: theme.colors.surfaceMuted, justifyContent: 'center', alignItems: 'center', borderWidth: 2, borderColor: 'transparent' },
  chipSelected: { backgroundColor: theme.colors.green }, chipText: { flexShrink: 1, textAlign: 'center', fontFamily: theme.fontFamily, fontSize: theme.type.small, fontWeight: '700', color: theme.colors.muted }, onPrimary: { color: theme.colors.white },
  focus: { borderColor: theme.colors.blue }, dimmed: { opacity: 0.65 },
  iconButton: { width: theme.touch, height: theme.touch, borderRadius: theme.radii.pill, alignItems: 'center', justifyContent: 'center', backgroundColor: theme.colors.surfaceMuted, borderWidth: 2, borderColor: 'transparent' },
  listItem: { padding: theme.space.lg, gap: theme.space.md, backgroundColor: theme.colors.surface, borderRadius: theme.radii.md, borderWidth: 2, borderColor: 'transparent', minHeight: 76 },
  listRow: { flexDirection: 'row', alignItems: 'center', gap: theme.space.md }, listFooter: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.space.sm, alignItems: 'center' },
  listTitle: { fontFamily: theme.fontFamily, fontSize: theme.type.body, fontWeight: '700', color: theme.colors.graphite },
  quick: { alignSelf: 'stretch', flexGrow: 1, flexBasis: 125, gap: theme.space.sm, padding: theme.space.lg, backgroundColor: theme.colors.surface, borderRadius: theme.radii.md, borderWidth: 2, borderColor: 'transparent' },
  quickIcon: { width: 44, height: 44, borderRadius: theme.radii.md, backgroundColor: theme.colors.lightGreen, alignItems: 'center', justifyContent: 'center' },
  feedback: { flexDirection: 'row', gap: theme.space.sm, padding: theme.space.md, borderRadius: theme.radii.md, alignItems: 'center' }, feedbackText: { flex: 1, fontFamily: theme.fontFamily, fontSize: theme.type.small, lineHeight: 21 },
  form: { width: '100%', maxWidth: theme.formWidth, alignSelf: 'center', gap: theme.space.lg },
});
