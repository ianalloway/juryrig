# juryrig site

The public landing page for [juryrig](https://github.com/ianalloway/juryrig),
Ian Alloway's Python toolkit for auditing LLM judges.

[Live site](https://exposur-ochre.vercel.app) · [Python package](https://pypi.org/project/juryrig/) · [Toolkit source](https://github.com/ianalloway/juryrig)

## Local development

Use Node.js 22 or newer and pnpm (the package manager version is recorded in
`package.json`). Install the committed dependency versions before starting:

```sh
pnpm install --frozen-lockfile
pnpm dev
```

Open <http://localhost:3000>.

## Check a change

```sh
pnpm typecheck
pnpm build
pnpm start
```

The production build checks TypeScript errors. Before publishing a visual change,
check desktop and narrow phone widths, keyboard navigation, and reduced motion.
The page uses a dark background with a readable mint accent and visible focus rings.

## Where to edit

| File | Purpose |
| --- | --- |
| `app/page.tsx` | Page copy, audit cards, and install links |
| `app/globals.css` | Shared styles, focus treatment, and reduced motion |
| `app/layout.tsx` | Page metadata, icons, and production analytics |
| `public/` | Static icons and images |

This is a Next.js App Router site styled with Tailwind CSS. Vercel Analytics is
included only in production. No environment variables are required to build the
landing page.

## Deployment

The repository is connected to Vercel through its existing v0 project. Merging to
`main` triggers the configured deployment. Review the preview and checks before
merging. Changes to the Python toolkit belong in the separate
[juryrig repository](https://github.com/ianalloway/juryrig).
