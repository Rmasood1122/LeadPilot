/**
 * Email network ("Email contacts" tab of the Network page), pure parts.
 *  - wire: the upload is the RAW file body (never multipart), with the
 *    attestation in the query string; the Gmail scan posts the attestation.
 *  - rules: summary wording, file checks, saved-only attach, honest labels.
 * The page itself: emailNetworkPage.test.tsx.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import {
  attachEmailMessage, deleteEmailContact, startGmailScan, uploadEmailNetworkFile,
} from "@/lib/api/emailNetwork";
import {
  checkUploadFile, importErrorMessage, importSummary, isAttachable, isEditable,
  messageStatusLabel, openerDead, parseOwnAddresses, relationshipBadge, scanLine, validateEmail,
} from "@/lib/emailNetwork";
import type { EmailImport, EmailNetworkMessage } from "@/lib/api/emailNetwork";

const LIMITS = { mbox_max_bytes: 300 * 1048576, contacts_max_bytes: 20 * 1048576 };

const IMPORT: EmailImport = {
  id: "i1", kind: "mbox", status: "done", rows_in_file: 1240, messages_scanned: 1240,
  people_found: 1240, added: 600, updated: 30, excluded: 610,
  excluded_by_reason: [
    { reason: "automated", label: "newsletters / automated senders", count: 300 },
    { reason: "personal_domain", label: "personal email domains", count: 120 },
    { reason: "role_inbox", label: "role inboxes (info@, support@ ...)", count: 190 },
  ],
  cap_note: null, error: null, created_at: null, finished_at: null, matched: 42,
};

const msg = (status: EmailNetworkMessage["status"]): EmailNetworkMessage => ({
  id: "m1", contact_id: "c1", product_id: "p1", subject: "Hi", body: "Hello", status,
  strategy_id: null, lead_id: null, campaign_message_status: null, error: null,
});

describe("wire", () => {
  let calls: { url: string; init: RequestInit }[] = [];
  beforeEach(() => {
    calls = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it("uploads the raw file with the attestation in the query string", async () => {
    const file = new Blob(["From x@y Mon Oct 05 10:00:00 +0000 2026\n"]);
    await uploadEmailNetworkFile(file, "1", " me@corp.com ");
    const { url, init } = calls[0];
    expect(url).toContain("/email-network/import?");
    expect(url).toContain("attested=true");
    expect(url).toContain("attestation_version=1");
    expect(url).not.toContain("own_addresses");          // never in the URL / access logs
    expect((init.headers as Record<string, string>)["X-Own-Addresses"]).toBe("me%40corp.com");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(file);
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/octet-stream");
  });

  it("sends no own-addresses header when none were typed", async () => {
    await uploadEmailNetworkFile(new Blob(["x"]), "1", "  ");
    expect((calls[0].init.headers as Record<string, string>)["X-Own-Addresses"]).toBeUndefined();
  });

  it("deletes one contact by id", async () => {
    await deleteEmailContact("c9");
    expect(calls[0].url).toMatch(/\/email-network\/contacts\/c9$/);
    expect(calls[0].init.method).toBe("DELETE");
  });

  it("starts a Gmail scan with the attestation", async () => {
    await startGmailScan("1", ["me@corp.com"]);
    expect(calls[0].url).toMatch(/\/email-network\/gmail-scan$/);
    expect(JSON.parse(calls[0].init.body as string)).toEqual(
      { attested: true, attestation_version: "1", own_addresses: ["me@corp.com"] });
  });

  it("attaches by campaign id only", async () => {
    await attachEmailMessage("m1", "s1");
    expect(calls[0].url).toMatch(/\/email-network\/messages\/m1\/attach$/);
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ strategy_id: "s1" });
  });
});

describe("rules", () => {
  it("summarises imports with exclusion reasons", () => {
    expect(importSummary(IMPORT)).toBe(
      "1,240 people found, 610 excluded: 300 newsletters / automated senders, " +
      "120 personal email domains, 190 role inboxes (info@, support@ ...). " +
      "600 added, 30 updated; 42 matches for your products.");
  });

  it("checks files before uploading", () => {
    expect(checkUploadFile({ name: "a.csv", size: 0 }, LIMITS)).toBe("That file is empty.");
    expect(checkUploadFile({ name: "a.csv", size: 21 * 1048576 }, LIMITS)).toMatch(/20 MB/);
    expect(checkUploadFile({ name: "All mail.mbox", size: 200 * 1048576 }, LIMITS)).toBeNull();
    expect(checkUploadFile({ name: "All mail.mbox", size: 301 * 1048576 }, LIMITS)).toMatch(/300 MB/);
  });

  it("only saved words can be attached; attached words are not editable", () => {
    expect(isAttachable(msg("draft"))).toBe(false);
    expect(isAttachable(msg("approved"))).toBe(true);
    expect(isEditable(msg("attached"))).toBe(false);
    expect(isEditable(msg("used"))).toBe(false);
    expect(messageStatusLabel(msg("draft"))).toBe("Draft (not saved)");
    expect(messageStatusLabel(msg("attached"))).toMatch(/every check/);
    expect(openerDead({ ...msg("used"), campaign_message_status: "cancelled" })).toBe(true);
    expect(openerDead({ ...msg("used"), campaign_message_status: "sent" })).toBe(false);
  });

  it("validates subject and body", () => {
    expect(validateEmail("", "x")).toMatch(/subject/);
    expect(validateEmail("s", " ")).toMatch(/email/);
    expect(validateEmail("s", "b")).toBeNull();
  });

  it("labels the relationship honestly", () => {
    expect(relationshipBadge({ two_way: true, sent_to_count: 3, received_from_count: 2 })).toBe("Two-way");
    expect(relationshipBadge({ two_way: false, sent_to_count: 0, received_from_count: 2 })).toBe("They wrote");
    expect(relationshipBadge({ two_way: false, sent_to_count: 0, received_from_count: 0 })).toBe("Contacts file");
  });

  it("reports scan progress and reconnects", () => {
    expect(scanLine({ ...IMPORT, status: "running", messages_scanned: 300, max_messages: 5000 }))
      .toBe("Scanning Gmail headers… 300 of up to 5,000 messages read.");
    expect(scanLine({ ...IMPORT, status: "reconnect_required", error: null }))
      .toMatch(/Reconnect Gmail/);
  });

  it("maps errors", () => {
    expect(importErrorMessage(new ApiError(402, "x"))).toMatch(/Growth/);
    expect(importErrorMessage(new ApiError(422, "Confirm first."))).toBe("Confirm first.");
    expect(parseOwnAddresses("A@x.com, bad, b@y.org;a@x.com")).toEqual(["a@x.com", "b@y.org"]);
  });
});
