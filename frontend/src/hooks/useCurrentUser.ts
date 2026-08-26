import { useCallback, useEffect, useState } from "react";
import type { User } from "../domain/types";
import { expenseService } from "../services";

export function useCurrentUser() {
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined = loading

  const refresh = useCallback(async () => {
    const current = await expenseService.getCurrentUser();
    setUser(current);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { user, loading: user === undefined, refresh };
}
