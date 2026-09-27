import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { StatusBar } from 'expo-status-bar';
import type { MainTab } from '@eleven/shared';
import type { TabParams } from './navigation';
import { MainScreen } from './screens/MainScreen';
import { theme } from './theme';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { AuthScreens } from './screens/AuthScreens';
import { ProfileScreen } from './screens/ProfileScreen';
import { TeamsScreen } from './screens/TeamsScreen';
import { TeamProvider, useTeams } from './teams/TeamContext';
import { GamesScreen } from './screens/GamesScreen';
import { RosterScreen } from './screens/RosterScreen';
import { MoreScreen } from './screens/MoreScreen';
import { FinanceScreen } from './screens/FinanceScreen';
import { BottomNavigation } from './components/BottomNavigation';
import { StatisticsScreen } from './screens/StatisticsScreen';

const Tab = createBottomTabNavigator<TabParams>();
const icons: Record<MainTab, keyof typeof Ionicons.glyphMap> = {
  Início: 'home-outline', Jogos: 'football-outline', Times: 'shield-outline',
  Notificações: 'notifications-outline', Perfil: 'person-outline',
  Elenco: 'people-outline', Mais: 'menu-outline', Estatísticas: 'stats-chart-outline', Financeiro: 'wallet-outline',
};

function MainNavigation() {
  const { teams } = useTeams();
  // Keep routes mounted during selection revalidation; operational screens gate data themselves.
  const visible: MainTab[] = teams.length ? ['Início', 'Jogos', 'Elenco', 'Mais'] : ['Times', 'Notificações', 'Perfil'];
  return <Tab.Navigator backBehavior="history" tabBar={props => <BottomNavigation {...props} visible={visible} icons={icons} />} screenOptions={({ route }) => ({
    headerShown: false,
    tabBarAccessibilityLabel: route.name === 'Times' ? 'Meus Times' : route.name,
    tabBarLabel: route.name === 'Times' ? 'Meus Times' : route.name,
    ...(!visible.includes(route.name) ? { tabBarButton: () => null, tabBarItemStyle: { display: 'none' as const } } : {}),
    tabBarActiveTintColor: theme.colors.green,
    tabBarInactiveTintColor: theme.colors.muted,
    tabBarLabelPosition: 'below-icon',
    tabBarLabelStyle: { fontFamily: theme.fontFamily, fontSize: 10, fontWeight: '600' },
    tabBarIcon: ({ color, size }) => <Ionicons name={icons[route.name]} color={color} size={size} />,
  })}>
    <Tab.Screen name="Início" component={MainScreen} />
    <Tab.Screen name="Jogos" component={GamesScreen} />
    <Tab.Screen name="Times" component={TeamsScreen} />
    <Tab.Screen name="Notificações" component={MainScreen} />
    <Tab.Screen name="Perfil" component={ProfileScreen} />
    <Tab.Screen name="Elenco" component={RosterScreen} />
    <Tab.Screen name="Mais" component={MoreScreen} />
    <Tab.Screen name="Estatísticas" component={StatisticsScreen} />
    <Tab.Screen name="Financeiro" component={FinanceScreen} />
  </Tab.Navigator>;
}

export default function App() {
  return <SafeAreaProvider>
    <StatusBar style="dark" />
    <AuthProvider><AppContent /></AuthProvider>
  </SafeAreaProvider>;
}

function AppContent() {
  const { profile, booting, bootError } = useAuth();
  if (booting || bootError || !profile?.player_id) return <AuthScreens />;
  return (
    <TeamProvider key={profile.user_id} userId={profile.user_id}><NavigationContainer theme={{ ...DefaultTheme, colors: { ...DefaultTheme.colors, primary: theme.colors.green, background: theme.colors.background, text: theme.colors.graphite } }}>
      <MainNavigation />
    </NavigationContainer></TeamProvider>
  );
}
