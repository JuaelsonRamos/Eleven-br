// Only an ID preference, never credentials or cached private team data.
const key = (userId: string) => `eleven.team.${userId}`;
export async function readSelection(userId: string) { return localStorage.getItem(key(userId)); }
export async function storeSelection(userId: string, id: string | null) {
  if (id) localStorage.setItem(key(userId), id);
  else localStorage.removeItem(key(userId));
}
