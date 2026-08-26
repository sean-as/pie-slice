import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Group } from "../domain/types";
import { expenseService } from "../services";
import { useCurrentUser } from "../hooks/useCurrentUser";

export function HomePage() {
  const { user, loading } = useCurrentUser();

  if (loading) return <p>Loading…</p>;

  if (!user) {
    return (
      <div>
        <h1>Split expenses with your group</h1>
        <p>Real accounts — sign up, log in, and see the groups you're in.</p>
        <div className="actions">
          <Link to="/signup">
            <button type="button">Sign up</button>
          </Link>
          <Link to="/login">
            <button type="button" className="secondary">
              Log in
            </button>
          </Link>
        </div>
      </div>
    );
  }

  return <GroupsList displayName={user.displayName} />;
}

function GroupsList({ displayName }: { displayName: string }) {
  const navigate = useNavigate();
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [groupName, setGroupName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const refresh = useCallback(async () => {
    setGroups(await expenseService.listGroups());
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleCreateGroup(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const name = groupName.trim();
    if (!name) {
      setError("Group name is required.");
      return;
    }
    setSubmitting(true);
    try {
      const group = await expenseService.createGroup({ name });
      navigate(`/group/${group.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the group.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1>Welcome, {displayName}</h1>

      <h2>Your groups</h2>
      {groups === null ? (
        <p>Loading…</p>
      ) : groups.length === 0 ? (
        <p className="meta">You're not in any groups yet.</p>
      ) : (
        <ul className="list">
          {groups.map((g) => (
            <li key={g.id} className="card">
              <Link to={`/group/${g.id}`}>{g.name}</Link>
              <span className="meta">{g.members.length} members</span>
            </li>
          ))}
        </ul>
      )}

      <h2>New group</h2>
      <form onSubmit={handleCreateGroup} className="inline-form">
        <input
          type="text"
          value={groupName}
          onChange={(e) => setGroupName(e.target.value)}
          placeholder="Cabin trip"
        />
        <button type="submit" disabled={submitting}>
          {submitting ? "Creating…" : "Create group"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
