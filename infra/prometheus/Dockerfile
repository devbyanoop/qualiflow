# Config baked into the image at build time, not bind-mounted — a runtime
# bind mount would try to resolve a path on the REMOTE Docker daemon's
# filesystem (we run against a remote host over SSH), not this machine's.
# `docker compose build` streams this folder to wherever the daemon is,
# so this works the same locally or remote.
FROM prom/prometheus:latest
COPY prometheus.yml /etc/prometheus/prometheus.yml
