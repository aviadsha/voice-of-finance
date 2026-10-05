# Voice of Finance — Frontend

Next.js (App Router, TypeScript, Tailwind CSS) web app for Voice of Finance. See the [root README](../README.md) for
the full architecture and setup guide.

```bash
cp .env.example .env.local   # set API_URL, NEXTAUTH_URL, NEXTAUTH_SECRET
npm install
npm run dev                  # http://localhost:3000
npm run lint && npm run typecheck && npm run build
```

- Authentication: NextAuth.js credentials provider backed by the FastAPI `/auth/login` endpoint. The backend JWT lives
  only inside the encrypted session cookie; browser requests go through the same-origin `/api/backend/*` proxy.
- Data fetching: React Server Components call the backend directly (`src/lib/api.ts`).
