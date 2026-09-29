import { useState } from 'react';
import { Image, Linking, StyleSheet, Text, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { Field, TextAction } from '../components/AuthLayout';
import { EmptyState, ListItem } from '../components/ui';
import { theme } from '../theme';
import { findTopic, helpSections, type HelpMedia, type HelpSection, type HelpTopic } from './content';

const normalize = (value: string) => value.replace(/\*\*/g, '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

export function HelpCenter({ topicId, onTopic }: { topicId: string | null; onTopic: (id: string | null) => void }) {
  const [query, setQuery] = useState('');
  const current = topicId ? findTopic(topicId) : null;
  if (current) return <TopicView section={current.section} topic={current.topic} onTopic={onTopic} />;
  const term = normalize(query.trim());
  const sections = (helpSections as readonly HelpSection[])
    .map(section => ({ ...section, topics: section.topics.filter(topic => !term || normalize([topic.title, topic.summary, ...topic.steps, ...(topic.notes ?? [])].join(' ')).includes(term)) }))
    .filter(section => section.topics.length);
  return <View style={s.stack}>
    <View style={s.intro}>
      <Text accessibilityRole="header" style={s.title}>Aprenda a usar</Text>
      <Text style={s.note}>Guias rápidos das principais funções do ELEVEN BR, do cadastro ao financeiro.</Text>
    </View>
    <Field label="Buscar na ajuda" value={query} onChangeText={setQuery} placeholder="Ex.: mensalidade, sorteio, convite" maxLength={60} />
    {!sections.length && <EmptyState title="Nada encontrado" description="Tente outra palavra ou navegue pelos assuntos." icon="search-outline" />}
    {sections.map(section => <View key={section.id} style={s.section}>
      <View style={s.sectionTitle}>
        <Ionicons accessible={false} aria-hidden name={section.icon} size={theme.icon.medium} color={theme.colors.green} />
        <Text accessibilityRole="header" style={s.heading}>{section.title}</Text>
      </View>
      {section.topics.map(topic => <ListItem key={topic.id} title={topic.title} subtitle={topic.summary} onPress={() => onTopic(topic.id)} />)}
    </View>)}
  </View>;
}

function TopicView({ section, topic, onTopic }: { section: HelpSection; topic: HelpTopic; onTopic: (id: string | null) => void }) {
  const related = (topic.related ?? []).map(id => findTopic(id)?.topic).filter((item): item is HelpTopic => !!item);
  return <View style={s.stack}>
    <TextAction label="Voltar aos assuntos" onPress={() => onTopic(null)} />
    <View style={s.intro}>
      <Text style={s.eyebrow}>{section.title.toUpperCase()}</Text>
      <Text accessibilityRole="header" style={s.title}>{topic.title}</Text>
      <Text style={s.note}>{topic.summary}</Text>
    </View>
    <View style={s.card}>
      <Text accessibilityRole="header" style={s.heading}>Passo a passo</Text>
      {topic.steps.map((step, index) => <View key={step} style={s.step}>
        <View style={s.number}><Text style={s.numberText}>{index + 1}</Text></View>
        <Rich text={step} />
      </View>)}
    </View>
    {!!topic.notes?.length && <View style={[s.card, s.tips]}>
      <Text accessibilityRole="header" style={s.heading}>Bom saber</Text>
      {topic.notes.map(note => <View key={note} style={s.step}>
        <Ionicons accessible={false} aria-hidden name="information-circle-outline" size={theme.icon.medium} color={theme.colors.green} />
        <Rich text={note} />
      </View>)}
    </View>}
    {topic.media?.map(item => <Media key={'source' in item ? item.description : item.url} item={item} />)}
    {!!related.length && <View style={s.section}>
      <Text accessibilityRole="header" style={s.heading}>Veja também</Text>
      {related.map(item => <ListItem key={item.id} title={item.title} subtitle={item.summary} onPress={() => onTopic(item.id)} />)}
    </View>}
    <TextAction label="Ver todos os assuntos" onPress={() => onTopic(null)} />
  </View>;
}

/** Renders **label** segments in bold; the guide never embeds markup beyond that. */
function Rich({ text }: { text: string }) {
  return <Text style={s.body}>{text.split('**').map((part, index) => <Text key={index} style={index % 2 ? s.strong : undefined}>{part}</Text>)}</Text>;
}

function Media({ item }: { item: HelpMedia }) {
  if ('source' in item) return <Image source={item.source} accessibilityLabel={item.description} resizeMode="contain" style={s.media} />;
  return <TextAction label={item.label} onPress={() => void Linking.openURL(item.url)} />;
}

const s = StyleSheet.create({
  stack: { gap: theme.space.lg },
  intro: { gap: theme.space.sm },
  section: { gap: theme.space.md },
  sectionTitle: { flexDirection: 'row', alignItems: 'center', gap: theme.space.sm, paddingTop: theme.space.sm },
  eyebrow: { fontFamily: theme.fontFamily, fontSize: theme.type.caption, fontWeight: '800', letterSpacing: 1, color: theme.colors.green },
  title: { fontFamily: theme.fontFamily, fontSize: theme.type.title, fontWeight: '800', color: theme.colors.graphite },
  heading: { fontFamily: theme.fontFamily, fontSize: theme.type.heading, fontWeight: '800', color: theme.colors.graphite },
  note: { fontFamily: theme.fontFamily, fontSize: theme.type.body, lineHeight: 24, color: theme.colors.muted },
  card: { padding: theme.space.lg, gap: theme.space.md, borderRadius: theme.radii.md, backgroundColor: theme.colors.surface },
  tips: { backgroundColor: theme.colors.lightGreen },
  step: { flexDirection: 'row', alignItems: 'flex-start', gap: theme.space.md },
  number: { width: 28, height: 28, borderRadius: theme.radii.pill, backgroundColor: theme.colors.green, alignItems: 'center', justifyContent: 'center' },
  numberText: { fontFamily: theme.fontFamily, fontSize: theme.type.small, fontWeight: '800', color: theme.colors.white },
  body: { flex: 1, minWidth: 0, fontFamily: theme.fontFamily, fontSize: theme.type.body, lineHeight: 24, color: theme.colors.graphite },
  strong: { fontWeight: '800', color: theme.colors.green },
  media: { width: '100%', aspectRatio: 16 / 9, borderRadius: theme.radii.md, backgroundColor: theme.colors.surfaceMuted },
});
