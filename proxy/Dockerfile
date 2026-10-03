FROM node:22-alpine
WORKDIR /app
COPY package.json ./
COPY src ./src
COPY scripts ./scripts
ENV NODE_ENV=production \
    PORT=8787 \
    KEYS_FILE=/data/keys.json \
    USAGE_FILE=/data/usage.json
VOLUME ["/data"]
EXPOSE 8787
USER node
CMD ["node", "src/server.js"]
