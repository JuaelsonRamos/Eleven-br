import { useState, type ReactNode } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import FontAwesome5 from '@expo/vector-icons/FontAwesome5';
import { PlatformStats } from '../components/PlatformStats';
import { theme } from '../theme';

// Official logo (E11, ELEVEN BR and slogan): margins trimmed, white background made transparent.
const logo = require('../../assets/brand/eleven-br-logo.png');
const LOGO_RATIO = 800 / 439;
// Art cropped from the approved reference (players, stadium, ball), with no text or UI baked in.
const art = require('../../assets/landing/players.webp');
const ART_RATIO = 989 / 710;
// Band tone of the approved reference; the art's lower edge fades into it.
const BAND = '#012B21';
const COLUMN = 560;

const features: { label: string; icon: ReactNode }[] = [
  { label: 'TIMES', icon: <Ionicons accessible={false} aria-hidden name="people-outline" size={25} color={theme.colors.white} /> },
  { label: 'PELADAS', icon: <Ionicons accessible={false} aria-hidden name="football-outline" size={25} color={theme.colors.white} /> },
  { label: 'JOGOS', icon: <Ionicons accessible={false} aria-hidden name="calendar-outline" size={25} color={theme.colors.white} /> },
  { label: 'FINANCEIRO', icon: <FontAwesome5 accessible={false} aria-hidden name="coins" size={21} color={theme.colors.white} /> },
];

/** Public entry page. Both actions reuse the existing registration and login flows. */
export function WelcomeScreen({ onRegister, onLogin }: { onRegister: () => void; onLogin: () => void }) {
  const { width } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const column = Math.min(width, COLUMN);
  const gutter = width < 360 ? 20 : Math.round(Math.min(40, Math.max(24, column * 0.08)));
  // Proportions measured on the approved reference (title ≈ 76% of the content width).
  const title = Math.round(Math.min(44, Math.max(28, (column - gutter * 2) * 0.09)));
  const lead = width >= 600 ? 18 : width >= 400 ? 16 : 15;
  // Close to the approved reference while keeping the logo's own slogan legible.
  const logoWidth = Math.round(Math.min(196, Math.max(120, (column - gutter * 2) * 0.4)));
  const framed = width > COLUMN + theme.space.xxl;
  return <SafeAreaView style={s.safe} edges={['top', 'left', 'right']}>
    <ScrollView contentContainerStyle={s.scroll}>
      <View style={[s.column, framed && s.columnFramed]}>
        <View style={[s.content, { paddingHorizontal: gutter }]}>
          <View style={s.header}>
            <View style={s.brand}>
              {/* Explicit width and height keep the logo proportion (a static asset has no auto height). */}
              <Image source={logo} accessibilityRole="image" accessibilityLabel="ELEVEN BR. Seu time. Seu jogo." resizeMode="contain"
                style={{ width: logoWidth, height: Math.round(logoWidth / LOGO_RATIO) }} />
            </View>
            <View accessible accessibilityLabel="Futebol brasileiro" style={s.mark}>
              <Ionicons name="football-outline" size={28} color={theme.colors.green} />
            </View>
          </View>
          <View style={s.intro}>
            <Text accessibilityRole="header" style={[s.title, { fontSize: title, lineHeight: Math.round(title * 1.12) }]}>Entre em campo.</Text>
            <Text style={[s.lead, { fontSize: lead, lineHeight: Math.round(lead * 1.45) }]}>Seu futebol, mais organizado.{'\n'}Faça parte do ELEVEN BR.</Text>
          </View>
          <PlatformStats />
          <View style={s.actions}>
            <Cta label="Criar minha conta" primary onPress={onRegister} />
            <Cta label="Já tenho conta" onPress={onLogin} />
          </View>
        </View>
        <View style={[s.showcase, framed && s.showcaseFramed]}>
          {/* Explicit 100% size: a static asset otherwise keeps its intrinsic 989×710 box. */}
          <View style={[s.artFrame, { aspectRatio: ART_RATIO }]}>
            <Image source={art} accessible={false} aria-hidden importantForAccessibility="no-hide-descendants" resizeMode="cover" style={s.art} />
          </View>
          <View style={[s.band, { paddingBottom: theme.space.md + (framed ? 0 : insets.bottom) }]}>
            {features.map((item, index) => <View key={item.label} style={[s.feature, index > 0 && s.divider]}>
              <View style={s.featureIcon}>{item.icon}</View>
              <Text style={[s.featureLabel, width < 360 && s.featureLabelCompact]}>{item.label}</Text>
            </View>)}
          </View>
        </View>
      </View>
    </ScrollView>
  </SafeAreaView>;
}

function Cta({ label, primary = false, onPress }: { label: string; primary?: boolean; onPress: () => void }) {
  const [focused, setFocused] = useState(false);
  return <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
    style={({ pressed }) => [s.cta, primary ? s.ctaPrimary : s.ctaSecondary, focused && s.focus, pressed && s.pressed]}>
    <Text style={[s.ctaText, primary && s.ctaTextPrimary]}>{label}</Text>
    {primary && <Ionicons accessible={false} aria-hidden name="arrow-forward" size={theme.icon.medium} color={theme.colors.white} style={s.arrow} />}
  </Pressable>;
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1 },
  column: { width: '100%', maxWidth: COLUMN, alignSelf: 'center' },
  columnFramed: { paddingBottom: theme.space.xxl },
  content: { gap: theme.space.lg + theme.space.xs, paddingTop: theme.space.md, paddingBottom: theme.space.md },
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: theme.space.md },
  brand: { flex: 1, minWidth: 0 },
  mark: { width: 46, height: 46, borderRadius: 23, backgroundColor: theme.colors.lightGreen, alignItems: 'center', justifyContent: 'center' },
  intro: { gap: theme.space.sm },
  title: { fontFamily: theme.fontFamily, fontWeight: '900', letterSpacing: -0.5, color: theme.colors.green },
  lead: { fontFamily: theme.fontFamily, color: theme.colors.muted },
  actions: { gap: theme.space.sm + 2 },
  cta: { minHeight: 50, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 48, borderRadius: 14, borderWidth: 2, borderColor: 'transparent' },
  ctaPrimary: { backgroundColor: theme.colors.green },
  ctaSecondary: { backgroundColor: theme.colors.surfaceMuted },
  ctaText: { flexShrink: 1, textAlign: 'center', fontFamily: theme.fontFamily, fontSize: 16, fontWeight: '800', color: theme.colors.green },
  ctaTextPrimary: { color: theme.colors.white },
  arrow: { position: 'absolute', right: theme.space.lg + theme.space.xs },
  focus: { borderColor: theme.colors.blue },
  pressed: { opacity: 0.8 },
  showcase: { width: '100%', overflow: 'hidden' },
  showcaseFramed: { borderRadius: theme.radii.lg },
  artFrame: { width: '100%' },
  art: { width: '100%', height: '100%' },
  band: { flexDirection: 'row', marginTop: -2, paddingTop: theme.space.md, backgroundColor: BAND },
  feature: { flex: 1, minWidth: 0, alignItems: 'center', gap: theme.space.xs + 2, paddingHorizontal: 2 },
  divider: { borderLeftWidth: 1, borderLeftColor: 'rgba(255,255,255,0.18)' },
  featureIcon: { height: 28, alignItems: 'center', justifyContent: 'center' },
  featureLabel: { fontFamily: theme.fontFamily, fontSize: 12, fontWeight: '600', letterSpacing: 0.4, color: theme.colors.white, textAlign: 'center' },
  featureLabelCompact: { fontSize: 11, letterSpacing: 0.1 },
});
