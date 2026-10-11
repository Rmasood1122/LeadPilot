"use client";

import { useEffect, useState } from "react";

import { formatUtc } from "../lib/format.ts";

/**
 * A UTC timestamp, server-rendered (readable without JavaScript). After
 * hydration the tooltip shows the same moment in the reader's local time zone.
 */
export function LocalTime({ iso }: { iso: string }) {
  const [title, setTitle] = useState("Times are shown in UTC");
  useEffect(() => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return;
    const local = new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZoneName: "short",
    }).format(d);
    setTitle(`Your local time: ${local}`);
  }, [iso]);
  return (
    <time dateTime={iso} title={title}>
      {formatUtc(iso)}
    </time>
  );
}
