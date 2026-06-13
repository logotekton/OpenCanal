# OpenCanal gateway — Fastify + ws
FROM node:22-alpine AS base
RUN corepack enable

FROM base AS build
WORKDIR /app
COPY pnpm-workspace.yaml package.json ./
COPY apps/gateway/package.json apps/gateway/
COPY packages/db/package.json packages/db/
COPY packages/shared/package.json packages/shared/
RUN pnpm install --frozen-lockfile=false
COPY . .
RUN pnpm --filter @opencanal/db exec prisma generate
RUN pnpm --filter @opencanal/gateway build

FROM base AS run
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/packages ./packages
COPY --from=build /app/apps/gateway/dist ./apps/gateway/dist
COPY --from=build /app/apps/gateway/package.json ./apps/gateway/
EXPOSE 8787
CMD ["node", "apps/gateway/dist/index.js"]
