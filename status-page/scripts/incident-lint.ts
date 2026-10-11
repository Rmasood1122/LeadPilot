/**
 * npm run incident-lint [dir]
 *
 * Validates every incident file's name and front matter with the same parser
 * the site uses (lib/incidents.ts). Exit 0 when every file is valid (or there
 * are none), 1 otherwise. Runs in CI on every status-page change, including
 * incident-only PRs.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { lintIncidentDir } from "../lib/incidents.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const dir = process.argv[2] ? path.resolve(process.argv[2]) : path.join(here, "..", "incidents");

const reports = lintIncidentDir(dir);
let failed = 0;
for (const { file, errors } of reports) {
  if (errors.length === 0) {
    console.log(`ok    ${file}`);
    continue;
  }
  failed += 1;
  console.log(`FAIL  ${file}`);
  for (const e of errors) console.log(`      - ${e}`);
}
console.log(
  `incident-lint: ${reports.length} file(s) checked in ${path.relative(process.cwd(), dir) || "."}, ${failed} invalid`,
);
process.exit(failed === 0 ? 0 : 1);
