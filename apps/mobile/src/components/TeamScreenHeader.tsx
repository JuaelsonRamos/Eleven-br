import { Image, StyleSheet, View } from 'react-native';
import { AppHeader } from './ui';
import { theme } from '../theme';

/** Decorative treatment shared only by the main team screens. */
export function TeamScreenHeader({ onProfile }: { onProfile?: () => void }) {
  return <View style={styles.header}>
    <View pointerEvents="none" accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={StyleSheet.absoluteFill}>
      <Image source={require('../../assets/landing/players.webp')} resizeMode="cover" style={styles.art} />
      <View style={styles.overlay} />
    </View>
    <View style={styles.content}><AppHeader onProfile={onProfile} /></View>
    <View style={styles.accent} />
  </View>;
}

const styles = StyleSheet.create({
  header: { marginTop: theme.space.md, minHeight: 140, justifyContent: 'flex-end', backgroundColor: theme.colors.lightGreen, borderRadius: theme.radii.lg, overflow: 'hidden', borderWidth: 1, borderColor: theme.colors.surfaceMuted },
  art: { width: '100%', height: '100%', opacity: 0.3 },
  overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(255,255,255,0.62)' },
  content: { paddingHorizontal: theme.space.md },
  accent: { height: 3, width: 48, marginLeft: theme.space.md, marginBottom: theme.space.md, borderRadius: theme.radii.pill, backgroundColor: theme.colors.gold },
});
