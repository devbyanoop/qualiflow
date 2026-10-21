# Config/init scripts baked in at build time, not bind-mounted — same
# remote-Docker-context reasoning as infra/prometheus/Dockerfile.
FROM pgvector/pgvector:pg16
COPY init-app-role.sh /docker-entrypoint-initdb.d/10-init-app-role.sh
