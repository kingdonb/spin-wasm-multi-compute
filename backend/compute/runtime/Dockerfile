# Spin WASM Runtime Container
# Architecture: x86_64 (amd64) - see UPGRADE.md for arm64 instructions
FROM ubuntu:24.04

ARG SPIN_VERSION=3.5.1
ARG TARGETARCH=amd64
ARG LAMBDA_ADAPTER_VERSION=0.9.1

RUN apt-get update && apt install curl jq -y && apt-get clean && apt-get autoclean && apt-get autoremove

SHELL ["/bin/bash", "-c"]

# Install Spin - architecture-aware download
# For arm64: change spin-v${SPIN_VERSION}-linux-aarch64.tar.gz
RUN curl -L -O https://github.com/spinframework/spin/releases/download/v${SPIN_VERSION}/spin-v${SPIN_VERSION}-linux-${TARGETARCH}.tar.gz \
    && tar -zxvf spin-v${SPIN_VERSION}-linux-${TARGETARCH}.tar.gz \
    && mv spin /usr/local/bin/spin \
    && rm spin-v${SPIN_VERSION}-linux-${TARGETARCH}.tar.gz

ENV PORT 3000

# Lambda function requires that the container listens on port 3000
EXPOSE ${PORT}

# Lambda function local runtime (to run the image locally)
# For arm64: change aws-lambda-rie-arm64
RUN curl -L -o /usr/bin/lambda_rie https://github.com/aws/aws-lambda-runtime-interface-emulator/releases/latest/download/aws-lambda-rie-x86_64
RUN chmod +x /usr/bin/lambda_rie

# Lambda adapter - updated to latest version
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.9.1 /lambda-adapter /opt/extensions/lambda-adapter

# Create non-root user for security (required for K8s runAsNonRoot)
RUN groupadd -r spin && useradd -r -g spin -u 65532 spin \
    && mkdir -p /tmp && chown spin:spin /tmp

USER spin

# The container need to be laucnhed with EFS_MOUNT_PATH variable set.
# EFS_MOUNT_PATH should be a path under /mnt. This is required for Lambda function.
# This assumes that files/artifacts are mounted on the folder specified in EFS_MOUNT_PATH.
# The --disable-cache and --log-dir flags are required because of the lambda restrictive environment (only /tmp is R/W)
CMD spin up --listen 0.0.0.0:${PORT} --disable-cache --log-dir /tmp --file ${EFS_MOUNT_PATH}/spin-hello-world/spin.toml
