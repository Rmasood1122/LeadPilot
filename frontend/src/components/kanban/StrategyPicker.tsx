"use client";

import { useStrategies } from "@/lib/api/hooks";
import { Label } from "@/components/ui/input";

/** Shared strategy selector used by Pipeline / Campaigns / Analytics. */
export function StrategyPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (id: string) => void;
}) {
  const { data } = useStrategies();
  return (
    <div className="flex items-center gap-2">
      <Label htmlFor="strategy-picker" className="whitespace-nowrap">
        Strategy
      </Label>
      <select
        id="strategy-picker"
        className="h-10 rounded border border-border bg-card px-2 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Select…</option>
        {data?.map((s) => (
          <option key={s.id} value={s.id}>
            {(s as unknown as { product_name?: string }).product_name ?? s.id.slice(0, 8)}
          </option>
        ))}
      </select>
    </div>
  );
}
