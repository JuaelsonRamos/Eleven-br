/** Public vocabulary only. Authorization and plan limits are enforced by the API. */
export type TeamPlan = 'free' | 'pro';
export type MainTab = 'Início' | 'Jogos' | 'Elenco' | 'Mais' | 'Times' | 'Notificações' | 'Perfil' | 'Estatísticas' | 'Financeiro';

export const brand = {
  name: 'ELEVEN BR',
  slogan: 'Seu time. Seu jogo.',
  colors: {
    green: '#075E45',
    gold: '#F2B705',
    blue: '#123B66',
    white: '#FFFFFF',
    graphite: '#182026',
    lightGreen: '#E8F3EF',
  },
} as const;

export const designTokens = {
  space: { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 },
  radii: { sm: 10, md: 16, lg: 24, pill: 999 },
  type: { caption: 12, small: 14, body: 16, heading: 20, title: 28, display: 34 },
  icon: { small: 18, medium: 22, large: 28 },
  touch: 48,
  colors: {
    primaryDark: '#063D30', background: '#F2F5F3', surface: '#FFFFFF',
    surfaceMuted: '#EAF0ED', text: '#182026', textSecondary: '#52635D',
    border: '#D7E1DB', danger: '#A12736', dangerSurface: '#FBEAED',
    warning: '#7C4C06', warningSurface: '#FFF2D6',
    info: '#123B66', infoSurface: '#EAF0F8',
    exempt: '#62428A', exemptSurface: '#F1EBF8', onDarkMuted: '#C6E2D6',
  },
} as const;
