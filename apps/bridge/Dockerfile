# OpenCanal Telegram bridge — getUpdates long-poll + outbox push.
# No-op(exit 0) without TELEGRAM_BOT_TOKEN → compose는 restart: on-failure로 둔다.
FROM node:22-alpine AS base
RUN corepack enable

FROM base AS build
WORKDIR /app
COPY pnpm-workspace.yaml package.json ./
COPY apps/bridge/package.json apps/bridge/
RUN pnpm install --frozen-lockfile=false
COPY . .
RUN pnpm --filter @opencanal/bridge build

FROM base AS run
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/apps/bridge/dist ./apps/bridge/dist
COPY --from=build /app/apps/bridge/package.json ./apps/bridge/
CMD ["node", "apps/bridge/dist/index.js"]
