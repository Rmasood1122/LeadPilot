/**
 * app/privacy/page.tsx — Privacy Policy, served at /privacy.
 *
 * Must stay publicly accessible over HTTPS (Play Store requirement for the
 * Android build). Static server component: no API calls, no auth. Does NOT use
 * Shell.tsx (authenticated dashboard shell).
 */

import type { Metadata } from "next";
import Link from "next/link";
import { Footer } from "@/components/Footer";

export const metadata: Metadata = {
  title: "Privacy Policy | Clanderharvest",
  description: "How LeadPilot Enterprise collects, uses, and protects your data.",
  robots: "index, follow",
};

const EMAIL = "ahmadshahid@calendarharvest.com";

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white">
      <SiteNav />

      <main className="px-6 py-24">
        <article className="mx-auto max-w-3xl">
          <h1 className="text-4xl font-bold tracking-tight">Privacy Policy</h1>
          <p className="mt-4 text-sm text-gray-400">Effective date: September 13, 2026</p>

          <Section title="1. Who we are and what this policy covers">
            <p>
              LeadPilot Enterprise is operated by Clanderharvest (&quot;we&quot;, &quot;us&quot;, or
              &quot;our&quot;). We run done-with-you outbound pipeline campaigns for businesses. This policy
              explains how we collect, use, store, and protect personal data when you visit
              calendarharvest.com, use the LeadPilot dashboard, or engage us to run outreach on your behalf.
              It also covers the data we process about the prospects we contact for our clients.
            </p>
          </Section>

          <Section title="2. What data we collect">
            <p>
              When you become a client we collect <strong className="text-white">account data</strong>: your
              name, email address, company name, and the details you share about your business and ideal
              client profile. As you use the dashboard we collect <strong className="text-white">usage
              data</strong>, such as the pages and features you use, along with basic technical information
              like browser type and device.
            </p>
            <p>
              To run campaigns we collect <strong className="text-white">prospect data</strong> on behalf of
              our clients. This includes publicly available LinkedIn profile information, professional email
              addresses, job titles, company details, and public posts and activity used to personalise
              outreach. For this data, our client decides who is targeted and why, and we process it on
              their instructions.
            </p>
            <p>
              <strong className="text-white">Payment data</strong> is processed by Stripe. We receive
              confirmation of payment and limited billing details, but we never see or store your full card
              number. Finally, we keep <strong className="text-white">communication data</strong>: the emails
              and LinkedIn messages sent and received through the system, and any correspondence you have
              with us directly.
            </p>
          </Section>

          <Section title="3. How we use data">
            <p>
              We use personal data to deliver the LeadPilot service: researching prospects, writing and
              sending outreach, managing replies, and reporting results to you. We use campaign results to
              improve performance, for example by learning which messages and audiences produce replies for
              your account. We also use your contact details to communicate with you about your account,
              billing, and material changes to the service.
            </p>
            <p>
              We do not sell your data, or your prospects&apos; data, to third parties. We do not use your
              data to train AI models without your consent. Where the UK or EU GDPR applies, we rely on
              performance of our contract with you, our legitimate interests in running and improving the
              service, and, where required, your consent.
            </p>
          </Section>

          <Section title="4. Data storage and security">
            <p>
              Data is stored on encrypted servers and transmitted over encrypted connections. Our primary
              database is a managed Neon PostgreSQL database hosted on servers in the European Union and the
              United States. Access to personal data is limited to the personnel who need it to deliver the
              service, and passwords are stored only as one-way hashes. No system is perfectly secure, but we
              review our safeguards regularly and will notify affected users and regulators of a data breach
              where the law requires it.
            </p>
          </Section>

          <Section title="5. Third-party services we use">
            <p>
              We share data with a small number of service providers, only as far as each needs it to do its
              job. Stripe processes payments. Anthropic&apos;s Claude models help generate personalised
              message drafts from prospect research. Unipile provides our LinkedIn integration for sending and
              receiving messages. Vercel hosts our website. Google provides analytics that help us understand
              how the site is used. Each provider is bound by its own privacy and security commitments, and a
              current list of the providers that process your data is available on request.
            </p>
            <p>
              Some of these providers are based outside your country, including in the United States. Where
              we transfer data from the UK or EU, we rely on appropriate safeguards such as Standard
              Contractual Clauses.
            </p>
          </Section>

          <Section title="6. Your rights">
            <p>
              You can ask us to access, correct, or delete the personal data we hold about you, and you can
              withdraw any consent you have given at any time. You can also ask for a copy of your data in a
              portable, machine-readable format.
            </p>
            <p>
              If you are in the UK or the European Economic Area, the GDPR gives you additional rights,
              including the right to object to or restrict processing and the right to complain to your data
              protection authority, such as the Information Commissioner&apos;s Office in the UK. If you are a
              California resident, the CCPA gives you the right to know what personal information we collect
              and how we use it, to request its deletion, and not to be discriminated against for exercising
              these rights. As stated above, we do not sell personal information.
            </p>
            <p>
              If you are a prospect we contacted on behalf of a client, you can ask us at any time to stop
              contacting you and to delete your data, and we will honour that request.
            </p>
          </Section>

          <Section title="7. Cookies">
            <p>
              We use essential cookies only: the cookies needed to keep you signed in, keep the site secure,
              and make the dashboard work. We do not use advertising cookies, and we do not allow third
              parties to track you across other websites for advertising purposes.
            </p>
          </Section>

          <Section title="8. Data retention">
            <p>
              We keep account data for as long as your account is active and for as long as needed to meet
              legal, tax, and accounting obligations. When you ask us to delete your data, we will delete it
              within 30 days, except for records we are legally required to keep. Prospect data collected for
              a client campaign is deleted when that client&apos;s engagement ends or on request.
            </p>
          </Section>

          <Section title="9. Contact for privacy requests">
            <p>
              To exercise any of your rights or ask a question about this policy, email{" "}
              <a href={`mailto:${EMAIL}`} className="text-blue-500 hover:text-blue-400">
                {EMAIL}
              </a>
              . We may need to verify your identity before acting on a request, and we will respond within 30
              days.
            </p>
          </Section>

          <Section title="10. Changes to this policy">
            <p>
              We may update this policy as our service or the law changes. If we make a material change, we
              will notify users by email before it takes effect. The effective date at the top of this page
              shows the current version.
            </p>
          </Section>
        </article>
      </main>

      <Footer />
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-12 border-t border-white/10 pt-10">
      <h2 className="text-2xl font-semibold text-white">{title}</h2>
      <div className="mt-4 space-y-4 leading-relaxed text-gray-300">{children}</div>
    </section>
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
          <li><Link href="/contact" className="hover:text-white">Contact</Link></li>
        </ul>
      </nav>
    </header>
  );
}
