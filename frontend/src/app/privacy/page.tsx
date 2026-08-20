/**
 * app/privacy/page.tsx — ClientHunter Enterprise
 *
 * Privacy policy page served at /privacy.
 * Required by Play Store — must be publicly accessible via HTTPS.
 *
 * This is a static page (no API calls, no auth required).
 * Content mirrors PRIVACY_POLICY.md — update both together.
 */

import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Privacy Policy — LeadPilot',
  description: 'How LeadPilot collects, uses, and protects your data.',
  robots: 'index, follow',
};

export default function PrivacyPage() {
  return (
    <main
      className="mx-auto max-w-3xl px-6 py-12"
      style={{ color: 'var(--color-text)', background: 'var(--color-background)' }}
    >
      {/* Header */}
      <h1 className="mb-2 text-3xl font-bold" style={{ color: 'var(--color-text)' }}>
        Privacy Policy
      </h1>
      <p className="mb-10 text-sm" style={{ color: 'var(--color-text-muted)' }}>
        Last updated: August 2026
      </p>

      {/* Legal note */}
      <div
        className="mb-8 rounded-lg border-l-4 p-4 text-sm"
        style={{
          borderColor: 'var(--color-warning)',
          background: 'var(--color-surface)',
          color: 'var(--color-text-muted)',
        }}
      >
        This document was reviewed by the LeadPilot team and reflects accurate information
        about data collection and processing. Have a qualified lawyer review it before scaling
        to EU users or handling personal data at volume.
      </div>

      <Section title="1. Who we are">
        <p>
          LeadPilot is a software service for B2B client acquisition automation.
          {/* TODO: replace with your legal entity name and address */}
          Operated by <strong>[Your name / company name]</strong>, [Your country].
          Contact: <a href="mailto:privacy@clienthunter.app" style={{ color: 'var(--color-primary)' }}>
            privacy@clienthunter.app {/* TODO: replace with real address */}
          </a>
        </p>
      </Section>

      <Section title="2. What data we collect">
        <h3 className="mb-1 mt-4 font-semibold">Data you provide directly</h3>
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>Account:</strong> Email address and password (stored as one-way hash).</li>
          <li><strong>Product description:</strong> What you sell or offer.</li>
          <li><strong>Past client details:</strong> Information you voluntarily enter about previous clients.</li>
        </ul>

        <h3 className="mb-1 mt-4 font-semibold">Data sourced on your behalf</h3>
        <p>
          When you run a campaign, the system sources business contact information (name, company,
          email, job title) from third-party data providers (see Section 5). This data is used
          solely for the outreach campaigns you configure.
        </p>

        <h3 className="mb-1 mt-4 font-semibold">Device and usage data</h3>
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>Device token:</strong> Firebase Cloud Messaging token for push notifications.</li>
          <li><strong>App interactions:</strong> Feature usage, used to improve the product.</li>
        </ul>
      </Section>

      <Section title="3. How we use your data">
        <ul className="list-disc pl-5 space-y-1">
          <li>To operate the LeadPilot service on your behalf</li>
          <li>To send push notifications about campaign events</li>
          <li>To improve the product and AI strategy accuracy</li>
          <li>To comply with legal obligations</li>
        </ul>
        <p className="mt-3">
          We do <strong>not</strong> sell your data, use it for advertising, or share it with
          parties outside Section 5.
        </p>
      </Section>

      <Section title="4. Legal basis (GDPR)">
        <p>
          If you are in the EEA, UK, or Switzerland: our legal basis is contract performance
          (Art. 6(1)(b)), legitimate interests (Art. 6(1)(f)), and consent for push
          notifications (Art. 6(1)(a) — withdraw at any time in device settings).
        </p>
      </Section>

      <Section title="5. Third-party services">
        <p className="mb-3">We use the following services to operate LeadPilot:</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                <th className="py-2 pr-4 text-left font-semibold">Service</th>
                <th className="py-2 pr-4 text-left font-semibold">Purpose</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['Anthropic', 'AI research, strategy generation, message personalisation'],
                ['Apollo.io', 'Lead sourcing and contact enrichment'],
                ['Hunter.io', 'Email finding and verification'],
                ['Google (Gmail API)', 'Sending outreach emails on your behalf'],
                ['Google (Firebase)', 'Push notifications'],
                ['Meta (WhatsApp Business)', 'WhatsApp outreach on your behalf'],
                ['Calendly', 'Meeting booking'],
              ].map(([service, purpose]) => (
                <tr key={service} style={{ borderBottom: '1px solid var(--color-border)' }}>
                  <td className="py-2 pr-4 font-medium">{service}</td>
                  <td className="py-2" style={{ color: 'var(--color-text-muted)' }}>{purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="6. Your rights">
        <ul className="list-disc pl-5 space-y-1">
          <li><strong>Access and portability:</strong> Request a copy of your data.</li>
          <li><strong>Erasure:</strong> Delete your account in Settings → Account → Delete, or email us.</li>
          <li><strong>Rectification:</strong> Correct inaccurate data via the app.</li>
          <li><strong>Push notifications:</strong> Disable in your device Settings → Apps → LeadPilot at any time.</li>
        </ul>
        <p className="mt-3">
          Email{' '}
          <a href="mailto:privacy@clienthunter.app" style={{ color: 'var(--color-primary)' }}>
            privacy@clienthunter.app {/* TODO: replace with real address */}
          </a>{' '}
          to exercise any right. We respond within 30 days.
        </p>
      </Section>

      <Section title="7. Security">
        <p>
          All data is transmitted over HTTPS. Passwords are stored as bcrypt hashes.
          Firebase tokens are used only to deliver notifications to your device.
        </p>
      </Section>

      <Section title="8. Children">
        <p>
          LeadPilot is a professional B2B tool for adults (18+).
          We do not knowingly collect data from minors.
        </p>
      </Section>

      <Section title="9. Changes">
        <p>
          Material changes will be announced via email or in-app notification.
          The &quot;Last updated&quot; date at the top reflects the current version.
        </p>
      </Section>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h2
        className="mb-3 text-xl font-semibold"
        style={{ color: 'var(--color-text)' }}
      >
        {title}
      </h2>
      <div
        className="space-y-2 leading-relaxed"
        style={{ color: 'var(--color-text-muted)' }}
      >
        {children}
      </div>
    </section>
  );
}
