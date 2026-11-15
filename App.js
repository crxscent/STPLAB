import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import HomeScreen from './src/screens/HomeScreen';
import SearchScreen from './src/screens/SearchScreen';
import FavoritesScreen from './src/screens/FavoritesScreen';
import DetailScreen from './src/screens/DetailScreen';
import { FavoritesProvider } from './src/context/FavoritesContext';
import { colors } from './src/theme/colors';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

const linking = {
  prefixes: ['/'],
  config: {
    screens: {
      Main: {
        screens: {
          Top: 'top',
          Search: 'search',
          Favorites: 'favorites',
        },
      },
      Detail: 'coin/:id',
    },
  },
};

const navTheme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    background: colors.bg,
    card: colors.bgElev,
    text: colors.text,
    border: colors.border,
    primary: colors.primary,
  },
};

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarStyle: {
          backgroundColor: colors.bgElev,
          borderTopColor: colors.border,
          height: 60,
          paddingBottom: 8,
          paddingTop: 6,
        },
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarIcon: ({ color, size }) => {
          let icon = 'ellipse';
          if (route.name === 'Top') icon = 'trending-up';
          if (route.name === 'Search') icon = 'search';
          if (route.name === 'Favorites') icon = 'star';
          return <Ionicons name={icon} size={size} color={color} />;
        },
      })}
    >
      <Tab.Screen name="Top" component={HomeScreen} options={{ title: 'Топ-20' }} />
      <Tab.Screen name="Search" component={SearchScreen} options={{ title: 'Пошук' }} />
      <Tab.Screen name="Favorites" component={FavoritesScreen} options={{ title: 'Обране' }} />
    </Tab.Navigator>
  );
}

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <FavoritesProvider>
          <NavigationContainer theme={navTheme} linking={linking}>
            <StatusBar style="light" />
            <Stack.Navigator screenOptions={{ headerShown: false }}>
              <Stack.Screen name="Main" component={MainTabs} />
              <Stack.Screen name="Detail" component={DetailScreen} />
            </Stack.Navigator>
          </NavigationContainer>
        </FavoritesProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
