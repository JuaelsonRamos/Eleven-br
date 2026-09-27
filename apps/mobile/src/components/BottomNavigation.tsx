import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import type { MainTab } from '@eleven/shared';
import { theme } from '../theme';
import type { IconName } from './design';

export function BottomNavigation({ state, navigation, visible, icons }: BottomTabBarProps & { visible: MainTab[]; icons: Record<MainTab, IconName> }) {
  const insets = useSafeAreaInsets();
  const [focused, setFocused] = useState<string | null>(null);
  const current = state.routes[state.index];
  const parent = current && !visible.includes(current.name as MainTab)
    ? (['Financeiro', 'Estatísticas'].includes(current.name) ? 'Início' : 'Mais') : undefined;
  return <View style={[s.surface, { paddingBottom: Math.max(insets.bottom, theme.space.sm) }]}><View style={s.bar}>
    {state.routes.filter(route => visible.includes(route.name as MainTab)).map(route => {
      const active = current?.key === route.key || parent === route.name;
      const label = route.name === 'Times' ? 'Meus Times' : route.name;
      return <Pressable key={route.key} accessibilityRole="tab" accessibilityLabel={label} accessibilityState={{ selected: active }} onFocus={() => setFocused(route.key)} onBlur={() => setFocused(null)} onPress={() => {
        const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
        if (current?.key !== route.key && !event.defaultPrevented) navigation.navigate(route.name, route.params);
      }} onLongPress={() => navigation.emit({ type: 'tabLongPress', target: route.key })} style={[s.item, focused === route.key && s.focus]}>
        <View style={[s.indicator, active && s.active]}><Ionicons name={icons[route.name as MainTab]} size={theme.icon.medium} color={active ? theme.colors.green : theme.colors.muted} /></View>
        <Text style={[s.label, active && s.activeLabel]}>{label}</Text>
      </Pressable>;
    })}
  </View></View>;
}
const s = StyleSheet.create({
  surface: { backgroundColor: theme.colors.surface, paddingTop: theme.space.xs },
  bar: { flexDirection: 'row', width: '100%', maxWidth: theme.maxWidth, alignSelf: 'center', paddingHorizontal: theme.space.sm },
  item: { flex: 1, minHeight: 60, alignItems: 'center', justifyContent: 'center', gap: theme.space.xs, borderWidth: 2, borderColor: 'transparent', borderRadius: theme.radii.md },
  indicator: { paddingHorizontal: theme.space.lg, paddingVertical: theme.space.xs, borderRadius: theme.radii.pill }, active: { backgroundColor: theme.colors.lightGreen },
  label: { fontFamily: theme.fontFamily, fontSize: theme.type.caption, fontWeight: '600', color: theme.colors.muted }, activeLabel: { color: theme.colors.green, fontWeight: '800' }, focus: { borderColor: theme.colors.blue },
});
