import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import type { Group } from "../domain/types";
import { expenseService } from "../services";
import { ExpenseForm } from "../components/ExpenseForm";
import { CsvImportPanel } from "../components/CsvImportPanel";
import { useCurrentUser } from "../hooks/useCurrentUser";

/** Where expenses get added: by hand, or in bulk from a CSV statement. */
export function AddExpensePage() {
  const { user, loading: userLoading } = useCurrentUser();
  const { groupId } = useParams<{ groupId: string }>();
  const navigate = useNavigate();
  const [group, setGroup] = useState<Group | null | undefined>(undefined);
  const [mode, setMode] = useState<"manual" | "csv">("manual");

  useEffect(() => {
    if (!groupId || !user) return;
    expenseService.getGroup(groupId).then(setGroup);
  }, [groupId, user]);

  if (userLoading || group === undefined) return <p>Loading…</p>;
  if (!user) return <Navigate to="/login" replace />;
  if (group === null) {
    return (
      <div>
        <h1>Group not found</h1>
        <p>This group doesn't exist, or you're not a member of it.</p>
      </div>
    );
  }

  const back = `/group/${group.id}`;

  return (
    <div>
      <p className="meta">
        <Link to={back}>← Back to {group.name}</Link>
      </p>
      <h1>Add expense</h1>
      <div className="actions">
        <button type="button" className={mode === "manual" ? "" : "secondary"} onClick={() => setMode("manual")}>
          Enter manually
        </button>
        <button type="button" className={mode === "csv" ? "" : "secondary"} onClick={() => setMode("csv")}>
          Import from CSV
        </button>
      </div>

      {mode === "manual" ? (
        <ExpenseForm
          members={group.members}
          onCancel={() => navigate(back)}
          onSubmit={async (input) => {
            await expenseService.addExpense(group.id, input);
            navigate(back);
          }}
        />
      ) : (
        <CsvImportPanel groupId={group.id} onImported={async () => navigate(back)} />
      )}
    </div>
  );
}
