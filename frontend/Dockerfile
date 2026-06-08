# Kasa frontend image — Next.js app. Build context MUST be the repo root
# (`docker build -f frontend/Dockerfile .`): the frontend depends on the `@kasa/shared` workspace
# package, which is built from source here before `next build`.
#
# NEXT_PUBLIC_* is inlined at BUILD time and read by the browser, so the API URL must be the
# host-reachable address (compose maps the backend to localhost:8000), not the in-network name.
FROM node:20-bookworm-slim

ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN corepack enable
WORKDIR /app

# Install layer: copy every workspace manifest + the lockfile so pnpm can resolve the frozen graph,
# then install only what the frontend (and its @kasa/shared dep) need — not the contracts toolchain.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY contracts/package.json ./contracts/
COPY frontend/package.json ./frontend/
COPY packages/shared/package.json ./packages/shared/
RUN pnpm install --frozen-lockfile --filter "frontend..."

# Sources, then build @kasa/shared → dist (frontend imports its compiled output) and the Next app.
COPY packages/shared ./packages/shared
COPY frontend ./frontend
RUN pnpm --filter @kasa/shared build && pnpm --filter frontend build

WORKDIR /app/frontend
EXPOSE 3000
CMD ["pnpm", "exec", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
