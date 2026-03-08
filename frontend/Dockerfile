# Stage 1: Dependencies
FROM node:20-alpine AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --frozen-lockfile

# Stage 2: Build
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./

# Contract samples needed by mock imports at build time.
# Imports in src/lib/api/mock.ts resolve to /contract inside the container.
COPY contract /contract

ARG NEXT_PUBLIC_API_MODE=real
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000

ENV NEXT_PUBLIC_API_MODE=$NEXT_PUBLIC_API_MODE
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# Stage 3: Production
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./app/public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./app/.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "app/server.js"]
