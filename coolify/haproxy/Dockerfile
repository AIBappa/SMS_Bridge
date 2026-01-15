FROM haproxy:2.9-alpine

# Switch to root to install packages
USER root

# Install curl for healthcheck
RUN apk add --no-cache curl

# Switch back to haproxy user (if base image uses non-root)
USER haproxy

# Use the default entrypoint and command from base image
