import { useState, type PropsWithChildren } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type TextInputProps } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AppHeader } from './ui';
import { theme } from '../theme';

export function AuthLayout({ title, description, children }: PropsWithChildren<{ title: string; description?: string }>) {
  return <SafeAreaView style={styles.safe}>
    <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.scroll}>
        <View style={styles.container}>
          <AppHeader />
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

export function Field({ label, password = false, ...props }: TextInputProps & { label: string; password?: boolean }) {
  const [visible, setVisible] = useState(false);
  return <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <View style={styles.inputRow}>
      <TextInput accessibilityLabel={label} placeholderTextColor={theme.colors.muted}
        autoCapitalize="none" autoCorrect={false} {...props}
        secureTextEntry={password && !visible} style={[styles.input, props.style]} />
      {password && <Pressable onPress={() => setVisible(!visible)} accessibilityRole="button"
        accessibilityLabel={`${visible ? 'Ocultar' : 'Mostrar'} ${label.toLowerCase()}`} style={styles.reveal}>
        <Text style={styles.link}>{visible ? 'Ocultar' : 'Mostrar'}</Text>
      </Pressable>}
    </View>
  </View>;
}

export function TextAction({ label, onPress, disabled = false }: { label: string; onPress: () => void; disabled?: boolean }) {
  return <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button"
    accessibilityState={{ disabled }} style={[styles.action, disabled && { opacity: 0.5 }]}>
    <Text style={styles.link}>{label}</Text>
  </Pressable>;
}

export function FormError({ message }: { message: string | null }) {
  return message ? <Text accessibilityRole="alert" accessibilityLiveRegion="polite" style={styles.error}>{message}</Text> : null;
}

export const authStyles = StyleSheet.create({
  note: { fontFamily: theme.fontFamily, color: theme.colors.muted, fontSize: 14, lineHeight: 21 },
  center: { alignItems: 'center', gap: 12 },
  row: { flexDirection: 'row', gap: 8 },
});

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: theme.colors.background },
  scroll: { flexGrow: 1, paddingHorizontal: 24, paddingBottom: 32 },
  container: { width: '100%', maxWidth: 460, alignSelf: 'center', gap: 16 },
  heading: { gap: 10, paddingVertical: 16 },
  title: { fontFamily: theme.fontFamily, fontSize: 34, fontWeight: '800', color: theme.colors.green },
  description: { fontFamily: theme.fontFamily, color: theme.colors.muted, fontSize: 16, lineHeight: 25 },
  field: { gap: 8 },
  label: { fontFamily: theme.fontFamily, color: theme.colors.graphite, fontSize: 15, fontWeight: '600' },
  inputRow: { flexDirection: 'row', borderWidth: 1, borderColor: theme.colors.border, borderRadius: 12, backgroundColor: theme.colors.white },
  input: { fontFamily: theme.fontFamily, flex: 1, minWidth: 0, minHeight: 52, padding: 14, fontSize: 16, color: theme.colors.graphite },
  reveal: { justifyContent: 'center', paddingHorizontal: 12, minWidth: 64, minHeight: 48 },
  action: { minHeight: 48, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 8 },
  link: { fontFamily: theme.fontFamily, color: theme.colors.green, fontSize: 14, fontWeight: '700', textAlign: 'center' },
  error: { fontFamily: theme.fontFamily, color: theme.colors.error, fontSize: 14, lineHeight: 21 },
});
