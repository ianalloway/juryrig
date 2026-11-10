import { ArrowUpRight, Check, ChevronRight, GitBranch, ShieldCheck, Terminal } from 'lucide-react'

const checks = [
  {
    number: '01',
    title: 'Position bias',
    description: 'Does the score change when the same answers swap places?',
    signal: 'A ↔ B',
  },
  {
    number: '02',
    title: 'Verbosity bias',
    description: 'Does more text win, even when it says nothing new?',
    signal: 'short → long',
  },
  {
    number: '03',
    title: 'Prompt injection',
    description: 'Can an answer talk its way into a higher score?',
    signal: 'ignore ↑',
  },
  {
    number: '04',
    title: 'Self-consistency',
    description: 'Does the judge give the same answer twice?',
    signal: 'x → x',
  },
  {
    number: '05',
    title: 'Calibration',
    description: 'Does confidence track what people actually label?',
    signal: 'judge ≈ human',
  },
]

export default function Page() {
  return (
    <>
    <a href="#main-content" className="skip-link">Skip to content</a>
    <main id="main-content" tabIndex={-1} className="min-h-screen overflow-hidden bg-[#10120f] text-[#f3f4e9] selection:bg-[#5EEAD4] selection:text-[#10120f]">
      <div className="mx-auto max-w-[1440px] px-6 md:px-10 lg:px-16">
        <header className="flex items-center justify-between border-b border-[#f3f4e9]/15 py-6">
          <a href="#top" className="group flex items-center gap-3 font-mono text-sm font-bold tracking-tight">
            <span className="grid size-8 place-items-center border border-[#5EEAD4] text-[#5EEAD4] transition-transform group-hover:rotate-45">j</span>
            <span>juryrig</span>
          </a>
          <nav aria-label="Main navigation" className="flex items-center gap-6 font-mono text-xs text-[#f3f4e9]/60">
            <a className="hidden transition-colors hover:text-[#5EEAD4] sm:block" href="#checks">checks</a>
            <a className="hidden transition-colors hover:text-[#5EEAD4] sm:block" href="#why">why it matters</a>
            <a className="inline-flex items-center gap-1 border border-[#f3f4e9]/25 px-3 py-2 text-[#f3f4e9] transition-colors hover:border-[#5EEAD4] hover:text-[#5EEAD4]" href="https://github.com/ianalloway/juryrig" target="_blank" rel="noreferrer">
              <GitBranch className="size-3.5" aria-hidden="true" /> source <ArrowUpRight className="size-3" aria-hidden="true" />
            </a>
          </nav>
        </header>

        <section id="top" className="relative grid gap-14 py-20 md:py-28 lg:grid-cols-[1.05fr_.95fr] lg:items-end lg:gap-20">
          <div className="relative z-10">
            <div className="mb-8 flex items-center gap-3 font-mono text-xs uppercase tracking-[0.22em] text-[#5EEAD4]">
              <span className="size-2 rounded-full bg-[#5EEAD4] shadow-[0_0_16px_#5EEAD4]" />
              open-source toolkit
            </div>
            <h1 className="max-w-4xl text-[clamp(4.4rem,11vw,10.5rem)] font-black leading-[.82] tracking-[-0.08em] text-[#f3f4e9]">
              Test the<br /><span className="text-[#5EEAD4]">judge.</span>
            </h1>
            <p className="mt-5 font-mono text-xs uppercase tracking-[0.16em] text-[#f3f4e9]/65">Source and history live on GitHub</p>
            <p className="mt-10 max-w-xl text-lg leading-relaxed text-[#f3f4e9]/65 md:text-xl">
              <span className="font-mono text-[#f3f4e9]">juryrig</span> is a tiny Python toolkit for testing the AI models you use as graders — before you trust their scores.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <a href="#install" className="inline-flex items-center gap-2 bg-[#5EEAD4] px-5 py-3 font-mono text-sm font-bold text-[#10120f] transition-transform hover:-translate-y-1">
                install juryrig <ChevronRight className="size-4" aria-hidden="true" />
              </a>
              <a href="https://pypi.org/project/juryrig/" target="_blank" rel="noreferrer" className="font-mono text-sm text-[#f3f4e9]/60 underline decoration-[#f3f4e9]/30 underline-offset-4 transition-colors hover:text-[#5EEAD4]">view on PyPI ↗</a>
            </div>
          </div>
          <div className="relative min-h-[280px] border border-[#f3f4e9]/15 bg-[#171a15] p-6 md:p-9">
            <div className="absolute -right-px -top-px size-5 border-r border-t border-[#5EEAD4]" />
            <div className="absolute -bottom-px -left-px size-5 border-b border-l border-[#5EEAD4]" />
            <div className="mb-12 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-[#f3f4e9]/60"><span>judge / audit</span><span>ready</span></div>
            <div className="font-mono text-sm leading-loose text-[#f3f4e9]/70">
              <p><span className="text-[#5EEAD4]">$</span> juryrig cases.json</p>
              <p className="mt-5 text-[#f3f4e9]/60">running adversarial checks...</p>
              <div className="mt-5 space-y-2">
                {['position bias', 'verbosity bias', 'prompt injection', 'self-consistency', 'calibration'].map((item) => <p key={item} className="flex items-center gap-3"><Check className="size-4 text-[#5EEAD4]" aria-hidden="true" /><span>{item}</span><span className="ml-auto text-[#5EEAD4]">audit</span></p>)}
              </div>
              <p className="mt-5 border-t border-[#f3f4e9]/10 pt-4 text-[#5EEAD4]">5 audits run</p>
            </div>
          </div>
        </section>

        <section id="why" className="grid gap-8 border-t border-[#f3f4e9]/15 py-20 md:grid-cols-[.7fr_1.3fr] md:py-28">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-[#5EEAD4]">01 — the premise</p>
          <div><h2 className="max-w-3xl text-4xl font-bold leading-tight tracking-[-0.04em] md:text-6xl">If the grader is biased, every score it hands out is suspect.</h2><p className="mt-8 max-w-2xl text-lg leading-relaxed text-[#f3f4e9]/60">LLM judges are models too. They can anchor on order, reward padding, follow instructions they should ignore, or simply change their mind. juryrig treats the judge like any other model: something to probe before putting it in charge.</p></div>
        </section>

        <section id="checks" className="border-t border-[#f3f4e9]/15 py-20 md:py-28">
          <div className="mb-12 flex flex-col justify-between gap-5 md:flex-row md:items-end"><div><p className="font-mono text-xs uppercase tracking-[0.2em] text-[#5EEAD4]">02 — the test suite</p><h2 className="mt-5 text-4xl font-bold tracking-[-0.04em] md:text-6xl">Five ways a judge can lie.</h2></div><p className="max-w-xs font-mono text-xs leading-relaxed text-[#f3f4e9]/65">Small, focused probes for the failure modes hiding behind a single confident number.</p></div>
          <div className="grid border-l border-t border-[#f3f4e9]/15 sm:grid-cols-2 lg:grid-cols-5">{checks.map((check) => <article key={check.number} className="group flex min-h-[250px] flex-col justify-between border-b border-r border-[#f3f4e9]/15 p-5 transition-colors hover:bg-[#5EEAD4] hover:text-[#10120f] md:p-6"><div className="flex justify-between font-mono text-xs text-[#5EEAD4] group-hover:text-[#10120f]"><span>{check.number}</span><span>{check.signal}</span></div><div><h3 className="text-xl font-bold">{check.title}</h3><p className="mt-3 text-sm leading-relaxed text-[#f3f4e9]/65 group-hover:text-[#10120f]/65">{check.description}</p></div></article>)}</div>
        </section>

        <section id="install" className="grid gap-10 border-t border-[#f3f4e9]/15 py-20 md:grid-cols-[.8fr_1.2fr] md:py-28 md:items-center"><div><p className="font-mono text-xs uppercase tracking-[0.2em] text-[#5EEAD4]">03 — get started</p><h2 className="mt-5 max-w-md text-4xl font-bold tracking-[-0.04em] md:text-6xl">Don&apos;t trust the score. Test it.</h2></div><div className="border border-[#f3f4e9]/15 bg-[#171a15] p-6 md:p-8"><div className="mb-5 flex items-center gap-2 font-mono text-xs text-[#f3f4e9]/60"><Terminal className="size-4" aria-hidden="true" /> terminal</div><code className="block font-mono text-lg text-[#f3f4e9] md:text-2xl"><span className="text-[#5EEAD4]">$</span> pip install juryrig</code><p className="mt-6 flex items-center gap-2 font-mono text-xs text-[#f3f4e9]/65"><ShieldCheck className="size-4 text-[#5EEAD4]" aria-hidden="true" /> zero dependencies · Python toolkit</p></div></section>

        <footer className="flex flex-col gap-5 border-t border-[#f3f4e9]/15 py-8 font-mono text-xs text-[#f3f4e9]/65 sm:flex-row sm:items-center sm:justify-between"><span>juryrig / made by Ian Alloway</span><div className="flex gap-5"><a className="transition-colors hover:text-[#5EEAD4]" href="https://github.com/ianalloway/juryrig" target="_blank" rel="noreferrer">GitHub ↗</a><a className="transition-colors hover:text-[#5EEAD4]" href="https://pypi.org/project/juryrig/" target="_blank" rel="noreferrer">PyPI ↗</a></div></footer>
      </div>
    </main>
    </>
  )
}
