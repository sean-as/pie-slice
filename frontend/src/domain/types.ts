/** Never carries a password/passwordHash — this is what's safe to hand to the UI. */
export type User = {
  id: string;
  email: string;
  displayName: string;
};

/**
 * A group member is either linked to a real account (userId set — that
 * user can log in and act on the group) or a placeholder (userId null —
 * just a name, can be a payer/split participant, but can't log in).
 */
export type Member = {
  id: string;
  displayName: string;
  userId: string | null;
};

export type Group = {
  id: string;
  name: string;
  members: Member[];
};

export type SplitMethod = "equal" | "exact" | "percent" | "shares";

/** Final per-member cents, always resolved at save time regardless of method used to build it. */
export type Split = {
  memberId: string;
  amountCents: number;
};

export type Expense = {
  id: string;
  groupId: string;
  description: string;
  amountCents: number;
  payerId: string;
  date: string; // ISO date, e.g. "2026-08-26"
  splitMethod: SplitMethod;
  splits: Split[];
  /** Whoever was logged in when this was created — only they may edit/delete it. */
  createdByUserId: string;
};

export type Settlement = {
  id: string;
  groupId: string;
  fromMemberId: string;
  toMemberId: string;
  amountCents: number;
  date: string;
  method?: string;
  /** Whoever was logged in when this was created — only they may edit/delete it. */
  createdByUserId: string;
};

export type MemberBalance = {
  memberId: string;
  netCents: number; // positive = owed money by the group, negative = owes the group
};

export type SettleUpTransfer = {
  fromMemberId: string;
  toMemberId: string;
  amountCents: number;
};

export type BalancesResult = {
  balances: MemberBalance[];
  settleUp: SettleUpTransfer[];
};

/**
 * One parsed CSV transaction awaiting the user's yes/no. Nothing exists in
 * the group for it yet — `confirmImport` is what creates expenses.
 */
export type ReviewRow = {
  id: string;
  date: string;
  description: string;
  amountCents: number;
  /**
   * True when this user has imported this merchant into this group before,
   * so the UI ticks it by default. A default, not a decision — the user can
   * untick it, and ticking a new merchant is equally allowed.
   */
  preselected: boolean;
};

/** A CSV row that couldn't be parsed. Reported to the user, never fatal. */
export type SkippedRow = {
  line: number;
  reason: string;
};

export type ImportPreview = {
  importId: string;
  rows: ReviewRow[];
  skipped: SkippedRow[];
  /** Rows left out because this user already imported them into this group. */
  duplicateCount: number;
};
