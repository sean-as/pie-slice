import type { Expense, Group, Member, Settlement, User } from "../domain/types";
import { computeBalances } from "../domain/balances";
import { splitEqual, splitExact, splitPercent, splitShares } from "../domain/splitting";
import type {
  AddExpenseInput,
  AddSettlementInput,
  CreateGroupInput,
  ExpenseServiceApi,
  LoginInput,
  SignupInput,
  UpdateExpenseInput,
  UpdateSettlementInput,
} from "./types";

const STORAGE_KEY = "pie-slice:mock-db";
const SESSION_KEY = "pie-slice:session";
const SIMULATED_LATENCY_MS = 150;

type StoredUser = User & { passwordHash: string };

type Db = {
  users: Record<string, StoredUser>;
  groups: Record<string, Group>;
  expenses: Record<string, Expense[]>;
  settlements: Record<string, Settlement[]>;
};

function emptyDb(): Db {
  return { users: {}, groups: {}, expenses: {}, settlements: {} };
}

function loadDb(): Db {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return emptyDb();
  try {
    return JSON.parse(raw) as Db;
  } catch {
    return emptyDb();
  }
}

function saveDb(db: Db): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(db));
}

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), SIMULATED_LATENCY_MS));
}

function id(): string {
  return crypto.randomUUID();
}

function toPublicUser(user: StoredUser): User {
  const { passwordHash: _passwordHash, ...publicUser } = user;
  return publicUser;
}

/**
 * SHA-256 of the password — NOT how a real backend should hash passwords
 * (see product-spec.md: needs a slow hash like bcrypt/argon2). This mock
 * only needs to avoid storing plaintext in localStorage; it isn't a
 * security boundary.
 */
async function hashPassword(password: string): Promise<string> {
  const bytes = new TextEncoder().encode(password);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function getSessionUserId(): string | null {
  return localStorage.getItem(SESSION_KEY);
}

function setSessionUserId(userId: string | null): void {
  if (userId) localStorage.setItem(SESSION_KEY, userId);
  else localStorage.removeItem(SESSION_KEY);
}

function requireSessionUserId(): string {
  const userId = getSessionUserId();
  if (!userId) throw new Error("Not authenticated.");
  return userId;
}

function requireMembership(group: Group | undefined, userId: string): Group {
  const isMember = !!group && group.members.some((m) => m.userId === userId);
  if (!isMember || !group) {
    // Same error for "doesn't exist" and "exists but you're not a member" —
    // never leak which one it is.
    throw new Error("Group not found.");
  }
  return group;
}

function resolveSplits(amountCents: number, splitInput: AddExpenseInput["splitInput"]) {
  switch (splitInput.method) {
    case "equal":
      return splitEqual(amountCents, splitInput.memberIds);
    case "exact":
      return splitExact(amountCents, splitInput.amounts);
    case "percent":
      return splitPercent(amountCents, splitInput.percentages);
    case "shares":
      return splitShares(amountCents, splitInput.shares);
  }
}

/**
 * In-memory/localStorage implementation of ExpenseServiceApi — the whole
 * app runs against this, no backend required. Swap services/index.ts to a
 * real HTTP implementation later without touching any UI code.
 */
export class MockExpenseService implements ExpenseServiceApi {
  async signup(input: SignupInput): Promise<User> {
    const db = loadDb();
    const email = input.email.trim().toLowerCase();
    if (Object.values(db.users).some((u) => u.email === email)) {
      throw new Error("An account with that email already exists.");
    }
    if (!email || !input.displayName.trim() || input.password.length < 8) {
      throw new Error("Email, display name, and an 8+ character password are required.");
    }

    const user: StoredUser = {
      id: id(),
      email,
      displayName: input.displayName.trim(),
      passwordHash: await hashPassword(input.password),
    };
    db.users[user.id] = user;
    saveDb(db);
    setSessionUserId(user.id);
    return delay(toPublicUser(user));
  }

  async login(input: LoginInput): Promise<User> {
    const db = loadDb();
    const email = input.email.trim().toLowerCase();
    const user = Object.values(db.users).find((u) => u.email === email);
    const passwordHash = await hashPassword(input.password);

    // Generic error either way — never reveal whether the email exists.
    if (!user || user.passwordHash !== passwordHash) {
      throw new Error("Invalid email or password.");
    }

    setSessionUserId(user.id);
    return delay(toPublicUser(user));
  }

  async logout(): Promise<void> {
    setSessionUserId(null);
    return delay(undefined);
  }

  async getCurrentUser(): Promise<User | null> {
    const db = loadDb();
    const userId = getSessionUserId();
    const user = userId ? db.users[userId] : undefined;
    return delay(user ? toPublicUser(user) : null);
  }

  async listGroups(): Promise<Group[]> {
    const db = loadDb();
    const userId = requireSessionUserId();
    return delay(Object.values(db.groups).filter((g) => g.members.some((m) => m.userId === userId)));
  }

  async createGroup(input: CreateGroupInput): Promise<Group> {
    const db = loadDb();
    const userId = requireSessionUserId();
    const creator = db.users[userId];
    if (!creator) throw new Error("Not authenticated.");

    const group: Group = {
      id: id(),
      name: input.name,
      members: [{ id: id(), displayName: creator.displayName, userId: creator.id }],
    };
    db.groups[group.id] = group;
    db.expenses[group.id] = [];
    db.settlements[group.id] = [];
    saveDb(db);
    return delay(group);
  }

  async getGroup(groupId: string): Promise<Group | null> {
    const db = loadDb();
    const userId = requireSessionUserId();
    const group = db.groups[groupId];
    const isMember = !!group && group.members.some((m) => m.userId === userId);
    return delay(isMember ? group! : null);
  }

  async addLinkedMember(groupId: string, email: string): Promise<Group> {
    const db = loadDb();
    const userId = requireSessionUserId();
    const group = requireMembership(db.groups[groupId], userId);

    const normalizedEmail = email.trim().toLowerCase();
    const target = Object.values(db.users).find((u) => u.email === normalizedEmail);
    if (!target) {
      throw new Error("No account found for that email.");
    }
    if (group.members.some((m) => m.userId === target.id)) {
      throw new Error("That person is already in the group.");
    }

    const member: Member = { id: id(), displayName: target.displayName, userId: target.id };
    group.members.push(member);
    saveDb(db);
    return delay(group);
  }

  async addPlaceholderMember(groupId: string, displayName: string): Promise<Group> {
    const db = loadDb();
    const userId = requireSessionUserId();
    const group = requireMembership(db.groups[groupId], userId);

    const name = displayName.trim();
    if (!name) throw new Error("Name is required.");

    const member: Member = { id: id(), displayName: name, userId: null };
    group.members.push(member);
    saveDb(db);
    return delay(group);
  }

  async listExpenses(groupId: string): Promise<Expense[]> {
    const db = loadDb();
    const userId = requireSessionUserId();
    requireMembership(db.groups[groupId], userId);
    return delay(db.expenses[groupId] ?? []);
  }

  async addExpense(groupId: string, input: AddExpenseInput): Promise<Expense> {
    const db = loadDb();
    const userId = requireSessionUserId();
    requireMembership(db.groups[groupId], userId);

    const expense: Expense = {
      id: id(),
      groupId,
      description: input.description,
      amountCents: input.amountCents,
      payerId: input.payerId,
      date: input.date,
      splitMethod: input.splitMethod,
      splits: resolveSplits(input.amountCents, input.splitInput),
      createdByUserId: userId,
    };

    db.expenses[groupId] = [...(db.expenses[groupId] ?? []), expense];
    saveDb(db);
    return delay(expense);
  }

  async updateExpense(groupId: string, expenseId: string, input: UpdateExpenseInput): Promise<Expense> {
    const db = loadDb();
    const userId = requireSessionUserId();
    requireMembership(db.groups[groupId], userId);

    const list = db.expenses[groupId] ?? [];
    const index = list.findIndex((e) => e.id === expenseId);
    if (index === -1) throw new Error("Expense not found.");
    if (list[index].createdByUserId !== userId) {
      throw new Error("Only the person who logged this expense can edit it.");
    }

    const updated: Expense = {
      ...list[index],
      description: input.description,
      amountCents: input.amountCents,
      payerId: input.payerId,
      date: input.date,
      splitMethod: input.splitMethod,
      splits: resolveSplits(input.amountCents, input.splitInput),
    };

    list[index] = updated;
    db.expenses[groupId] = list;
    saveDb(db);
    return delay(updated);
  }

  async deleteExpense(groupId: string, expenseId: string): Promise<void> {
    const db = loadDb();
    const userId = requireSessionUserId();
    requireMembership(db.groups[groupId], userId);

    const list = db.expenses[groupId] ?? [];
    const existing = list.find((e) => e.id === expenseId);
    if (existing && existing.createdByUserId !== userId) {
      throw new Error("Only the person who logged this expense can delete it.");
    }

    db.expenses[groupId] = list.filter((e) => e.id !== expenseId);
    saveDb(db);
    return delay(undefined);
  }

  async listSettlements(groupId: string): Promise<Settlement[]> {
    const db = loadDb();
    const userId = requireSessionUserId();
    requireMembership(db.groups[groupId], userId);
    return delay(db.settlements[groupId] ?? []);
  }

  async addSettlement(groupId: string, input: AddSettlementInput): Promise<Settlement> {
    const db = loadDb();
    const userId = requireSessionUserId();
    requireMembership(db.groups[groupId], userId);

    const settlement: Settlement = { id: id(), groupId, ...input, createdByUserId: userId };
    db.settlements[groupId] = [...(db.settlements[groupId] ?? []), settlement];
    saveDb(db);
    return delay(settlement);
  }

  async updateSettlement(
    groupId: string,
    settlementId: string,
    input: UpdateSettlementInput
  ): Promise<Settlement> {
    const db = loadDb();
    const userId = requireSessionUserId();
    requireMembership(db.groups[groupId], userId);

    const list = db.settlements[groupId] ?? [];
    const index = list.findIndex((s) => s.id === settlementId);
    if (index === -1) throw new Error("Settlement not found.");
    if (list[index].createdByUserId !== userId) {
      throw new Error("Only the person who recorded this settlement can edit it.");
    }

    const updated: Settlement = { ...list[index], ...input };
    list[index] = updated;
    db.settlements[groupId] = list;
    saveDb(db);
    return delay(updated);
  }

  async deleteSettlement(groupId: string, settlementId: string): Promise<void> {
    const db = loadDb();
    const userId = requireSessionUserId();
    requireMembership(db.groups[groupId], userId);

    const list = db.settlements[groupId] ?? [];
    const existing = list.find((s) => s.id === settlementId);
    if (existing && existing.createdByUserId !== userId) {
      throw new Error("Only the person who recorded this settlement can delete it.");
    }

    db.settlements[groupId] = list.filter((s) => s.id !== settlementId);
    saveDb(db);
    return delay(undefined);
  }

  async getBalances(groupId: string) {
    const db = loadDb();
    const userId = requireSessionUserId();
    const group = requireMembership(db.groups[groupId], userId);
    const memberIds = group.members.map((m) => m.id);
    return delay(computeBalances(memberIds, db.expenses[groupId] ?? [], db.settlements[groupId] ?? []));
  }
}
