FROM node:24-alpine
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
COPY services/agent/zagent/view_schemas /app/services/agent/zagent/view_schemas
COPY evals/fixtures /app/evals/fixtures
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
