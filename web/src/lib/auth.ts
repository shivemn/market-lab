/** Signing in: the saved token, and the calls to the server's /api/auth routes. No React in here. */

const TOKEN_KEY = "marketlab-token";
/** Sent by any call that finds the server no longer accepts the token, so the sign-in page can come back. */
export const SIGNED_OUT = "marketlab:signed-out";

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function browserStore(): Store | null {
  try {
    return window.localStorage;
  } catch {
    return null; // private windows and blocked site data: signing in then lasts until the page is closed
  }
}

let memoryToken: string | null = null;

export function savedToken(store: Store | null = browserStore()): string | null {
  try {
    return store?.getItem(TOKEN_KEY) ?? memoryToken;
  } catch {
    return memoryToken;
  }
}

export function saveToken(token: string, store: Store | null = browserStore()): void {
  memoryToken = token;
  try {
    store?.setItem(TOKEN_KEY, token);
  } catch {
    /* kept in memory only */
  }
}

export function forgetToken(store: Store | null = browserStore()): void {
  memoryToken = null;
  try {
    store?.removeItem(TOKEN_KEY);
  } catch {
    /* nothing to do */
  }
}

/** The header every call to the server carries once you are signed in. */
export function authHeaders(token: string | null = savedToken()): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Tell the page the server stopped accepting the saved token (it expired, or the server was reset). */
export function announceSignedOut(): void {
  forgetToken();
  if (typeof window !== "undefined") window.dispatchEvent(new Event(SIGNED_OUT));
}

export interface Who {
  username: string;
  guest: boolean;
}

export type Entered =
  | { status: "confirm_new"; username: string }
  | { status: "signed_in" | "created"; username: string; guest: boolean; token: string };

/** The server said no, with words a person can read. */
export class AuthRefused extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function post<T>(url: string, body?: object, headers: Record<string, string> = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new AuthRefused('Could not reach the server. Is "marketlab serve" running?', 0);
  }
  if (!response.ok) {
    let detail = "";
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* no readable reason */
    }
    throw new AuthRefused(detail || `The server could not do that (${response.status}).`, response.status);
  }
  return (await response.json()) as T;
}

export async function loginRequired(): Promise<boolean> {
  let response: Response;
  try {
    response = await fetch("/api/config");
  } catch {
    throw new AuthRefused('Could not reach the server. Is "marketlab serve" running?', 0);
  }
  if (!response.ok) throw new AuthRefused(`The server could not do that (${response.status}).`, response.status);
  return Boolean(((await response.json()) as { login_required?: boolean }).login_required);
}

export const enter = (username: string, secret: string, create: boolean) =>
  post<Entered>("/api/auth/enter", { username, secret, create });
export const playAsGuest = () => post<Entered>("/api/auth/guest");

export async function whoAmI(): Promise<Who | null> {
  const token = savedToken();
  if (!token) return null;
  try {
    const response = await fetch("/api/auth/me", { headers: authHeaders(token) });
    return response.ok ? ((await response.json()) as Who) : null;
  } catch {
    throw new AuthRefused('Could not reach the server. Is "marketlab serve" running?', 0);
  }
}

export async function signOutOnServer(): Promise<void> {
  try {
    await post("/api/auth/logout", undefined, authHeaders());
  } catch {
    /* the token is forgotten here either way */
  }
  forgetToken();
}
