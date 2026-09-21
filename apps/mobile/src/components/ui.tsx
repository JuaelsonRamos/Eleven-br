import type { PropsWithChildren } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { brand } from '@eleven/shared';
import { theme } from '../theme';

export function AppHeader() {
  return <View style={styles.header}>
    <View>
      <Text accessibilityRole="header" style={styles.brand}>{brand.name}</Text>
      <Text style={styles.slogan}>{brand.slogan}</Text>
    </View>
    <View accessible accessibilityLabel="Futebol brasileiro" style={styles.headerMark}>
      <Ionicons name="football-outline" size={26} color={theme.colors.green} />
    </View>
  </View>;
}

export function Card({ children }: PropsWithChildren) {
  return <View style={styles.card}>{children}</View>;
}

export function Button({ label, onPress, disabled = false }: {
  label: string; onPress: () => void; disabled?: boolean;
}) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }}
    disabled={disabled} onPress={onPress}
    style={({ pressed }) => [styles.button, (pressed || disabled) && styles.dimmed]}>
    <Text style={styles.buttonText}>{label}</Text>
  </Pressable>;
}

export function EmptyState({ title, description, icon = 'football-outline', children }: PropsWithChildren<{
  title: string; description: string; icon?: keyof typeof Ionicons.glyphMap;
}>) {
  return <View style={styles.empty}>
    <View style={styles.icon}><Ionicons name={icon} size={32} color={theme.colors.green} /></View>
    <Text accessibilityRole="header" style={styles.title}>{title}</Text>
    <Text style={styles.description}>{description}</Text>
    {children}
  </View>;
}

export function LoadingState({ label = 'Carregando…' }: { label?: string }) {
  return <View accessibilityLiveRegion="polite" style={styles.empty}>
    <ActivityIndicator color={theme.colors.green} accessibilityLabel={label} />
    <Text style={styles.description}>{label}</Text>
  </View>;
}

export function ErrorState({ onRetry }: { onRetry: () => void }) {
  return <View accessibilityRole="alert" style={styles.empty}>
    <Text style={styles.title}>Não foi possível carregar</Text>
    <Text style={styles.description}>Tente novamente em alguns instantes.</Text>
    <Button label="Tentar novamente" onPress={onRetry} />
  </View>;
}

export function Badge({ label }: { label: string }) {
  return <View style={styles.badge}><Text style={styles.badgeText}>{label}</Text></View>;
}

export function Avatar({ name }: { name: string }) {
  const initials = name.trim().split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('');
  return <View accessible accessibilityLabel={name} style={styles.avatar}>
    <Text style={styles.initials}>{initials || '?'}</Text>
  </View>;
}

export function TeamBadge({ name }: { name: string }) {
  return <View accessible accessibilityLabel={`Escudo de ${name}`} style={styles.icon}>
    <Ionicons name="shield-outline" size={30} color={theme.colors.green} />
  </View>;
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 24 },
  brand: { color: theme.colors.green, fontWeight: '900', fontFamily: theme.fontFamily, fontSize: 23, letterSpacing: 1.2 },
  slogan: { color: theme.colors.muted, fontFamily: theme.fontFamily, fontSize: 13, marginTop: 3 },
  headerMark: { width: 48, height: 48, borderRadius: 24, backgroundColor: theme.colors.lightGreen, alignItems: 'center', justifyContent: 'center' },
  card: { padding: 24, borderRadius: theme.radius, backgroundColor: theme.colors.white, borderWidth: 1, borderColor: theme.colors.border },
  button: { minHeight: 48, paddingVertical: 14, paddingHorizontal: 22, backgroundColor: theme.colors.green, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  buttonText: { color: theme.colors.white, fontWeight: '700', fontFamily: theme.fontFamily, fontSize: 16 },
  dimmed: { opacity: 0.65 },
  empty: { alignItems: 'center', paddingVertical: 30, gap: 16 },
  icon: { width: 64, height: 64, borderRadius: 20, backgroundColor: theme.colors.lightGreen, justifyContent: 'center', alignItems: 'center' },
  title: { color: theme.colors.graphite, fontWeight: '700', fontFamily: theme.fontFamily, fontSize: 22, textAlign: 'center' },
  description: { color: theme.colors.muted, fontFamily: theme.fontFamily, fontSize: 16, lineHeight: 25, textAlign: 'center', maxWidth: 390 },
  badge: { alignSelf: 'flex-start', backgroundColor: theme.colors.lightGreen, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 },
  badgeText: { color: theme.colors.green, fontFamily: theme.fontFamily, fontSize: 12, fontWeight: '700' },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: theme.colors.lightGreen, alignItems: 'center', justifyContent: 'center' },
  initials: { fontFamily: theme.fontFamily, fontSize: 18, fontWeight: '700', color: theme.colors.green },
});
