import type {
  BalancesResult,
  Expense,
  Group,
  ImportPreview,
  Settlement,
  User,
} from "../domain/types";
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

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";
const TOKEN_KEY = "pie-slice:token";

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    // A FormData body must set its own Content-Type: the browser adds the
    // multipart boundary, which we can't know here — forcing JSON would
    // make the server unable to find the file part.
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const body: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const detail = (body as { detail?: string } | null)?.detail ?? `Request failed (${response.status}).`;
    throw new ApiError(response.status, detail);
  }

  return body as T;
}

type AuthResponse = { user: User; token: string };

/**
 * Talks to the FastAPI backend (../../backend) over HTTP, implementing the
 * exact same ExpenseServiceApi as services/mockService.ts. The two request/
 * response shapes were designed to match ../../openapi.yaml's schemas
 * field-for-field, so request bodies here are passed straight through with
 * no translation layer.
 */
export class HttpExpenseService implements ExpenseServiceApi {
  async signup(input: SignupInput): Promise<User> {
    const { user, token } = await request<AuthResponse>("/auth/signup", {
      method: "POST",
      body: JSON.stringify(input),
    });
    setToken(token);
    return user;
  }

  async login(input: LoginInput): Promise<User> {
    const { user, token } = await request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(input),
    });
    setToken(token);
    return user;
  }

  async logout(): Promise<void> {
    try {
      await request<void>("/auth/logout", { method: "POST" });
    } finally {
      setToken(null);
    }
  }

  async getCurrentUser(): Promise<User | null> {
    if (!getToken()) {
      return null;
    }
    try {
      return await request<User>("/auth/me");
    } catch {
      // Covers an expired/invalid token (401) and any other failure — this
      // is a "can I confirm you're logged in" check, not meant to throw.
      setToken(null);
      return null;
    }
  }

  async listGroups(): Promise<Group[]> {
    return request<Group[]>("/groups");
  }

  async createGroup(input: CreateGroupInput): Promise<Group> {
    return request<Group>("/groups", { method: "POST", body: JSON.stringify(input) });
  }

  async getGroup(groupId: string): Promise<Group | null> {
    try {
      return await request<Group>(`/groups/${groupId}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  }

  async addLinkedMember(groupId: string, email: string): Promise<Group> {
    return request<Group>(`/groups/${groupId}/members/linked`, {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  }

  async addPlaceholderMember(groupId: string, displayName: string): Promise<Group> {
    return request<Group>(`/groups/${groupId}/members/placeholder`, {
      method: "POST",
      body: JSON.stringify({ displayName }),
    });
  }

  async listExpenses(groupId: string): Promise<Expense[]> {
    return request<Expense[]>(`/groups/${groupId}/expenses`);
  }

  async addExpense(groupId: string, input: AddExpenseInput): Promise<Expense> {
    return request<Expense>(`/groups/${groupId}/expenses`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  async updateExpense(groupId: string, expenseId: string, input: UpdateExpenseInput): Promise<Expense> {
    return request<Expense>(`/groups/${groupId}/expenses/${expenseId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  }

  async deleteExpense(groupId: string, expenseId: string): Promise<void> {
    await request<void>(`/groups/${groupId}/expenses/${expenseId}`, { method: "DELETE" });
  }

  async listSettlements(groupId: string): Promise<Settlement[]> {
    return request<Settlement[]>(`/groups/${groupId}/settlements`);
  }

  async addSettlement(groupId: string, input: AddSettlementInput): Promise<Settlement> {
    return request<Settlement>(`/groups/${groupId}/settlements`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  async updateSettlement(
    groupId: string,
    settlementId: string,
    input: UpdateSettlementInput
  ): Promise<Settlement> {
    return request<Settlement>(`/groups/${groupId}/settlements/${settlementId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  }

  async deleteSettlement(groupId: string, settlementId: string): Promise<void> {
    await request<void>(`/groups/${groupId}/settlements/${settlementId}`, { method: "DELETE" });
  }

  async getBalances(groupId: string): Promise<BalancesResult> {
    return request<BalancesResult>(`/groups/${groupId}/balances`);
  }

  async uploadCsv(groupId: string, file: File): Promise<ImportPreview> {
    const body = new FormData();
    body.append("file", file);
    return request<ImportPreview>(`/groups/${groupId}/imports`, { method: "POST", body });
  }

  async confirmImport(groupId: string, importId: string, rowIds: string[]): Promise<Expense[]> {
    const result = await request<{ imported: Expense[] }>(
      `/groups/${groupId}/imports/${importId}/confirm`,
      { method: "POST", body: JSON.stringify({ rowIds }) }
    );
    return result.imported;
  }
}
