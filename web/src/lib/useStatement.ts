import { useEffect, useState } from "react";
import { getWorldStatement, WorldStatement } from "./world";

/** The account statement, fetched again whenever `stamp` changes (it should change when the account does). */
export function useStatement(worldId: string | null, stamp: string): { statement: WorldStatement | null; failed: boolean } {
  const [statement, setStatement] = useState<WorldStatement | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (worldId === null) {
      setStatement(null);
      return;
    }
    let current = true;
    getWorldStatement(worldId).then(
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
  }, [worldId, stamp]);
  return { statement, failed };
}
