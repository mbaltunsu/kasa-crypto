"use client";

import { Select } from "@/components/ui/Select";
import { useUsers } from "@/api/queries";

/** A dropdown of Kasa users (by email) for the transfer / mint recipient pickers. Demo
 * convenience so people can switch between seeded accounts without typing emails. */
export function UserSelect({
  id,
  value,
  onChange,
  excludeEmail,
  placeholder = "Select a user…",
  disabled,
}: {
  id?: string;
  value: string;
  onChange: (email: string) => void;
  excludeEmail?: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  const users = useUsers().data ?? [];
  const options = excludeEmail ? users.filter((u) => u.email !== excludeEmail) : users;
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
      <option value="" disabled>
        {placeholder}
      </option>
      {options.map((u) => (
        <option key={u.id} value={u.email}>
          {u.email}
        </option>
      ))}
    </Select>
  );
}
