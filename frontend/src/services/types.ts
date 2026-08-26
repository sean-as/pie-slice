import type {
  BalancesResult,
  Expense,
  Group,
  Settlement,
  SplitMethod,
  User,
} from "../domain/types";

export type SignupInput = {
  email: string;
  password: string;
  displayName: string;
};

export type LoginInput = {
  email: string;
  password: string;
};

export type CreateGroupInput = {
  name: string;
};

export type AddExpenseInput = {
  description: string;
  amountCents: number;
  payerId: string;
  date: string;
  splitMethod: SplitMethod;
  /** Per-method raw input the service resolves into final cents (see domain/splitting.ts). */
  splitInput:
    | { method: "equal"; memberIds: string[] }
    | { method: "exact"; amounts: { memberId: string; amountCents: number }[] }
    | { method: "percent"; percentages: { memberId: string; percent: number }[] }
    | { method: "shares"; shares: { memberId: string; shares: number }[] };
};

export type UpdateExpenseInput = AddExpenseInput;

export type AddSettlementInput = {
  fromMemberId: string;
  toMemberId: string;
  amountCents: number;
  date: string;
  method?: string;
};

export type UpdateSettlementInput = AddSettlementInput;

/**
 * The one boundary every backend call crosses. All UI code talks to this
 * interface only — never to a specific transport (mock, HTTP, etc.) directly.
 * See services/mockService.ts for the no-backend implementation and
 * services/index.ts for which one is active.
 *
 * Every group/expense/settlement method requires an active session (see
 * signup/login) — the mock throws "Not authenticated." otherwise, matching
 * the real backend's requirement that every write derive "who did this"
 * from the session, never from client input. `createdByUserId` is never
 * accepted as an input field for this reason — it's always derived
 * server-side (mock-side) from the current session.
 */
export interface ExpenseServiceApi {
  signup(input: SignupInput): Promise<User>;
  login(input: LoginInput): Promise<User>;
  logout(): Promise<void>;
  getCurrentUser(): Promise<User | null>;

  /** Groups the current user is a linked member of. */
  listGroups(): Promise<Group[]>;
  createGroup(input: CreateGroupInput): Promise<Group>;
  /** Returns null if the group doesn't exist OR the current user isn't a linked member (same response either way — no leaking existence). */
  getGroup(groupId: string): Promise<Group | null>;
  /** Adds an existing user (looked up by email) as a linked member. */
  addLinkedMember(groupId: string, email: string): Promise<Group>;
  /** Adds a name-only member with no account. */
  addPlaceholderMember(groupId: string, displayName: string): Promise<Group>;

  listExpenses(groupId: string): Promise<Expense[]>;
  addExpense(groupId: string, input: AddExpenseInput): Promise<Expense>;
  /** Throws if the current user did not create this expense. */
  updateExpense(groupId: string, expenseId: string, input: UpdateExpenseInput): Promise<Expense>;
  /** Throws if the current user did not create this expense. */
  deleteExpense(groupId: string, expenseId: string): Promise<void>;

  listSettlements(groupId: string): Promise<Settlement[]>;
  addSettlement(groupId: string, input: AddSettlementInput): Promise<Settlement>;
  /** Throws if the current user did not create this settlement. */
  updateSettlement(
    groupId: string,
    settlementId: string,
    input: UpdateSettlementInput
  ): Promise<Settlement>;
  /** Throws if the current user did not create this settlement. */
  deleteSettlement(groupId: string, settlementId: string): Promise<void>;

  getBalances(groupId: string): Promise<BalancesResult>;
}
