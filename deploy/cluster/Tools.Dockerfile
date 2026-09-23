FROM docker:28-cli
RUN apk add --no-cache bash curl python3 py3-yaml git tar
ARG K3D_VERSION=v5.8.3
ARG KUBECTL_VERSION=v1.32.5
ARG TILT_VERSION=0.34.2
RUN set -eu; \
    case "$(uname -m)" in aarch64) arch=arm64; tilt_arch=arm64;; x86_64) arch=amd64; tilt_arch=x86_64;; *) exit 1;; esac; \
    mkdir -p /tmp/_dist; \
    curl -fsSL "https://github.com/k3d-io/k3d/releases/download/${K3D_VERSION}/k3d-linux-${arch}" -o "/tmp/_dist/k3d-linux-${arch}"; \
    curl -fsSL "https://github.com/k3d-io/k3d/releases/download/${K3D_VERSION}/checksums.txt" -o /tmp/k3d-checksums; \
    cd /tmp; grep " _dist/k3d-linux-${arch}$" k3d-checksums | sha256sum -c -; \
    install -m 755 "_dist/k3d-linux-${arch}" /usr/local/bin/k3d; \
    curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${arch}/kubectl" -o kubectl; \
    curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${arch}/kubectl.sha256" -o kubectl.sha256; \
    printf '%s  kubectl\n' "$(cat kubectl.sha256)" | sha256sum -c -; \
    install -m 755 kubectl /usr/local/bin/kubectl; \
    archive="tilt.${TILT_VERSION}.linux-alpine.${tilt_arch}.tar.gz"; \
    curl -fsSL "https://github.com/tilt-dev/tilt/releases/download/v${TILT_VERSION}/${archive}" -o "$archive"; \
    curl -fsSL "https://github.com/tilt-dev/tilt/releases/download/v${TILT_VERSION}/checksums.txt" -o tilt-checksums; \
    grep " ${archive}$" tilt-checksums | sha256sum -c -; \
    tar -xzf "$archive" tilt; install -m 755 tilt /usr/local/bin/tilt
WORKDIR /workspace
ENTRYPOINT []