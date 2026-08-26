import { HttpExpenseService } from "./httpService";
import type { ExpenseServiceApi } from "./types";

export type { ExpenseServiceApi } from "./types";
export * from "./types";

/**
 * The single place that decides which backend implementation is active.
 * Every component imports `expenseService` from here — never a concrete
 * implementation directly. Talks to the FastAPI backend in ../../backend
 * (see httpService.ts); swap back to `new MockExpenseService()` from
 * ./mockService if you need to run with no backend again — no UI code
 * would need to change either way.
 */
export const expenseService: ExpenseServiceApi = new HttpExpenseService();
