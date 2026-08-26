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
