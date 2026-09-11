"use client";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function formatHour(h: number) {
  const period = h >= 12 ? "PM" : "AM";
  const display = h % 12 === 0 ? 12 : h % 12;
  return `${display}:00 ${period}`;
}

interface SendTimeCardProps {
  channel?: string;
  icpIndustry?: string;
  icpCompanySize?: string;
}

export function SendTimeCard({
  channel = "gmail",
  icpIndustry,
  icpCompanySize,
}: SendTimeCardProps) {
  const params = new URLSearchParams({ channel });
  if (icpIndustry) params.set("icp_industry", icpIndustry);
  if (icpCompanySize) params.set("icp_company_size", icpCompanySize);

  const { data, isLoading } = useQuery({
    queryKey: ["send-times", channel, icpIndustry, icpCompanySize],
    queryFn: () => apiClient.get(`/playbook/send-times?${params}`),
  });

  if (isLoading) {
    return (
      <div className="rounded-lg border bg-card p-4 space-y-2">
        <h3 className="font-semibold text-sm">Best time to send</h3>
        <div className="text-xs text-muted-foreground">Loading…</div>
      </div>
    );
  }

  const slots: any[] = data?.recommended_slots ?? [];
  const confidence: string = data?.confidence ?? "no_data";
  const fallback: boolean = data?.fallback_used ?? true;

  const confidenceColor: Record<string, string> = {
    high: "text-green-600",
    medium: "text-amber-600",
    low: "text-muted-foreground",
    no_data: "text-muted-foreground",
  };

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm">Best time to send</h3>
        <span className={`text-xs font-medium ${confidenceColor[confidence] ?? ""}`}>
          {confidence === "no_data" ? "No data yet" : `${confidence} confidence`}
          {fallback && confidence === "no_data" && " — showing defaults"}
        </span>
      </div>

      {slots.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No send-time data yet. Run more campaigns to build recommendations.
        </p>
      ) : (
        <div className="space-y-1.5">
          {slots.slice(0, 3).map((slot: any, i: number) => (
            <div key={i} className="flex items-center justify-between text-sm">
              <span className="font-medium">
                {DAY_NAMES[slot.day_of_week]} {formatHour(slot.hour_utc)} UTC
              </span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">
                  {(slot.expected_reply_rate * 100).toFixed(1)}% reply rate
                </span>
                {!slot.is_reliable && (
                  <span className="text-[10px] text-amber-500">(limited data)</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="text-[10px] text-muted-foreground">
        Based on {channel} outcomes{icpIndustry ? ` · ${icpIndustry}` : ""}.
        Schedules prefer these windows automatically.
      </p>
    </div>
  );
}
