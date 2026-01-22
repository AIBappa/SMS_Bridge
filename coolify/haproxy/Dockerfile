FROM haproxy:2.9-alpine

# Switch to root to install packages
USER root

# Install curl and netcat for healthcheck and stats socket communication
RUN apk add --no-cache curl netcat-openbsd

# Create directory for stats socket
RUN mkdir -p /var/run/haproxy && \
    chown haproxy:haproxy /var/run/haproxy

# Switch back to haproxy user
USER haproxy

# Expose ports: 8080 (HTTP), 9090 (PostgreSQL), 9091 (Redis), 9999 (stats socket)
EXPOSE 8080 9090 9091 9999

# Use the default entrypoint and command from base image
