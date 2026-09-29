import { useState } from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useNavigation } from '@react-navigation/native';
import type { BottomTabNavigationProp } from '@react-navigation/bottom-tabs';
import type { TabParams } from '../navigation';
import { theme } from '../theme';
import type { HelpTopicId } from './content';

/** Contextual entry point: opens one topic of the "Aprenda a usar" guide. */
export function HelpShortcut({ topic, label }: { topic: HelpTopicId; label: string }) {
  const navigation = useNavigation<BottomTabNavigationProp<TabParams>>();
  const [focused, setFocused] = useState(false);
  return <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={() => navigation.navigate('Ajuda', { topic })}
    onFocus={() => setFocused(true)} onBlur={() => setFocused(false)} style={({ pressed }) => [s.link, focused && s.focus, pressed && s.pressed]}>
    <Ionicons accessible={false} aria-hidden name="help-circle-outline" size={theme.icon.medium} color={theme.colors.green} />
    <Text style={s.text}>{label}</Text>
  </Pressable>;
}

const s = StyleSheet.create({
  link: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', maxWidth: '100%', gap: theme.space.sm, minHeight: theme.touch, paddingHorizontal: theme.space.sm, borderWidth: 2, borderColor: 'transparent', borderRadius: theme.radii.md },
  text: { flexShrink: 1, fontFamily: theme.fontFamily, fontSize: theme.type.small, fontWeight: '700', color: theme.colors.green, textDecorationLine: 'underline' },
  focus: { borderColor: theme.colors.blue }, pressed: { opacity: 0.65 },
});
