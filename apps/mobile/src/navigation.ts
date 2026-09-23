import type { MainTab } from '@eleven/shared';

export type TabParams = { [Tab in MainTab]: Tab extends 'Times' ? { view?: 'list' | 'detail' } | undefined : undefined };
