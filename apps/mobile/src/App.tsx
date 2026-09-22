import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
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
import { TeamProvider } from './teams/TeamContext';
import { GamesScreen } from './screens/GamesScreen';

const Tab = createBottomTabNavigator<TabParams>();
const icons: Record<MainTab, keyof typeof Ionicons.glyphMap> = {
  Início: 'home-outline', Jogos: 'football-outline', Times: 'shield-outline',
  Notificações: 'notifications-outline', Perfil: 'person-outline',
};

function MainNavigation() {
  const insets = useSafeAreaInsets();
  return <Tab.Navigator screenOptions={({ route }) => ({
    headerShown: false,
    tabBarAccessibilityLabel: route.name,
    tabBarActiveTintColor: theme.colors.green,
    tabBarInactiveTintColor: theme.colors.muted,
    tabBarLabelPosition: 'below-icon',
    tabBarLabelStyle: { fontFamily: theme.fontFamily, fontSize: 10, fontWeight: '600' },
    tabBarStyle: { height: 66 + insets.bottom, paddingTop: 8, paddingBottom: Math.max(insets.bottom, 8), borderTopColor: theme.colors.border },
    tabBarIcon: ({ color, size }) => <Ionicons name={icons[route.name]} color={color} size={size} />,
  })}>
    {(Object.keys(icons) as MainTab[]).map(name => <Tab.Screen key={name} name={name} component={name === 'Perfil' ? ProfileScreen : name === 'Times' ? TeamsScreen : name === 'Jogos' ? GamesScreen : MainScreen} />)}
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
