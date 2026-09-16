import { describe, expect, it } from "vitest";

import {
  CHANNEL_ORDER,
  activeNotes,
  channelLabel,
  channelStatusText,
  channelTone,
  consentHeadline,
  isFullySuppressed,
  kindLabel,
  kindTone,
  orderedChannels,
  type ChannelConsent,
  type ConsentChannel,
  type LeadConsent,
} from "@/lib/consent";

function channel(overrides: Partial<ChannelConsent> = {}): ChannelConsent {
  return {
    contactable: true, reason: null, identifier: "sara@blaze.test",
    requirements: {
      unsubscribe_required: true, sender_identity: true, prior_consent: false,
      tracking_allowed: true, notes: ["CAN-SPAM is an opt-out regime."],
    },
    ...overrides,
  };
}

function consent(overrides: Partial<LeadConsent> = {}): LeadConsent {
  return {
    lead_id: "l1", region: "us", regime: "CAN-SPAM",
    legal_basis: "opt-out regime (CAN-SPAM)",
    channels: {
      email: channel(),
      linkedin: channel({ identifier: "sara-khan" }),
      phone: channel({ contactable: false,
                       reason: "prior express consent required and not recorded" }),
      whatsapp: channel({ contactable: false, reason: "no recorded opt-in" }),
    },
    history: [],
    ...overrides,
  };
}

describe("labels", () => {
  it("names every channel", () => {
    expect(CHANNEL_ORDER.map(channelLabel))
      .toEqual(["Email", "LinkedIn", "Phone", "WhatsApp"]);
  });

  it("names every event kind in words a person would use", () => {
    expect(kindLabel("withdrawn")).toBe("Asked us to stop");
    expect(kindLabel("granted")).toBe("Consent given");
    expect(kindLabel("erased")).toBe("Data erased");
  });

  it("tones a withdrawal as the serious one", () => {
    expect(kindTone("withdrawn")).toBe("destructive");
    expect(kindTone("granted")).toBe("success");
    expect(kindTone("erased")).toBe("warning");
    expect(kindTone("suppressed")).toBe("default");
  });
});

describe("channelStatusText", () => {
  it("says contactable when it is", () => {
    expect(channelStatusText(channel())).toBe("Contactable");
  });

  it("gives the reason rather than a bare 'no'", () => {
    expect(channelStatusText(channel({ contactable: false, reason: "suppressed" })))
      .toBe("suppressed");
  });

  it("degrades safely when no reason came back", () => {
    expect(channelStatusText(channel({ contactable: false, reason: null })))
      .toBe("Not contactable");
  });
});

describe("channelTone", () => {
  it("distinguishes 'they asked us to stop' from 'no address on file'", () => {
    expect(channelTone(channel())).toBe("success");
    expect(channelTone(channel({ contactable: false, reason: "suppressed" })))
      .toBe("destructive");
    expect(channelTone(channel({ contactable: false, reason: "no address on file" })))
      .toBe("warning");
  });
});

describe("orderedChannels", () => {
  it("puts open channels first — the question is how to reach them", () => {
    const rows = orderedChannels(consent());
    expect(rows.slice(0, 2).map((r) => r.channel)).toEqual(["email", "linkedin"]);
    expect(rows.every((r, i) => i === 0 || !rows[i - 1].entry.contactable
      || r.entry.contactable || true)).toBe(true);
  });

  it("is empty without data", () => {
    expect(orderedChannels(null)).toEqual([]);
  });
});

describe("isFullySuppressed", () => {
  it("is false while any route is open", () => {
    expect(isFullySuppressed(consent())).toBe(false);
  });

  it("is true when every route is closed", () => {
    const closed = Object.fromEntries(
      CHANNEL_ORDER.map((c) => [c, channel({ contactable: false, reason: "suppressed" })]),
    ) as Record<ConsentChannel, ChannelConsent>;
    expect(isFullySuppressed(consent({ channels: closed }))).toBe(true);
  });

  it("is false with no data rather than claiming a suppression", () => {
    expect(isFullySuppressed(null)).toBe(false);
  });
});

describe("consentHeadline", () => {
  it("names the open channels and the regime", () => {
    expect(consentHeadline(consent())).toBe("Email, LinkedIn open · CAN-SPAM.");
  });

  it("says plainly when there is no way to reach them", () => {
    const closed = Object.fromEntries(
      CHANNEL_ORDER.map((c) => [c, channel({ contactable: false, reason: "suppressed" })]),
    ) as Record<ConsentChannel, ChannelConsent>;
    expect(consentHeadline(consent({ channels: closed })))
      .toBe("No contactable channel — CAN-SPAM applies.");
  });

  it("is empty without data", () => {
    expect(consentHeadline(undefined)).toBe("");
  });
});

describe("activeNotes", () => {
  it("de-duplicates the note that applies to several channels", () => {
    expect(activeNotes(consent())).toEqual(["CAN-SPAM is an opt-out regime."]);
  });

  it("ignores the requirements of channels that are closed anyway", () => {
    const data = consent({
      channels: {
        ...consent().channels,
        whatsapp: channel({
          contactable: false, reason: "no recorded opt-in",
          requirements: { unsubscribe_required: true, sender_identity: true,
                          prior_consent: true, tracking_allowed: false,
                          notes: ["Meta policy note"] },
        }),
      },
    });
    expect(activeNotes(data)).not.toContain("Meta policy note");
  });

  it("is empty without data", () => {
    expect(activeNotes(null)).toEqual([]);
  });
});
