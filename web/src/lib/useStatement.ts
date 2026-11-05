import { useEffect, useState } from "react";
import { getStatement, Statement } from "./practice";

/** The account statement, fetched again whenever `stamp` changes (it should change when the account does). */
export function useStatement(sessionId: string | null, stamp: string): { statement: Statement | null; failed: boolean } {
  const [statement, setStatement] = useState<Statement | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (sessionId === null) {
      setStatement(null);
      return;
    }
    let current = true;
    getStatement(sessionId).then(
      (s) => {
        if (current) {
          setStatement(s);
          setFailed(false);
        }
      },
      () => {
        if (current) setFailed(true);
      },
    );
    return () => {
      current = false;
    };
  }, [sessionId, stamp]);
  return { statement, failed };
}
