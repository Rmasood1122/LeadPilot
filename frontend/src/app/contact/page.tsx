/**
 * app/contact/page.tsx — public marketing page served at /contact.
 *
 * Static server component. There is intentionally no form: no backend endpoint
 * exists to receive one, so contact is a Calendly link, a mailto link, and
 * LinkedIn. Does NOT use Shell.tsx (authenticated dashboard shell).
 */

import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@/components/Footer";

export const metadata: Metadata = {
  title: "Book a Call | LeadPilot Enterprise",
  description:
    "Talk to Rehan directly. If LeadPilot is a fit, we will tell you honestly. If it is not, we will tell you that too.",
};

const CALENDLY_URL = "https://calendly.com/rmasood112224/30min";
const EMAIL = "ahmadshahid@calendarharvest.com";
const LINKEDIN_URL = "https://www.linkedin.com/company/leadpilot-app";

const WHATSAPP = [
  { label: "+92 342 696 7730 (Pakistan)", href: "https://wa.me/923426967730" },
  { label: "+1 646 756 0056 (US)", href: "https://wa.me/16467560056" },
];

const FOR_YOU = [
  "You run a boutique agency with 3–30 staff in the US, UK, Canada, Australia, New Zealand, Ireland, or Singapore.",
  "You are doing all sales personally and your pipeline stops every time a client project gets heavy.",
  "You have tried cold email or LinkedIn outreach and it has not produced consistent results.",
  "You are open to a done-with-you system rather than a tool you configure yourself.",
  "You want a pipeline that runs without you in it.",
];

const NOT_FOR_YOU = [
  "You have a dedicated SDR team and a working outbound system.",
  "You are based outside our approved geographies.",
  "You need clients in the next 7 days. This is a 4–8 week system, not a quick fix.",
  "You are looking for a self-serve tool you set up once and forget.",
];

const FAQ = [
  {
    q: "How long does it take to see results?",
    a: "Most clients see their first qualified conversations in 4–6 weeks. The pipeline builds as the system learns what works for your ICP.",
  },
  {
    q: "What does LeadPilot cost?",
    a: "Pricing is discussed on the call. It is a premium engagement priced for US, UK, and AU markets.",
  },
  {
    q: "Do I need to be on LinkedIn?",
    a: "Yes. LinkedIn is the primary outreach channel. You need an active profile — not necessarily a large following.",
  },
];

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <SiteNav />

      <main>
        {/* 1. Hero */}
        <section className="px-6 py-24">
          <div className="mx-auto max-w-4xl">
            <h1 className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
              Talk to Rehan directly.
            </h1>
            <p className="mt-6 max-w-3xl text-lg leading-relaxed text-gray-300">
              No sales team. No SDR handoff. If LeadPilot is a fit for your agency, we will tell you
              honestly. If it is not, we will tell you that too.
            </p>
          </div>
        </section>

        {/* 2. Contact options */}
        <section className="border-t border-white/10 px-6 py-24">
          <div className="mx-auto grid max-w-6xl gap-12 md:grid-cols-2">
            <div className="rounded-md border border-white/10 p-8">
              <h2 className="text-2xl font-bold">Book a call</h2>
              <p className="mt-4 leading-relaxed text-gray-300">
                30 minutes. We will look at your current pipeline, understand what you have tried, and tell
                you whether LeadPilot makes sense for your situation.
              </p>
              <a
                href={CALENDLY_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-8 inline-block rounded-md bg-blue-600 px-6 py-3 font-semibold text-white hover:bg-blue-700"
              >
                Book on Calendly
              </a>
            </div>

            <div className="rounded-md border border-white/10 p-8">
              <h2 className="text-2xl font-bold">Get in touch</h2>
              <dl className="mt-6 space-y-6">
                <div>
                  <dt className="text-sm font-medium uppercase tracking-wider text-gray-400">Email</dt>
                  <dd className="mt-1">
                    <a href={`mailto:${EMAIL}`} className="break-all text-lg font-medium text-blue-500 hover:text-blue-400">
                      {EMAIL}
                    </a>
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium uppercase tracking-wider text-gray-400">LinkedIn</dt>
                  <dd className="mt-1">
                    <a
                      href={LINKEDIN_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-lg font-medium text-blue-500 hover:text-blue-400"
                    >
                      LeadPilot on LinkedIn
                    </a>
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium uppercase tracking-wider text-gray-400">WhatsApp</dt>
                  {WHATSAPP.map((w) => (
                    <dd key={w.href} className="mt-1">
                      <a
                        href={w.href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-lg font-medium text-blue-500 hover:text-blue-400"
                      >
                        {w.label}
                      </a>
                    </dd>
                  ))}
                </div>
              </dl>
            </div>
          </div>
        </section>

        {/* 3 + 4. Fit */}
        <section className="border-t border-white/10 px-6 py-24">
          <div className="mx-auto grid max-w-6xl gap-16 md:grid-cols-2">
            <div>
              <h2 className="text-2xl font-bold sm:text-3xl">This call is for you if:</h2>
              <ul className="mt-8 space-y-5">
                {FOR_YOU.map((item) => (
                  <li key={item} className="border-l-2 border-blue-600 pl-5 leading-relaxed text-gray-300">
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h2 className="text-2xl font-bold sm:text-3xl">This call is not for you if:</h2>
              <ul className="mt-8 space-y-5">
                {NOT_FOR_YOU.map((item) => (
                  <li key={item} className="border-l-2 border-gray-600 pl-5 leading-relaxed text-gray-300">
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* 5. FAQ (static) */}
        <section className="border-t border-white/10 px-6 py-24">
          <div className="mx-auto max-w-4xl">
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Common questions</h2>
            <dl className="mt-10 divide-y divide-white/10">
              {FAQ.map((item) => (
                <div key={item.q} className="py-8 first:pt-0">
                  <dt className="text-lg font-semibold">{item.q}</dt>
                  <dd className="mt-3 leading-relaxed text-gray-300">{item.a}</dd>
                </div>
              ))}
            </dl>
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
          <li><Link href="/how-it-works" className="hover:text-white">How it Works</Link></li>
          <li><Link href="/about" className="hover:text-white">About</Link></li>
          <li><Link href="/pricing" className="hover:text-white">Pricing</Link></li>
          <li><Link href="/contact" aria-current="page" className="text-white">Contact</Link></li>
        </ul>
      </nav>
    </header>
  );
}
