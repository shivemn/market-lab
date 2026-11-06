import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AuthRefused,
  SIGNED_OUT,
  loginRequired,
  saveToken,
  signOutOnServer,
  whoAmI,
  type Entered,
  type Who,
} from "../lib/auth";
import { LoginView } from "./LoginView";

interface Account {
  /** The signed-in name, or null when the server does not ask anyone to sign in. */
  username: string | null;
  guest: boolean;
  signOut: () => void;
}

const AccountContext = createContext<Account>({ username: null, guest: false, signOut: () => undefined });

export const useAccount = () => useContext(AccountContext);

type Phase =
  | { kind: "loading" }
  | { kind: "unreachable"; message: string }
  | { kind: "open" } // no sign-in needed (marketlab serve --no-login)
  | { kind: "signed-out" }
  | { kind: "in"; who: Who };

/** Shows the sign-in page until you are in, when the server asks for it; otherwise just the app. */
export function AuthGate({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });

  const start = useCallback(() => {
    setPhase({ kind: "loading" });
    loginRequired()
      .then(async (required) => {
        if (!required) return setPhase({ kind: "open" });
        const who = await whoAmI();
        setPhase(who ? { kind: "in", who } : { kind: "signed-out" });
      })
      .catch((problem: unknown) =>
        setPhase({ kind: "unreachable", message: problem instanceof AuthRefused ? problem.message : "Could not reach the server." }),
      );
  }, []);

  useEffect(start, [start]);

  // any call that finds the server no longer accepts the saved sign-in brings the sign-in page back
  useEffect(() => {
    const back = () => setPhase((now) => (now.kind === "in" ? { kind: "signed-out" } : now));
    window.addEventListener(SIGNED_OUT, back);
    return () => window.removeEventListener(SIGNED_OUT, back);
  }, []);

  const signOut = useCallback(() => {
    void signOutOnServer().then(() => setPhase({ kind: "signed-out" }));
  }, []);

  const account = useMemo<Account>(
    () => (phase.kind === "in" ? { username: phase.who.username, guest: phase.who.guest, signOut } : { username: null, guest: false, signOut }),
    [phase, signOut],
  );

  if (phase.kind === "loading") {
    return (
      <main className="gate">
        <p className="muted" role="status">
          Connecting…
        </p>
      </main>
    );
  }
  if (phase.kind === "unreachable") {
    return (
      <main className="gate">
        <section className="card gate-card">
          <h1>Can't reach the server</h1>
          <p className="muted">{phase.message}</p>
          <button className="btn primary big" type="button" onClick={start}>
            Try again
          </button>
        </section>
      </main>
    );
  }
  if (phase.kind === "signed-out") {
    const arrived = (entered: Entered) => {
      if (entered.status === "confirm_new") return;
      saveToken(entered.token);
      setPhase({ kind: "in", who: { username: entered.username, guest: entered.guest } });
    };
    return <LoginView onEntered={arrived} />;
  }
  return <AccountContext.Provider value={account}>{children}</AccountContext.Provider>;
}

