import { useState, type PropsWithChildren } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { brand } from '@eleven/shared';
import { theme } from '../theme';
import { imageUrl } from '../images/api';
import { useAuth } from '../auth/AuthContext';
import { IconButton, StatusBadge, type Tone } from './design';
export { SectionHeader, StatCard, StatusBadge, FilterChip, IconButton, ListItem, QuickAction, Feedback, FormSurface } from './design';

export function AppHeader({ onProfile, onNotifications }: { onProfile?: () => void; onNotifications?: () => void } = {}) {
  const { profile } = useAuth();
  return <View style={styles.header}>
    <View>
      <Text accessibilityRole="header" style={styles.brand}>{brand.name}</Text>
      <Text style={styles.slogan}>{brand.slogan}</Text>
    </View>
    <View style={styles.headerActions}>{onNotifications && <IconButton label="Notificações" icon="notifications-outline" onPress={onNotifications} />}{onProfile ? <Pressable accessibilityRole="button" accessibilityLabel="Perfil" onPress={onProfile} style={({ pressed }) => [styles.headerMark, pressed && styles.dimmed]}><Avatar name={profile?.display_name || 'Jogador'} photoUrl={profile?.photo_url} /></Pressable> : profile?.photo_url ? <Avatar name={profile.display_name || 'Jogador'} photoUrl={profile.photo_url} /> : <View accessible accessibilityLabel="Futebol brasileiro" style={styles.headerMark}>
      <Ionicons name="football-outline" size={26} color={theme.colors.green} />
    </View>}</View>
  </View>;
}

export function Card({ children }: PropsWithChildren) {
  return <View style={styles.card}>{children}</View>;
}

export function Button({ label, onPress, disabled = false, variant = 'primary', accessibilityLabel }: {
  label: string; onPress: () => void; disabled?: boolean; variant?: 'primary' | 'secondary' | 'danger'; accessibilityLabel?: string;
}) {
  const [focused, setFocused] = useState(false);
  return <Pressable accessibilityRole="button" accessibilityLabel={accessibilityLabel ?? label} accessibilityState={{ disabled }}
    disabled={disabled} onPress={onPress}
    onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
    style={({ pressed }) => [styles.button, variant === 'secondary' && styles.secondary, variant === 'danger' && styles.danger, focused && styles.focus, (pressed || disabled) && styles.dimmed]}>
    {disabled && /Salvando|Carregando|Enviando|Entrando/.test(label) && <ActivityIndicator size="small" color={variant === 'secondary' ? theme.colors.green : theme.colors.white} />}
    <Text style={[styles.buttonText, variant === 'secondary' && styles.secondaryText]}>{label}</Text>
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

export function Badge({ label, tone = 'success' }: { label: string; tone?: Tone }) {
  return <StatusBadge label={label} tone={tone} />;
}

export function SecondaryButton(props: Omit<Parameters<typeof Button>[0], 'variant'>) { return <Button {...props} variant="secondary" />; }

export function Avatar({ name, photoUrl, size = 48 }: { name: string; photoUrl?: string | null; size?: number }) {
  const [failed, setFailed] = useState<string | null>(null);
  if (photoUrl && failed !== photoUrl) return <Image source={{ uri: imageUrl(photoUrl) }} accessibilityLabel={`Foto de ${name}`}
    onError={() => setFailed(photoUrl)} resizeMode="cover" style={{ width: size, height: size, borderRadius: size / 2 }} />;
  const initials = name.trim().split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('');
  return <View accessible accessibilityLabel={name} style={[styles.avatar, { width: size, height: size, borderRadius: size / 2 }]}>
    <Text style={styles.initials}>{initials || '?'}</Text>
  </View>;
}

export function TeamBadge({ name, crestUrl, size = 64 }: { name: string; crestUrl?: string | null; size?: number }) {
  const [failed, setFailed] = useState<string | null>(null);
  if (crestUrl && failed !== crestUrl) return <Image source={{ uri: imageUrl(crestUrl) }} accessibilityLabel={`Escudo de ${name}`}
    onError={() => setFailed(crestUrl)} resizeMode="contain" style={{ width: size, height: size, borderRadius: 20 }} />;
  return <View accessible accessibilityLabel={`Escudo de ${name}`} style={[styles.icon, { width: size, height: size }]}>
    <Ionicons name="shield-outline" size={30} color={theme.colors.green} />
  </View>;
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: theme.space.lg, gap: theme.space.sm },
  headerActions: { flexDirection: 'row', gap: theme.space.xs, alignItems: 'center' },
  brand: { color: theme.colors.green, fontWeight: '900', fontFamily: theme.fontFamily, fontSize: 23, letterSpacing: 1.2 },
  slogan: { color: theme.colors.muted, fontFamily: theme.fontFamily, fontSize: 13, marginTop: 3 },
  headerMark: { width: 48, height: 48, borderRadius: 24, backgroundColor: theme.colors.lightGreen, alignItems: 'center', justifyContent: 'center' },
  card: { padding: theme.space.lg, borderRadius: theme.radius, backgroundColor: theme.colors.surface, gap: theme.space.md },
  button: { minHeight: theme.touch, paddingVertical: theme.space.md, paddingHorizontal: theme.space.lg, backgroundColor: theme.colors.green, borderRadius: theme.radii.md, justifyContent: 'center', alignItems: 'center', flexDirection: 'row', gap: theme.space.sm, borderWidth: 2, borderColor: 'transparent' },
  secondary: { backgroundColor: theme.colors.surfaceMuted }, secondaryText: { color: theme.colors.green },
  danger: { backgroundColor: theme.colors.danger }, focus: { borderColor: theme.colors.blue },
  buttonText: { flexShrink: 1, textAlign: 'center', color: theme.colors.white, fontWeight: '700', fontFamily: theme.fontFamily, fontSize: 16 },
  dimmed: { opacity: 0.65 },
  empty: { alignItems: 'center', paddingVertical: theme.space.xl, gap: theme.space.md, paddingHorizontal: theme.space.sm },
  icon: { width: 64, height: 64, borderRadius: 20, backgroundColor: theme.colors.lightGreen, justifyContent: 'center', alignItems: 'center' },
  title: { color: theme.colors.graphite, fontWeight: '700', fontFamily: theme.fontFamily, fontSize: 22, textAlign: 'center' },
  description: { color: theme.colors.muted, fontFamily: theme.fontFamily, fontSize: 16, lineHeight: 25, textAlign: 'center', maxWidth: 390 },
  badge: { alignSelf: 'flex-start', backgroundColor: theme.colors.lightGreen, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 5 },
  badgeText: { color: theme.colors.green, fontFamily: theme.fontFamily, fontSize: 12, fontWeight: '700' },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: theme.colors.lightGreen, alignItems: 'center', justifyContent: 'center' },
  initials: { fontFamily: theme.fontFamily, fontSize: 18, fontWeight: '700', color: theme.colors.green },
});
