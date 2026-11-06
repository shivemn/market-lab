import { useAccount } from "./AuthGate";

/** Who is signed in, and a way out. Nothing shows when the server isn't asking anyone to sign in. */
export function AccountChip() {
  const { username, guest, signOut } = useAccount();
  if (username === null) return null;
  return (
    <div className="account-chip">
      <span title={guest ? "A guest account stays in this browser" : "Signed in"}>
        {guest ? "Guest " : ""}
        <strong>{username}</strong>
      </span>
      <button className="link" type="button" onClick={signOut}>
        Sign out
      </button>
    </div>
  );
}
