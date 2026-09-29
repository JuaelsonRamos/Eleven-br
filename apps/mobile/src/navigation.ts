import type { MainTab } from '@eleven/shared';
import type { HelpTopicId } from './help/content';

export type TabParams = { [Tab in MainTab]: Tab extends 'Times' ? { view?: 'list' | 'detail' | 'join' } | undefined : Tab extends 'Jogos' ? { teamId?: string; eventId?: string } | undefined : Tab extends 'Financeiro' ? { teamId?: string; duesId?: string } | undefined : Tab extends 'Elenco' ? { teamId?: string; view?: 'requests' } | undefined : Tab extends 'Ajuda' ? { topic?: HelpTopicId } | undefined : undefined };
