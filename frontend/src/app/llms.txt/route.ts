/**
 * /llms.txt: plain-text briefing for AI systems, built at build time from the
 * facts file (src/lib/seo/llmsTxt.ts). Static export: force-static.
 */

import { llmsTxt } from "@/lib/seo/llmsTxt";

export const dynamic = "force-static";

export function GET() {
  return new Response(llmsTxt(), { headers: { "content-type": "text/plain; charset=utf-8" } });
}
