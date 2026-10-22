#!/usr/bin/env bash
set -euo pipefail

# Provisions the "qualiflow" realm and the "qualiflow-api" confidential
# client (service-accounts / client-credentials grant enabled) that
# the control plane's JWT auth (apps/api) assumes. Idempotent -- safe
# to re-run; skips creation if the realm/client already exist, but
# always syncs the client secret to match QUALIFLOW_API_CLIENT_SECRET
# so a fresh .env value takes effect.
#
# Requires: `docker compose up -d` (keycloak service running) and this
# script run with .env's variables in the environment, e.g.:
#   set -a; source .env; set +a; ./infra/keycloak/provision-realm.sh

: "${QUALIFLOW_KEYCLOAK_ADMIN_USER:?set in .env}"
: "${QUALIFLOW_KEYCLOAK_ADMIN_PASSWORD:?set in .env}"
: "${QUALIFLOW_API_CLIENT_SECRET:?set in .env}"

# On Git Bash / MSYS (Windows), a leading "/opt/..." argument gets
# silently rewritten into a Windows path before reaching the docker
# CLI -- this disables that path-conversion. Harmless on real POSIX
# shells (the variable is simply unused there).
export MSYS_NO_PATHCONV=1

KCADM="/opt/keycloak/bin/kcadm.sh"

run_kcadm() {
  docker compose exec -T keycloak "$KCADM" "$@"
}

run_kcadm config credentials --server http://localhost:8080 --realm master \
  --user "$QUALIFLOW_KEYCLOAK_ADMIN_USER" --password "$QUALIFLOW_KEYCLOAK_ADMIN_PASSWORD" >/dev/null

if run_kcadm get realms/qualiflow >/dev/null 2>&1; then
  echo "Realm qualiflow already exists, skipping creation"
else
  run_kcadm create realms -s realm=qualiflow -s enabled=true >/dev/null
  echo "Created realm: qualiflow"
fi

CLIENT_UUID=$(run_kcadm get clients -r qualiflow -q clientId=qualiflow-api --fields id --format csv --noquotes | tr -d '\r' | tail -n1)

if [ -z "$CLIENT_UUID" ]; then
  CLIENT_UUID=$(run_kcadm create clients -r qualiflow \
    -s clientId=qualiflow-api \
    -s enabled=true \
    -s publicClient=false \
    -s serviceAccountsEnabled=true \
    -s standardFlowEnabled=false \
    -s directAccessGrantsEnabled=false \
    -i)
  echo "Created client: qualiflow-api ($CLIENT_UUID)"
else
  echo "Client qualiflow-api already exists ($CLIENT_UUID), skipping creation"
fi

run_kcadm update "clients/$CLIENT_UUID" -r qualiflow -s "secret=$QUALIFLOW_API_CLIENT_SECRET" >/dev/null
echo "Synced client secret from QUALIFLOW_API_CLIENT_SECRET"

echo "Done. Issuer: http://localhost:8080/realms/qualiflow"
