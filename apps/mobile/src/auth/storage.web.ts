// Web refresh is an HttpOnly cookie owned by the API, never browser JS storage.
export async function readRefresh(): Promise<string | null> { return null; }
export async function storeRefresh(_token: string | null): Promise<void> {}
