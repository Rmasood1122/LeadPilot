/**
 * app/about/page.tsx — public marketing page served at /about.
 *
 * Static server component: no API calls, no auth. It deliberately does NOT use
 * components/shell/Shell.tsx — that is the authenticated dashboard shell and
 * redirects anyone without a session to /login.
 */

import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "About LeadPilot Enterprise | Clanderharvest",
  description:
    "LeadPilot Enterprise was built by a founder who used it to find his own clients. Here is the story.",
};

const STEPS = [
  {
    title: "Research",
    body: "A 72-step research pipeline runs on every prospect before a single message is written. We analyse the real profile, and every pain signal is sourced from actual posts and activity. No invented data.",
  },
  {
    title: "Outreach",
    body: "Human senders run personalised sequences across LinkedIn DM and email. LinkedIn compliance is maintained throughout: no bots, no automation tricks, no banned accounts.",
  },
  {
    title: "Learning",
    body: "Every campaign makes the next one smarter. Reply rates are tracked, your ICP is refined against real responses, and the system compounds over time.",
  },
];

const AUDIENCE = [
  {
    title: "Boutique agency owners",
    body: "Agencies of 3 to 30 staff in the US, UK, Canada, Australia, New Zealand, Ireland, and Singapore, where the founder is still doing all of the selling with no dedicated SDR team.",
  },
  {
    title: "Independent consultants and coaches",
    body: "Practitioners who have lived on referrals for years, know they need outbound, and have no system to run it.",
  },
  {
    title: "Early B2B SaaS founders",
    body: "Pre-Series A founders doing founder-led sales by hand while also building the product.",
  },
  {
    title: "Fractional sales consultants",
    body: "Consultants who want to resell or white-label LeadPilot for the clients they already serve.",
  },
];

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <SiteNav />

      <main>
        {/* 1. Hero */}
        <section className="px-6 py-24">
          <div className="mx-auto max-w-4xl">
            <p className="text-sm font-medium uppercase tracking-wider text-blue-500">About LeadPilot</p>
            <h1 className="mt-4 text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
              Built by a founder who used it to find his own clients.
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-relaxed text-gray-300">
              Rehan Masood is an AI engineer. He could build delivery systems for clients, but every
              time he went deep on delivery, his pipeline went quiet. So he built the system he wished
              existed, and today it is the system that finds LeadPilot&apos;s own clients.
            </p>
          </div>
        </section>

        {/* 2. The problem */}
        <section className="border-t border-white/10 px-6 py-24">
          <div className="mx-auto max-w-4xl">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              The pipeline runs when you push it. It stops when you stop.
            </h2>
            <p className="mt-6 text-lg leading-relaxed text-gray-300">
              Most agency founders are excellent at delivery, and that is exactly what traps them in a
              feast-famine cycle. When a client project gets heavy, prospecting is the first thing to go,
              and two months later there is nothing in the pipeline. Nobody can prospect well and deliver
              well at the same time, however disciplined they are. This is not a discipline problem. It is
              a structural problem, and it needs a structural fix.
            </p>
          </div>
        </section>

        {/* 3. How it works */}
        <section className="border-t border-white/10 px-6 py-24">
          <div className="mx-auto max-w-6xl">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">How LeadPilot works</h2>
            <ol className="mt-12 grid gap-10 md:grid-cols-3">
              {STEPS.map((step, i) => (
                <li key={step.title} className="border-t border-white/10 pt-6">
                  <span className="text-4xl font-bold text-blue-500">{i + 1}</span>
                  <h3 className="mt-4 text-xl font-semibold">{step.title}</h3>
                  <p className="mt-3 leading-relaxed text-gray-300">{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* 4. Who we serve */}
        <section className="border-t border-white/10 px-6 py-24">
          <div className="mx-auto max-w-4xl">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Who we serve</h2>
            <ul className="mt-10 space-y-8">
              {AUDIENCE.map((a) => (
                <li key={a.title} className="border-l-2 border-blue-600 pl-5">
                  <h3 className="text-lg font-semibold">{a.title}</h3>
                  <p className="mt-2 leading-relaxed text-gray-300">{a.body}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* 5. Founder bio */}
        <section className="border-t border-white/10 px-6 py-24">
          <div className="mx-auto max-w-4xl">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Rehan Masood — Founder</h2>
            <p className="mt-6 text-lg leading-relaxed text-gray-300">
              Rehan is an AI engineer based in Faisalabad, Pakistan, working with clients around the
              world. He builds AI-powered automation and agent systems, and has published more than 18
              public repositories on GitHub spanning enterprise AI projects. His strongest conviction is
              simple: a founder who is excellent at delivery should never have to choose between doing the
              work and finding the next client. LeadPilot is his answer to that problem. He uses it himself,
              every day, to find LeadPilot&apos;s own clients.
            </p>
          </div>
        </section>

        {/* 6. CTA strip */}
        <section className="border-t border-white/10 px-6 py-24">
          <div className="mx-auto flex max-w-4xl flex-col items-start gap-8 md:flex-row md:items-center md:justify-between">
            <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
              Ready to remove yourself from your own pipeline?
            </h2>
            <div className="flex flex-wrap items-center gap-6">
              <Link
                href="/contact"
                className="rounded-md bg-blue-600 px-6 py-3 font-semibold text-white hover:bg-blue-700"
              >
                Book a call
              </Link>
              <Link href="/how-it-works" className="font-medium text-blue-500 hover:text-blue-400">
                See how it works
              </Link>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter />
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
          <li><Link href="/how-it-works" className="hover:text-white">How it Works</Link></li>
          <li><Link href="/about" aria-current="page" className="text-white">About</Link></li>
          <li><Link href="/contact" className="hover:text-white">Contact</Link></li>
          <li><Link href="/pricing" className="hover:text-white">Pricing</Link></li>
        </ul>
      </nav>
    </header>
  );
}

function SiteFooter() {
  return (
    <footer className="border-t border-white/10 px-6 py-10">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 text-sm text-gray-400 sm:flex-row sm:items-center sm:justify-between">
        <p>&copy; 2026 Clanderharvest. All rights reserved.</p>
        <ul className="flex flex-wrap gap-6">
          <li><Link href="/privacy" className="hover:text-white">Privacy</Link></li>
          <li><Link href="/terms" className="hover:text-white">Terms</Link></li>
          <li><Link href="/contact" className="hover:text-white">Contact</Link></li>
        </ul>
      </div>
    </footer>
  );
}
