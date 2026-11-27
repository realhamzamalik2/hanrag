# HanRAG web UI. Build from frontend/:  docker build --build-arg BACKEND_URL=http://api:8000 .
FROM node:26-slim AS deps
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci

FROM node:26-slim
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /web/node_modules ./node_modules
COPY . .
# Next.js bakes the /api proxy target into the build.
ARG BACKEND_URL=http://api:8000
ENV BACKEND_URL=$BACKEND_URL
RUN npm run build && chown -R node /web/.next
USER node
ENV NODE_ENV=production
EXPOSE 3000
CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
