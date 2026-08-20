"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { hasSession } from "@/lib/api/client";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(hasSession() ? "/pipeline" : "/login");
  }, [router]);
  return null;
}
