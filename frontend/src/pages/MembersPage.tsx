import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import type { Group } from "../domain/types";
import { expenseService } from "../services";
import { useCurrentUser } from "../hooks/useCurrentUser";

export function MembersPage() {
  const { user, loading: userLoading } = useCurrentUser();
  const { groupId } = useParams<{ groupId: string }>();
  const [group, setGroup] = useState<Group | null | undefined>(undefined);
  const [editing, setEditing] = useState(false);

  const refresh = useCallback(async () => {
    if (!groupId || !user) return;
    setGroup(await expenseService.getGroup(groupId));
  }, [groupId, user]);

  useEffect(() => {
    refresh();
  }, [refresh]);

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

  const count = group.members.length;

  return (
    <div>
      <p className="meta">
        <Link to={`/group/${group.id}`}>← Back to group</Link>
      </p>
      <h1>{group.name}</h1>
      {group.description && <p>{group.description}</p>}
      <button type="button" className="secondary" onClick={() => setEditing((e) => !e)}>
        {count} member{count === 1 ? "" : "s"} · {editing ? "Done" : "Edit"}
      </button>

      <ul className="list">
        {group.members.map((m) => (
          <MemberRow
            key={m.id}
            group={group}
            memberId={m.id}
            editing={editing}
            isYou={m.userId === user.id}
            onChanged={setGroup}
          />
        ))}
      </ul>

      {editing && (
        <>
          <GroupDetailsForm group={group} onSaved={setGroup} />
          <AddMemberForms group={group} onChanged={setGroup} />
        </>
      )}
    </div>
  );
}

function MemberRow({
  group,
  memberId,
  editing,
  isYou,
  onChanged,
}: {
  group: Group;
  memberId: string;
  editing: boolean;
  isYou: boolean;
  onChanged: (g: Group) => void;
}) {
  const member = group.members.find((m) => m.id === memberId)!;
  const [name, setName] = useState(member.displayName);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<Group>, fallback: string) {
    setError(null);
    try {
      onChanged(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : fallback);
    }
  }

  return (
    <li className="card">
      <span>
        {editing && !member.userId ? (
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label={`Name for ${member.displayName}`}
          />
        ) : (
          member.displayName
        )}
        {isYou && <span className="meta"> · you</span>}
        {!member.userId && <span className="meta"> · no account</span>}
        {error && (
          <>
            <br />
            <span className="error">{error}</span>
          </>
        )}
      </span>
      {editing && (
        <span className="actions">
          {!member.userId && (
            <button
              type="button"
              className="secondary"
              disabled={!name.trim() || name.trim() === member.displayName}
              onClick={() => run(() => expenseService.renameMember(group.id, member.id, name), "Could not rename.")}
            >
              Save
            </button>
          )}
          {!isYou && (
            <button
              type="button"
              className="secondary"
              onClick={() => run(() => expenseService.removeMember(group.id, member.id), "Could not remove.")}
            >
              Remove
            </button>
          )}
        </span>
      )}
    </li>
  );
}

function GroupDetailsForm({ group, onSaved }: { group: Group; onSaved: (g: Group) => void }) {
  const [name, setName] = useState(group.name);
  const [description, setDescription] = useState(group.description ?? "");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Group name is required.");
      return;
    }
    try {
      onSaved(await expenseService.updateGroup(group.id, { name, description }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    }
  }

  return (
    <>
      <h2>Group details</h2>
      <form onSubmit={handleSubmit} className="inline-form">
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Group name" />
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)"
        />
        <button type="submit">Save</button>
      </form>
      {error && <p className="error">{error}</p>}
    </>
  );
}

function AddMemberForms({ group, onChanged }: { group: Group; onChanged: (g: Group) => void }) {
  const [linkedEmail, setLinkedEmail] = useState("");
  const [placeholderName, setPlaceholderName] = useState("");
  const [error, setError] = useState<string | null>(null);
  /** The name we've warned about; submitting it again confirms it. */
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);

  async function handleAddLinked(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const email = linkedEmail.trim();
    if (!email) return;
    try {
      onChanged(await expenseService.addLinkedMember(group.id, email));
      setLinkedEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add that member.");
    }
  }

  async function handleAddPlaceholder(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const name = placeholderName.trim();
    if (!name) return;

    const clashes = group.members.some((m) => m.displayName.trim().toLowerCase() === name.toLowerCase());
    if (clashes && duplicateWarning !== name) {
      setDuplicateWarning(name);
      return;
    }

    try {
      onChanged(await expenseService.addPlaceholderMember(group.id, name));
      setPlaceholderName("");
      setDuplicateWarning(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add that member.");
    }
  }

  return (
    <>
      <h2>Add members</h2>
      <form onSubmit={handleAddLinked} className="inline-form">
        <input
          type="email"
          value={linkedEmail}
          onChange={(e) => setLinkedEmail(e.target.value)}
          placeholder="Add by email (existing account)"
        />
        <button type="submit">Add</button>
      </form>
      <form onSubmit={handleAddPlaceholder} className="inline-form">
        <input
          type="text"
          value={placeholderName}
          onChange={(e) => {
            setPlaceholderName(e.target.value);
            setDuplicateWarning(null);
          }}
          placeholder="Add a name (no account)"
        />
        <button type="submit" className="secondary">
          Add placeholder
        </button>
      </form>
      {duplicateWarning && (
        <p className="warning">
          Someone in this group is already called “{duplicateWarning}” — that makes “who owes whom”
          ambiguous. Add it again to confirm.
        </p>
      )}
      {error && <p className="error">{error}</p>}
    </>
  );
}
