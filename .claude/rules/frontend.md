---
paths:
  - "frontend/src/**/*.ts"
  - "frontend/src/**/*.tsx"
---

# Frontend Conventions

- React 19 + Vite + TypeScript
- Tests co-located as `*.test.ts(x)` next to source, using vitest
- Run all: `cd frontend && npm test` | watch: `cd frontend && npm run test:watch`
- Environment: jsdom, globals enabled (`describe`, `it`, `expect`, `vi` available without import)
- Rendering: `@testing-library/react` — `render()`, `screen.getByText()`
- User interaction: `@testing-library/user-event`
- Mocking: `vi.mock("../../api/client", () => ({ ... }))` at file top
- Assertions: `@testing-library/jest-dom` matchers (`.toBeInTheDocument()`, etc.)
- Test data factories: `src/test-utils.ts` — `makeEvent()` and `makeCRRun()` helpers
- Types in `frontend/src/api/types.ts` must stay in sync with backend response shapes
