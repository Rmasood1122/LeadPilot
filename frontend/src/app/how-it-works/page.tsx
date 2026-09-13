/**
 * app/how-it-works/page.tsx — public marketing page served at /how-it-works.
 *
 * Static server component: no API calls, no auth. Does NOT use Shell.tsx
 * (authenticated dashboard shell).
 */

import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@/components/Footer";

export const metadata: Metadata = {
  title: "How LeadPilot Works | Clanderharvest",
  description: "LeadPilot builds and runs your outbound pipeline. Here is exactly how it works.",
};

const STEPS = [
  {
    number: "01",
    title: "Research",
    body: "We run a 72-step research pipeline on every prospect. Real LinkedIn profile analysis. Pain signals sourced from actual posts and activity — not guessed. No fabricated data. Every prospect is scored before we write a single word.",
  },
  {
    number: "02",
    title: "Outreach",
    body: "Personalised LinkedIn DMs and emails written in your voice. Sent by human senders — not bots. LinkedIn compliance maintained. A four-step conversation sequence: observe, reflect the pain, introduce your offer, earn the call.",
  },
  {
    number: "03",
    title: "Learning",
    body: "Every reply makes the next campaign smarter. Reply rates tracked. ICP refined. The system compounds over time. You get a Pipeline Health Score updated every 6 hours and a monthly ROI report.",
  },
];

export default function HowItWorksPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <SiteNav />

      <main>
        {/* 1. Hero */}
        <section className="px-6 py-24">
          <div className="mx-auto max-w-4xl">
            <p className="text-sm font-medium uppercase tracking-wider text-blue-500">How it works</p>
            <h1 className="mt-4 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
              Your pipeline. Running without you.
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-relaxed text-gray-300">
              LeadPilot does the prospecting, research, outreach, and follow-up. You show up to
              conversations that are already warm.
            </p>
          </div>
        </section>

        {/* 2. Process */}
        <section className="border-t border-white/10 px-6 py-24">
          <ol className="mx-auto max-w-4xl space-y-16">
            {STEPS.map((step) => (
              <li key={step.number} className="grid gap-4 md:grid-cols-[6rem_1fr]">
                <span className="text-4xl font-bold text-blue-500">{step.number}</span>
                <div>
                  <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">{step.title}</h2>
                  <p className="mt-4 text-lg leading-relaxed text-gray-300">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* 3. What you do */}
        <section className="border-t border-white/10 px-6 py-24">
          <div className="mx-auto max-w-4xl">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Your only job is to show up.</h2>
            <p className="mt-6 text-lg leading-relaxed text-gray-300">
              You review prospect research before outreach launches. You handle the calls we book.
              Everything between — finding, qualifying, messaging, following up — LeadPilot handles.
            </p>
          </div>
        </section>

        {/* 4. CTA */}
        <section className="border-t border-white/10 px-6 py-24">
          <div className="mx-auto flex max-w-4xl flex-wrap items-center gap-6">
            <Link
              href="/contact"
              className="rounded-md bg-blue-600 px-6 py-3 font-semibold text-white hover:bg-blue-700"
            >
              Book a call
            </Link>
            <Link href="/about" className="font-medium text-blue-500 hover:text-blue-400">
              Read about us
            </Link>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}

function SiteNav() {
  return (
    <header className="border-b border-white/10 px-6 py-5">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-8 gap-y-3">
        <Link href="/" className="text-lg font-bold text-white">
          LeadPilot
        </Link>
        <ul className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-gray-300">
          <li><Link href="/how-it-works" aria-current="page" className="text-white">How it Works</Link></li>
          <li><Link href="/about" className="hover:text-white">About</Link></li>
          <li><Link href="/pricing" className="hover:text-white">Pricing</Link></li>
          <li><Link href="/contact" className="hover:text-white">Contact</Link></li>
        </ul>
      </nav>
    </header>
  );
}
