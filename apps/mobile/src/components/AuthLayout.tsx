import { useState, type PropsWithChildren, type ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type TextInputProps } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from './ui';
import { Feedback } from './design';
import { theme } from '../theme';
import { maskDateTime, type DateTimeMask } from './dateTime';

export function AuthLayout({ title, description, children, header, wide = false }: PropsWithChildren<{ title: string; description?: string; header?: ReactNode; wide?: boolean }>) {
  return <SafeAreaView style={styles.safe}>
    <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}>
        <View style={[styles.container, wide && styles.wideContainer]}>
          {header ?? <AppHeader />}
          <View style={styles.heading}>
            <Text accessibilityRole="header" style={styles.title}>{title}</Text>
            {description && <Text style={styles.description}>{description}</Text>}
          </View>
          {children}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  </SafeAreaView>;
}

export function Field({ label, password = false, mask, ...props }: TextInputProps & { label: string; password?: boolean; mask?: DateTimeMask }) {
  const [visible, setVisible] = useState(false);
  const [focused, setFocused] = useState(false);
  return <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <View style={[styles.inputRow, focused && styles.focus]}>
      <TextInput accessibilityLabel={label} placeholderTextColor={theme.colors.muted}
        autoCapitalize="none" autoCorrect={false} {...props}
        keyboardType={mask ? 'number-pad' : props.keyboardType}
        onChangeText={value => props.onChangeText?.(mask ? maskDateTime(value, mask) : value)}
        onFocus={event => { setFocused(true); props.onFocus?.(event); }} onBlur={event => { setFocused(false); props.onBlur?.(event); }}
        secureTextEntry={password && !visible} style={[styles.input, props.style]} />
      {password && <Pressable onPress={() => setVisible(!visible)} accessibilityRole="button"
        accessibilityLabel={`${visible ? 'Ocultar' : 'Mostrar'} ${label.toLowerCase()}`} style={styles.reveal}>
        <Text style={styles.link}>{visible ? 'Ocultar' : 'Mostrar'}</Text>
      </Pressable>}
    </View>
  </View>;
}

export function TextAction({ label, onPress, disabled = false }: { label: string; onPress: () => void; disabled?: boolean }) {
  const [focused, setFocused] = useState(false);
  return <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button"
    onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
    accessibilityState={{ disabled }} style={({ pressed }) => [styles.action, focused && styles.focus, (disabled || pressed) && { opacity: 0.5 }]}>
    <Text style={styles.link}>{label}</Text>
  </Pressable>;
}

export function FormError({ message }: { message: string | null }) {
  return message ? <View accessibilityRole="alert"><Feedback message={message} tone="danger" /></View> : null;
}

export const authStyles = StyleSheet.create({
  note: { fontFamily: theme.fontFamily, color: theme.colors.muted, fontSize: 14, lineHeight: 21 },
  center: { alignItems: 'center', gap: 12 },
  row: { flexDirection: 'row', gap: 8 },
});

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: theme.space.lg, paddingBottom: 32 },
  container: { width: '100%', maxWidth: theme.formWidth, alignSelf: 'center', gap: theme.space.lg },
  wideContainer: { maxWidth: theme.maxWidth },
  heading: { gap: 10, paddingVertical: 16 },
  title: { fontFamily: theme.fontFamily, fontSize: theme.type.title, fontWeight: '800', color: theme.colors.green },
  description: { fontFamily: theme.fontFamily, color: theme.colors.muted, fontSize: 16, lineHeight: 25 },
  field: { gap: theme.space.sm, width: '100%', maxWidth: theme.formWidth, alignSelf: 'center' },
  label: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: 15, fontWeight: '600' },
  inputRow: { flexDirection: 'row', borderWidth: 2, borderColor: theme.colors.border, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface },
  focus: { borderColor: theme.colors.green },
  input: { fontFamily: theme.fontFamily, flex: 1, minWidth: 0, minHeight: 52, padding: 14, fontSize: 16, color: theme.colors.graphite },
  reveal: { justifyContent: 'center', paddingHorizontal: 12, minWidth: 64, minHeight: 48 },
  action: { maxWidth: '100%', paddingVertical: theme.space.sm, minHeight: theme.touch, justifyContent: 'center', alignItems: 'center', paddingHorizontal: theme.space.md, borderWidth: 2, borderColor: 'transparent', borderRadius: theme.radii.md, backgroundColor: theme.colors.surfaceMuted },
  link: { fontFamily: theme.fontFamily, color: theme.colors.green, fontSize: 14, fontWeight: '700', textAlign: 'center' },
  error: { fontFamily: theme.fontFamily, color: theme.colors.error, fontSize: 14, lineHeight: 21 },
});
