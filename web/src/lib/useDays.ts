import { useEffect, useState } from "react";
import { loadDays, SavedDay } from "./history";

/** The saved days of one account. Loads again whenever `refresh` changes (a day finished or was left). */
export function useDays(owner: string, refresh: unknown) {
  const [days, setDays] = useState<SavedDay[] | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!/^[A-Za-z0-9_-]{1,32}$/.test(owner)) return;
    let current = true;
    loadDays(owner).then(
      (list) => {
        if (current) {
          setDays(list);
          setFailed(false);
        }
      },
      () => current && setFailed(true),
    );
    return () => {
      current = false;
    };
  }, [owner, refresh]);
  return { days, failed };
}
