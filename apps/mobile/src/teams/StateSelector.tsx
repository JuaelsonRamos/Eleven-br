import { useState } from 'react';
import { FlatList, KeyboardAvoidingView, Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Field, TextAction } from '../components/AuthLayout';
import { theme } from '../theme';
import type { Choice } from './api';

const searchable = (text: string) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();

export function StateSelector({ value, options, onChange, disabled = false }: {
  value: string; options: Choice[]; onChange: (value: string) => void; disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const filtered = options.filter(item => searchable(item.label).includes(searchable(query)));
  const selected = options.find(item => item.value === value);
  return <View style={styles.field}>
    <Text style={styles.label}>UF</Text>
    <Pressable accessibilityRole="button" accessibilityLabel="UF"
      aria-expanded={open}
      accessibilityState={{ expanded: open, disabled }} disabled={disabled}
      onPress={() => { setQuery(''); setOpen(true); }} style={[styles.select, disabled && styles.disabled]}>
      <Text style={styles.value}>{selected?.label ?? 'Selecione o estado'} ▾</Text>
    </Pressable>
    <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
      <SafeAreaView style={styles.overlay}>
        <KeyboardAvoidingView style={styles.center} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View accessibilityViewIsModal style={styles.dialog}>
            <Text accessibilityRole="header" style={styles.title}>Selecione a UF</Text>
            <Field label="Pesquisar UF" placeholder="Nome ou sigla do estado" value={query} onChangeText={setQuery} autoFocus />
            <FlatList data={filtered} keyExtractor={item => item.value} keyboardShouldPersistTaps="handled"
              style={styles.list} ListEmptyComponent={<Text accessibilityLiveRegion="polite" style={styles.empty}>Nenhum estado encontrado.</Text>}
              renderItem={({ item }) => <Pressable accessibilityRole="button" accessibilityLabel={item.label}
                accessibilityState={{ selected: value === item.value }} style={[styles.option, value === item.value && styles.selected]}
                onPress={() => { onChange(item.value); setOpen(false); }}>
                <Text style={styles.value}>{item.label}{value === item.value ? ' ✓' : ''}</Text>
              </Pressable>} />
            <TextAction label="Fechar lista de UFs" onPress={() => setOpen(false)} />
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Modal>
  </View>;
}

const styles = StyleSheet.create({
  field: { gap: 8 }, label: { fontFamily: theme.fontFamily, fontSize: 15, fontWeight: '600', color: theme.colors.graphite },
  select: { minHeight: 48, borderWidth: 1, borderColor: theme.colors.border, borderRadius: 12, padding: 14, justifyContent: 'center' },
  disabled: { opacity: 0.65 }, value: { fontFamily: theme.fontFamily, fontSize: 16, color: theme.colors.graphite },
  overlay: { flex: 1, backgroundColor: theme.colors.background }, center: { flex: 1, justifyContent: 'center', padding: 20 },
  dialog: { width: '100%', maxWidth: 460, maxHeight: '90%', alignSelf: 'center', gap: 16, padding: 20, borderRadius: theme.radius, backgroundColor: theme.colors.white },
  title: { fontFamily: theme.fontFamily, fontSize: 22, fontWeight: '700', color: theme.colors.graphite },
  list: { flexGrow: 0, flexShrink: 1 }, option: { minHeight: 48, padding: 14, justifyContent: 'center', borderRadius: 8 },
  selected: { backgroundColor: theme.colors.lightGreen }, empty: { fontFamily: theme.fontFamily, color: theme.colors.muted, paddingVertical: 20 },
});
