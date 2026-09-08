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
  /** Optional free text: typed by hand or from a mapped CSV column. */
  category?: string | null;
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
  /** From the mapped category column, if any. */
  category?: string | null;
  /**
   * True when this user has imported this merchant into this group before,
   * so the UI ticks it by default. A default, not a decision — the user can
   * untick it, and ticking a new merchant is equally allowed. Never true
   * for a row that is already imported.
   */
  preselected: boolean;
  /**
   * True when this exact transaction was already imported by this user into
   * this group. Still shown and still importable: the check compares date,
   * merchant and amount, which can't tell a re-uploaded statement from two
   * identical real charges — so the user decides, warned.
   */
  alreadyImported: boolean;
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
};

export type DateFormat = "iso" | "mdy" | "dmy";
export type AmountSign = "positive_is_charge" | "negative_is_charge";

/**
 * How to read one bank's CSV export. Banks disagree on column names, on
 * which sign means a charge, and on date order, so all three are the
 * user's to set — with whatever the app can safely detect pre-filled.
 */
export type ColumnMapping = {
  dateColumn: string;
  descriptionColumn: string;
  amountColumn: string;
  dateFormat: DateFormat;
  amountSign: AmountSign;
  /**
   * Optional in a way the other three are not: null means "this file has no
   * category column", which never blocks an import.
   */
  categoryColumn?: string | null;
};

/**
 * What a file looks like before any transaction is read from it. Nothing
 * has been parsed into transactions and nothing is stored at this point.
 */
export type FileShape = {
  columns: string[];
  /** A few raw data rows, keyed by column name, to check the mapping against. */
  sampleRows: Record<string, string>[];
  suggested: ColumnMapping;
  /** Roles ("date"/"description"/"amount") the app couldn't work out. */
  unresolved: string[];
  /** True when MM/DD and DD/MM can't be told apart from this file's data. */
  dateFormatAmbiguous: boolean;
};
