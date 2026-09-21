/** Public vocabulary only. Authorization and plan limits are enforced by the API. */
export type TeamPlan = 'free' | 'pro';
export type MainTab = 'Início' | 'Jogos' | 'Times' | 'Notificações' | 'Perfil';

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
