FROM alpine:3.21
RUN apk add --no-cache pgbouncer
USER 65534:65534
CMD ["pgbouncer", "/etc/event-db/pgbouncer.ini"]
