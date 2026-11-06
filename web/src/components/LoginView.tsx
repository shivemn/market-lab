import { useState, type FormEvent } from "react";
import { AuthRefused, enter, playAsGuest, type Entered } from "../lib/auth";

type Step = { kind: "form" } | { kind: "confirm"; username: string };

/** One form for new and returning people. A free username is only created after a confirmation. */
export function LoginView({ onEntered }: { onEntered: (entered: Entered) => void }) {
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [show, setShow] = useState(false);
  const [step, setStep] = useState<Step>({ kind: "form" });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function run(job: () => Promise<Entered>, whenConfirm?: (username: string) => void) {
    setBusy(true);
    setProblem(null);
    try {
      const entered = await job();
      if (entered.status === "confirm_new") {
        whenConfirm?.(entered.username);
      } else {
        onEntered(entered);
      }
    } catch (error) {
      setProblem(error instanceof AuthRefused ? error.message : "Something went wrong. Try again.");
      setStep({ kind: "form" });
    } finally {
      setBusy(false);
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run(() => enter(username.trim(), secret, false), (name) => setStep({ kind: "confirm", username: name }));
  };

  return (
    <main className="gate">
      <div className="gate-brand">
        <div className="brand-name">Market Lab</div>
        <p className="muted">Practise trading with pretend money in a market of twelve made-up companies.</p>
      </div>

      <section className="card gate-card" aria-labelledby="gate-title">
        {step.kind === "form" ? (
          <form onSubmit={submit} className="gate-form">
            <h1 id="gate-title">Sign in or start an account</h1>
            <p className="muted lead">
              Pick a username and a secret. A new username starts a fresh account. A username that already exists needs its secret.
            </p>
            <label className="field">
              Username
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                maxLength={20}
                aria-describedby="username-help"
                required
              />
              <span id="username-help" className="help">
                3 to 20 letters, numbers or underscores. It needn't be your real name.
              </span>
            </label>
            <label className="field">
              Your secret: a favourite word and a number
              <span className="secret-row">
                <input
                  type={show ? "text" : "password"}
                  value={secret}
                  onChange={(e) => setSecret(e.target.value)}
                  autoComplete="current-password"
                  aria-describedby="secret-help"
                  maxLength={64}
                  required
                />
                <button className="btn" type="button" onClick={() => setShow((s) => !s)} aria-pressed={show}>
                  {show ? "Hide" : "Show"}
                </button>
              </span>
              <span id="secret-help" className="help">
                For example purple42. At least 6 characters; capitals don't matter. Don't use a password you use anywhere else.
              </span>
            </label>
            {problem && (
              <p className="error" role="alert">
                {problem}
              </p>
            )}
            <button className="btn primary big" type="submit" disabled={busy || username.trim().length < 3 || secret.length < 1}>
              {busy ? "Checking…" : "Continue"}
            </button>
          </form>
        ) : (
          <div className="gate-form">
            <h1 id="gate-title">Create “{step.username}”?</h1>
            <p className="lead">
              There is no account with that name yet. If you meant to sign in to an existing one, go back and check the spelling.
            </p>
            <p className="muted lead">
              There is no email and no reset: if you forget your secret, this account can't be recovered. You would start a new one.
            </p>
            {problem && (
              <p className="error" role="alert">
                {problem}
              </p>
            )}
            <div className="gate-actions">
              <button
                className="btn primary big"
                type="button"
                disabled={busy}
                onClick={() => void run(() => enter(step.username, secret, true))}
              >
                {busy ? "Creating…" : "Create account"}
              </button>
              <button className="btn big" type="button" disabled={busy} onClick={() => setStep({ kind: "form" })}>
                Go back
              </button>
            </div>
          </div>
        )}

        <div className="gate-guest">
          <span className="muted">Only looking around?</span>
          <button className="btn" type="button" disabled={busy} onClick={() => void run(playAsGuest)}>
            Play as a guest
          </button>
          <span className="help">A guest account stays in this browser. Clear the browser's data and it is gone.</span>
        </div>
      </section>

      <p className="muted small gate-foot">
        Educational only. The companies, prices and money are made up, and nothing here is investment advice.
      </p>
    </main>
  );
}
