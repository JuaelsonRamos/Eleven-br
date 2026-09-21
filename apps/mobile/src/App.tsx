import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { StatusBar } from 'expo-status-bar';
import type { MainTab } from '@eleven/shared';
import type { TabParams } from './navigation';
import { MainScreen } from './screens/MainScreen';
import { theme } from './theme';

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
    {(Object.keys(icons) as MainTab[]).map(name => <Tab.Screen key={name} name={name} component={MainScreen} />)}
  </Tab.Navigator>;
}

export default function App() {
  return <SafeAreaProvider>
    <StatusBar style="dark" />
    <NavigationContainer theme={{ ...DefaultTheme, colors: { ...DefaultTheme.colors, primary: theme.colors.green, background: theme.colors.background, text: theme.colors.graphite } }}>
      <MainNavigation />
    </NavigationContainer>
  </SafeAreaProvider>;
}
