#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"
action="${1:-up}"
image=zagent-devtools:plan9
name=zagent-plan9-tilt
mkdir -p .cluster
chmod 700 .cluster
export KUBECONFIG="$root/.cluster/kubeconfig"
options=(--network host --workdir "$root" -v "$root:$root" -v /var/run/docker.sock:/var/run/docker.sock
    -e "KUBECONFIG=$KUBECONFIG" -e "LOCAL_UID=$(id -u)" -e "LOCAL_GID=$(id -g)"
    -e "HOME=$root/.cluster/home" -e "ZAGENT_CLUSTER_MODE=${ZAGENT_CLUSTER_MODE:-replay}")
if [[ "${ZAGENT_CLUSTER_MODE:-replay}" == live ]]; then
    key="${ZAGENT_OPENROUTER_KEY_FILE:-$HOME/.config/zagent/openrouter.key}"
    options+=(-v "$key:/run/secrets/openrouter.key:ro" -e CLUSTER_PROVIDER_KEY_FILE=/run/secrets/openrouter.key)
fi

case "$action" in
    up)
        docker build --quiet -f deploy/cluster/Tools.Dockerfile -t "$image" deploy/cluster
        if docker container inspect "$name" >/dev/null 2>&1; then
            docker stop "$name" >/dev/null
            docker rm "$name" >/dev/null
        fi
        docker run --rm "${options[@]}" "$image" python3 deploy/cluster/control.py bootstrap
        docker run --detach --name "$name" "${options[@]}" "$image" tilt up --file "$root/Tiltfile" --host 127.0.0.1 --port 10359 --stream
        docker exec "$name" curl --fail --silent --show-error --retry 15 --retry-connrefused --retry-delay 1 --output /dev/null http://127.0.0.1:10359/
        docker exec "$name" tilt wait --port 10359 --for=create 'uiresource/(Tiltfile)' --timeout=30s
        docker exec "$name" tilt wait --port 10359 --for=condition=Ready 'uiresource/(Tiltfile)' --timeout=60s
        docker exec "$name" tilt wait --port 10359 --for=condition=Ready uiresources --all --timeout=10m
        printf '\nCluster app: http://localhost:5185\nAPI: http://localhost:8109\nTilt: http://localhost:10359\nTempo: http://localhost:3284\nGrafana: http://localhost:3285\n'
        ;;
    stop)
        if docker container inspect "$name" >/dev/null 2>&1; then docker stop "$name"; fi
        docker run --rm "${options[@]}" "$image" k3d cluster stop zagent-plan9
        ;;
    kubectl)
        shift
        docker run --rm -i "${options[@]}" "$image" kubectl "$@"
        ;;
    test)
        docker exec "$name" tilt wait --port 10359 --for=condition=Ready uiresources --all --timeout=3m
        docker run --rm "${options[@]}" "$image" python3 deploy/cluster/verify.py
        ;;
    evals)
        shift
        docker exec "$name" tilt wait --port 10359 --for=condition=Ready uiresources --all --timeout=3m
        docker run --rm "${options[@]}" "$image" python3 deploy/cluster/evidence.py "$@"
        ;;
    mutation)
        docker run --rm "${options[@]}" -e ZAGENT_MUTATION -e ZAGENT_TEST_MODE -e ZAGENT_LLM_MODE \
            -e DATABASE_URL -e ZAGENT_TEST_DATABASE_URL "$image" python3 deploy/cluster/mutation.py
        ;;
    *)
        printf 'Usage: bash deploy/cluster/cluster.sh up|stop|kubectl ...\n' >&2
        exit 2
        ;;
esac