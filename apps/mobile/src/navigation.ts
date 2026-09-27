import type { MainTab } from '@eleven/shared';

export type TabParams = { [Tab in MainTab]: Tab extends 'Times' ? { view?: 'list' | 'detail' | 'join' } | undefined : Tab extends 'Jogos' ? { teamId?: string; eventId?: string } | undefined : Tab extends 'Financeiro' ? { teamId?: string; duesId?: string } | undefined : Tab extends 'Elenco' ? { teamId?: string; view?: 'requests' } | undefined : undefined };
