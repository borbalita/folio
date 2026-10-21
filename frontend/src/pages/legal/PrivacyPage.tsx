import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { LegalLinks } from '@/components/LegalLinks'
import { ThemeToggle } from '@/components/ThemeToggle'
import { CONTACT_EMAIL } from '@/lib/legal'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-heading text-base font-semibold">{title}</h2>
      {children}
    </section>
  )
}

function Mail() {
  return (
    <a href={`mailto:${CONTACT_EMAIL}`} className="underline underline-offset-2">
      {CONTACT_EMAIL}
    </a>
  )
}

export function PrivacyPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between px-4 py-3 sm:px-6">
        <Link to="/" className="text-sm font-medium hover:underline">
          Borbfolio
        </Link>
        <ThemeToggle />
      </header>
      <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 pt-4 pb-16 text-sm leading-relaxed sm:px-6">
        <div className="flex flex-col gap-1">
          <h1 className="font-heading text-2xl font-semibold tracking-tight">Privacy</h1>
          <p className="text-muted-foreground">Last updated: October 2026</p>
        </div>

        <Section title="1. Controller">
          <p>
            Borbála Tasnádi, Buttmannstr. 2, 13357 Berlin, Germany. Email: <Mail />
          </p>
        </Section>

        <Section title="2. What Borbfolio is">
          <p>
            Borbfolio is a personal project. It holds only my own data: my own emails and my
            own bank and PayPal transactions. It is not offered to the public, and there is
            no sign-up.
          </p>
          <p>
            For demonstrations, a separate demo account shows invented data only: fictional
            vendors, invoices, transactions and newsletters. No real person's data is in it.
          </p>
          <p>
            Emails in my mailbox naturally contain the names and addresses of the people and
            companies who wrote to me. They are stored only so that I can search my own mail
            and keep track of my own invoices, and are never used for anything else.
          </p>
        </Section>

        <Section title="3. Visiting this site">
          <p>
            The app runs on Railway. When you open it, the hosting provider processes
            technically necessary data, in particular your IP address, the time of access,
            the page requested and browser information, to deliver the site and keep it
            secure. The legal basis is Art. 6(1)(f) GDPR (my legitimate interest in running
            the site securely). This data may be processed outside the EU, including in the
            USA.
          </p>
        </Section>

        <Section title="4. Sign-in and browser storage">
          <p>
            Sign-in uses Supabase Auth. When you sign in, your email address and password go
            to Supabase, and a session is stored in your browser's local storage so
            you stay signed in. Your choice of light or dark theme is also stored there.
            These entries are strictly necessary for the functions you use (§ 25(2) no. 2
            TDDDG). There are no tracking cookies and no analytics.
          </p>
        </Section>

        <Section title="5. My data and the services that process it">
          <p>Inside the app, the following services process my own data to provide its features:</p>
          <ul className="flex list-disc flex-col gap-1.5 pl-5">
            <li>
              <span className="font-medium">Supabase</span>: the database that stores my
              emails, invoices, transactions and chats, and the sign-in service.
            </li>
            <li>
              <span className="font-medium">Yahoo</span>: my mailbox, read over IMAP.
            </li>
            <li>
              <span className="font-medium">Enable Banking</span>: read-only access to my
              N26, ING and PayPal accounts, with my consent at the bank, for at most 180 days
              and revocable at any time. The app never sees bank logins.
            </li>
            <li>
              <span className="font-medium">OpenAI</span>: answers questions in the chats,
              extracts payment data from invoices and news items from newsletters, and
              creates search embeddings.
            </li>
            <li>
              <span className="font-medium">TypeSafe</span>: sorts incoming emails into
              labels and ranks search results.
            </li>
            <li>
              <span className="font-medium">Telegram</span>: sends me notifications about new
              invoices (payee, amount, due date) and big AI news headlines.
            </li>
            <li>
              <span className="font-medium">Langfuse</span> (EU): technical traces of the
              assistants, without content: model names, tools used, token counts, timings and
              errors only.
            </li>
          </ul>
          <p>
            Some of these providers are based in the USA, so data may be processed there.
            The data is never sold, never shared for any other purpose, and never used for
            advertising.
          </p>
        </Section>

        <Section title="6. Your rights">
          <p>
            Under the GDPR you have the right to access, rectification, erasure, restriction
            of processing, data portability and objection. If an email you sent me is stored
            here and you want it removed, write to <Mail />. You can also complain to a data
            protection supervisory authority, for example the Berlin Commissioner for Data
            Protection and Freedom of Information.
          </p>
        </Section>

        <Section title="7. Contact">
          <p>
            For any question about privacy: <Mail />
          </p>
        </Section>

        <LegalLinks className="pt-4" />
      </main>
    </div>
  )
}
