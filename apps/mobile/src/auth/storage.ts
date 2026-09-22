import * as SecureStore from 'expo-secure-store';

const KEY = 'eleven.refresh';
export const readRefresh = () => SecureStore.getItemAsync(KEY);
export async function storeRefresh(token: string | null) {
  if (token) {
    await SecureStore.setItemAsync(KEY, token, { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY });
  } else {
    await SecureStore.deleteItemAsync(KEY);
  }
}
