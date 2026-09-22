import * as SecureStore from 'expo-secure-store';

const key = (userId: string) => `eleven.team.${userId}`;
export const readSelection = (userId: string) => SecureStore.getItemAsync(key(userId));
export const storeSelection = (userId: string, id: string | null) => id
  ? SecureStore.setItemAsync(key(userId), id)
  : SecureStore.deleteItemAsync(key(userId));
