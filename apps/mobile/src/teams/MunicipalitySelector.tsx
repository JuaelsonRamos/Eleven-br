import { useEffect, useState } from 'react';
import { FlatList, KeyboardAvoidingView, Modal, Platform, Pressable, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Field, TextAction } from '../components/AuthLayout';
import { listMunicipalities, type Municipality } from './api';
import { selectorStyles as styles } from './StateSelector';

const searchable = (text: string) => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

/** Official IBGE municipalities of the chosen UF: the user searches, never types a new city. */
export function MunicipalitySelector({ state, value, onChange, disabled = false, label = 'Cidade' }: {
  state: string; value: Municipality | null; onChange: (value: Municipality) => void; disabled?: boolean; label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<Municipality[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setItems(null); setFailed(false);
    if (state) void listMunicipalities(state).then(found => { if (active) setItems(found); }, () => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [state, attempt]);
  const filtered = items?.filter(item => searchable(item.name).includes(searchable(query))) ?? [];
  const unavailable = disabled || !state;
  return <View style={styles.field}>
    <Text style={styles.label}>{label}</Text>
    <Pressable accessibilityRole="button" accessibilityLabel={label} aria-expanded={open}
      accessibilityState={{ expanded: open, disabled: unavailable }} disabled={unavailable}
      onPress={() => { setQuery(''); setOpen(true); }} style={[styles.select, unavailable && styles.disabled]}>
      <Text style={styles.value}>{value?.name ?? (state ? 'Pesquisar cidade…' : 'Escolha a UF primeiro')} ▾</Text>
    </Pressable>
    <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
      <SafeAreaView style={styles.overlay}>
        <KeyboardAvoidingView style={styles.center} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <View accessibilityViewIsModal style={styles.dialog}>
            <Text accessibilityRole="header" style={styles.title}>Selecione a cidade ({state})</Text>
            <Field label="Pesquisar cidade" placeholder="Parte do nome da cidade" value={query} onChangeText={setQuery} autoFocus />
            {failed ? <>
              <Text accessibilityLiveRegion="polite" style={styles.empty}>Não foi possível carregar as cidades.</Text>
              <TextAction label="Tentar novamente" onPress={() => setAttempt(value => value + 1)} />
            </> : !items ? <Text style={styles.empty}>Carregando cidades…</Text> : <FlatList data={filtered} keyExtractor={item => String(item.code)}
              keyboardShouldPersistTaps="handled" initialNumToRender={20} style={styles.list}
              ListEmptyComponent={<Text accessibilityLiveRegion="polite" style={styles.empty}>Nenhuma cidade encontrada.</Text>}
              renderItem={({ item }) => <Pressable accessibilityRole="button" accessibilityLabel={item.name}
                accessibilityState={{ selected: value?.code === item.code }} style={[styles.option, value?.code === item.code && styles.selected]}
                onPress={() => { onChange(item); setOpen(false); }}>
                <Text style={styles.value}>{item.name}{value?.code === item.code ? ' ✓' : ''}</Text>
              </Pressable>} />}
            <TextAction label="Fechar lista de cidades" onPress={() => setOpen(false)} />
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Modal>
  </View>;
}
