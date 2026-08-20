/**
 * deeplinks.test.ts — ClientHunter Enterprise (M7 Chunk 4)
 *
 * Tests for src/lib/deeplinks.ts — URL parsing, route mapping, and URL builders.
 * No mocks needed — this module is pure functions.
 */

import { describe, it, expect } from 'vitest';
import {
  parseDeepLink,
  routeToPath,
  deepLinks,
  buildCustomSchemeLink,
  buildAppLink,
  DEEP_LINK_SCHEME,
  APP_LINKS_HOST,
} from '@/lib/deeplinks';

// ── parseDeepLink — custom scheme ─────────────────────────────────────────────

describe('parseDeepLink — clienthunter:// scheme', () => {
  it('parses root → dashboard', () => {
    const route = parseDeepLink('clienthunter:///');
    expect(route).toEqual({ path: '/', params: {} });
  });

  it('parses strategy detail', () => {
    const route = parseDeepLink('clienthunter:///strategies/123');
    expect(route).toEqual({ path: '/strategies/[id]', params: { id: '123' } });
  });

  it('parses strategy list', () => {
    const route = parseDeepLink('clienthunter:///strategies');
    expect(route).toEqual({ path: '/strategies', params: {} });
  });

  it('parses campaign detail', () => {
    const route = parseDeepLink('clienthunter:///campaigns/456');
    expect(route).toEqual({ path: '/campaigns/[id]', params: { id: '456' } });
  });

  it('parses campaign list', () => {
    const route = parseDeepLink('clienthunter:///campaigns');
    expect(route).toEqual({ path: '/campaigns', params: {} });
  });

  it('parses lead detail', () => {
    const route = parseDeepLink('clienthunter:///leads/789');
    expect(route).toEqual({ path: '/leads/[id]', params: { id: '789' } });
  });

  it('parses leads list', () => {
    const route = parseDeepLink('clienthunter:///leads');
    expect(route).toEqual({ path: '/leads', params: {} });
  });

  it('parses analytics', () => {
    const route = parseDeepLink('clienthunter:///analytics');
    expect(route).toEqual({ path: '/analytics', params: {} });
  });

  it('parses settings', () => {
    const route = parseDeepLink('clienthunter:///settings');
    expect(route).toEqual({ path: '/settings', params: {} });
  });
});

// ── parseDeepLink — App Links scheme ─────────────────────────────────────────

describe('parseDeepLink — https App Links', () => {
  const host = APP_LINKS_HOST;

  it('parses strategy detail via App Links', () => {
    const route = parseDeepLink(`https://${host}/strategies/99`);
    expect(route).toEqual({ path: '/strategies/[id]', params: { id: '99' } });
  });

  it('parses campaign detail via App Links', () => {
    const route = parseDeepLink(`https://${host}/campaigns/77`);
    expect(route).toEqual({ path: '/campaigns/[id]', params: { id: '77' } });
  });

  it('parses dashboard via App Links', () => {
    const route = parseDeepLink(`https://${host}/`);
    expect(route).toEqual({ path: '/', params: {} });
  });
});

// ── parseDeepLink — edge cases ────────────────────────────────────────────────

describe('parseDeepLink — unknown or malformed URLs', () => {
  it('returns null for an unknown path', () => {
    expect(parseDeepLink('clienthunter:///unknown-page')).toBeNull();
  });

  it('returns null for a completely unrecognised URL', () => {
    expect(parseDeepLink('https://www.google.com/search?q=anything')).toBeNull();
  });

  it('returns null for a malformed string', () => {
    expect(parseDeepLink('not a url at all !!!')).toBeNull();
  });

  it('does not crash on an empty string', () => {
    expect(parseDeepLink('')).toBeNull();
  });

  it('handles numeric IDs correctly', () => {
    const route = parseDeepLink('clienthunter:///strategies/12345678');
    expect(route).toEqual({ path: '/strategies/[id]', params: { id: '12345678' } });
  });
});

// ── routeToPath ───────────────────────────────────────────────────────────────

describe('routeToPath', () => {
  it('converts strategy detail route to Next.js path', () => {
    expect(routeToPath({ path: '/strategies/[id]', params: { id: '42' } })).toBe('/strategies/detail?id=42');
  });

  it('converts campaign detail route', () => {
    expect(routeToPath({ path: '/campaigns/[id]', params: { id: '7' } })).toBe('/campaigns/7');
  });

  it('converts lead detail route', () => {
    expect(routeToPath({ path: '/leads/[id]', params: { id: '99' } })).toBe('/leads/99');
  });

  it('converts root route', () => {
    expect(routeToPath({ path: '/', params: {} })).toBe('/');
  });

  it('round-trip: parse → routeToPath returns a navigable path', () => {
    const url = 'clienthunter:///strategies/55';
    const route = parseDeepLink(url);
    expect(route).not.toBeNull();
    const path = routeToPath(route!);
    expect(path).toBe('/strategies/detail?id=55');
    expect(path.startsWith('/')).toBe(true);
  });
});

// ── URL builders ──────────────────────────────────────────────────────────────

describe('deepLinks URL builders', () => {
  it('strategy() generates correct custom scheme URL', () => {
    const { custom } = deepLinks.strategy(123);
    expect(custom).toBe(`${DEEP_LINK_SCHEME}:///strategies/detail?id=123`);
  });

  it('strategy() generates correct App Links URL', () => {
    const { web } = deepLinks.strategy(123);
    expect(web).toBe(`https://${APP_LINKS_HOST}/strategies/detail?id=123`);
  });

  it('campaign() custom URL', () => {
    expect(deepLinks.campaign(77).custom).toBe(`${DEEP_LINK_SCHEME}:///campaigns/77`);
  });

  it('lead() custom URL', () => {
    expect(deepLinks.lead(99).custom).toBe(`${DEEP_LINK_SCHEME}:///leads/99`);
  });

  it('dashboard() custom URL', () => {
    expect(deepLinks.dashboard().custom).toBe(`${DEEP_LINK_SCHEME}:///`);
  });

  it('buildCustomSchemeLink handles paths with or without leading slash', () => {
    expect(buildCustomSchemeLink('/strategies/1')).toBe(`${DEEP_LINK_SCHEME}:///strategies/1`);
    expect(buildCustomSchemeLink('strategies/1')).toBe(`${DEEP_LINK_SCHEME}:///strategies/1`);
  });

  it('buildAppLink handles paths with or without leading slash', () => {
    expect(buildAppLink('/strategies/1')).toBe(`https://${APP_LINKS_HOST}/strategies/1`);
    expect(buildAppLink('strategies/1')).toBe(`https://${APP_LINKS_HOST}/strategies/1`);
  });
});
