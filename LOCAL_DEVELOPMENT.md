# LOCAL_DEVELOPMENT.md

A comprehensive guide to running Spin WASM workloads on local Kubernetes without AWS costs.

## The Journey

### What We Set Out To Do

This project originally demonstrated running WebAssembly (Spin) applications across multiple AWS compute primitives: Lambda, ECS/Fargate, and EC2. After ~4 years, we modernized it with these goals:

1. **Update all dependencies** - Spin 0.6.0 → 3.5.1, CDK 2.45.0 → 2.235.0
2. **Add local-first development** - Use cdk8s + local Kubernetes for testing without AWS costs
3. **Use modern Python tooling** - Switch from pip-tools to `uv`
4. **Prepare for arm64** - Future deployment to Graviton, Raspberry Pi, edge devices

### What Actually Happened

We discovered a **lot** of things the hard way:

1. **Spin moved organizations**: `fermyon/spin` → `spinframework/spin`
2. **WASM target changed**: `wasm32-wasi` → `wasm32-wasip1`
3. **cdk8s-plus-30 defaults are strict**: `runAsNonRoot: true`, `readOnlyRootFilesystem: true`
4. **Spin needs writable directories**: `/tmp`, `/home/spin/.cache`, `/app/.spin`
5. **Architecture matters**: Building amd64 images on Apple Silicon → "Exec format error"
6. **Lima/k3s image loading**: `docker save | limactl shell default sudo k3s ctr images import -`
7. **WASM digest verification is strict**: Must match exact sha256 hash

## Quick Start

### Prerequisites

- Docker (or OrbStack on macOS)
- Local Kubernetes cluster (k3s via Lima, kind, k3d, minikube, Docker Desktop)
- Node.js (v20+)
- Python 3.11+ with `uv`

### Install Dependencies

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Python dependencies
uv sync --extra dev

# Install Node.js dependencies
npm install
```

### Build the Local Container Image

The key insight: the production Dockerfile expects an EFS mount with a Spin app. For local testing, we use a separate `Dockerfile.local` that bakes in a sample app.

```bash
cd k8s

# Build for your architecture (arm64 for Apple Silicon, amd64 for Intel/AMD)
docker build -f Dockerfile.local -t spin-wasm-demo:latest .
```

**For Intel/AMD systems:**
```bash
docker build -f Dockerfile.local --build-arg TARGETARCH=amd64 -t spin-wasm-demo:latest .
```

### Load Image into Local Kubernetes

Different clusters have different image loading mechanisms:

**For k3s via Lima (what we use):**
```bash
docker save spin-wasm-demo:latest | limactl shell default sudo k3s ctr images import -
```

**For kind:**
```bash
kind load docker-image spin-wasm-demo:latest
```

**For Docker Desktop Kubernetes:**
Images built locally are already available.

**For minikube:**
```bash
minikube image load spin-wasm-demo:latest
```

### Generate and Apply Kubernetes Manifests

```bash
cd k8s

# Silence the JSII Node.js version warning (optional but reduces noise)
export JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1

# Generate manifests with cdk8s
uv run python app.py

# Apply to your cluster (adjust namespace as needed)
kubectl apply -f dist/
```

### Verify and Test

```bash
# Watch pods come up
kubectl get pods -l app=spin-wasm -w

# Check logs
kubectl logs -l app=spin-wasm --tail=20

# Port-forward to test
kubectl port-forward svc/spin-wasm-service 8080:80

# In another terminal
curl http://localhost:8080/
```

Expected output: A nice HTML page saying "🚀 Hello from Spin on Kubernetes!"

## The Development Loop

When iterating on changes:

```bash
# 1. Make changes to Dockerfile.local, spin.toml, or static files
# 2. Rebuild
docker build -f Dockerfile.local -t spin-wasm-demo:latest .

# 3. Reimport into cluster
docker save spin-wasm-demo:latest | limactl shell default sudo k3s ctr images import -

# 4. Restart deployment to pick up new image
kubectl rollout restart deployment -l app=spin-wasm

# 5. Watch logs
kubectl logs -f -l app=spin-wasm
```

## Troubleshooting

### "cannot execute binary file: Exec format error"

**Cause:** Architecture mismatch. You built for amd64 but running on arm64 (or vice versa).

**Fix:** Rebuild with correct `TARGETARCH`:
```bash
# For Apple Silicon / ARM
docker build -f Dockerfile.local --build-arg TARGETARCH=aarch64 -t spin-wasm-demo:latest .

# For Intel/AMD
docker build -f Dockerfile.local --build-arg TARGETARCH=amd64 -t spin-wasm-demo:latest .
```

### "container has runAsNonRoot and image will run as root"

**Cause:** cdk8s-plus defaults to `runAsNonRoot: true`, but image runs as root.

**Fix:** Add `USER` directive to Dockerfile and create non-root user:
```dockerfile
RUN groupadd -r spin && useradd -r -g spin -u 65532 spin
USER spin
```

### "container has runAsNonRoot and image has non-numeric user"

**Cause:** Kubernetes can't verify non-root status with username, needs UID.

**Fix:** Set `runAsUser` in the security context (we do this in cdk8s app.py):
```python
security_context=kplus.ContainerSecurityContextProps(
    user=65532,
    group=65532,
    read_only_root_filesystem=True,
)
```

### "Read-only file system (os error 30)"

**Cause:** `readOnlyRootFilesystem: true` but Spin needs to write somewhere.

**Fix:** Mount emptyDir volumes for all writable paths Spin needs:
- `/tmp` - Spin log directory
- `/home/spin/.cache` - Spin registry cache
- `/app/.spin` - Spin runtime state (key-value store)

### "invalid content digest; expected sha256:XXX, downloaded sha256:YYY"

**Cause:** The WASM binary's hash has changed (or you had the wrong hash).

**Fix:** Download the file and compute the correct hash:
```bash
curl -L -o component.wasm <URL>
shasum -a 256 component.wasm
```
Then update `spin.toml` with the correct digest.

### "No resources found in monitoring namespace"

**Cause:** Looking in wrong namespace. The pod might be in `default` or another namespace.

**Fix:** Check all namespaces:
```bash
kubectl get pods -A | grep spin
```

### ImagePullBackOff

**Cause:** Kubernetes is trying to pull `spin-wasm-demo:latest` from Docker Hub.

**Fix:** 
1. Set `imagePullPolicy: IfNotPresent` (we do this in cdk8s)
2. Pre-load the image into your cluster before deploying

## File Structure

```
k8s/
├── app.py              # cdk8s Python app that generates K8s manifests
├── cdk8s.yaml          # cdk8s configuration
├── Dockerfile.local    # Self-contained image for local testing
├── spin.toml           # Spin application manifest
├── static/             # Static files served by Spin
│   ├── index.html      # Main page
│   └── healthz         # Health check endpoint
└── dist/               # Generated Kubernetes YAML (git-ignored or committed for GitOps)
```

## Environment Variables Quick Reference

```bash
# Silence Node.js version warnings from JSII
export JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1

# If using Lima, you may need to specify the instance
export LIMA_INSTANCE=default
```

## Version Matrix

| Component | Version | Notes |
|-----------|---------|-------|
| Spin | 3.5.1 | From spinframework (not fermyon) |
| AWS CDK (Python) | 2.235.0 | aws-cdk-lib |
| AWS CDK CLI | 2.1101.0 | npm aws-cdk |
| cdk8s | 2.70.43 | For local K8s |
| cdk8s-plus-30 | 2.4.10 | K8s 1.30 constructs |
| Lambda Web Adapter | 0.9.1 | For Lambda container deployment |
| Python | ≥3.11 | Via uv/pyproject.toml |
| Ubuntu Base | 24.04 | Dockerfile base image |

## Next Steps

Once local development works:

1. **Push image to registry** - GHCR, ECR, Docker Hub for real cluster deployment
2. **Set up GitOps** - Commit `dist/` and let Flux/ArgoCD deploy
3. **Deploy to AWS** - `npx cdk deploy WebAssemblyDemoBackendSandbox`
4. **Test arm64** - Deploy to Graviton-based Lambda/Fargate

## Credits

This documentation was written after spending several hours discovering all these edge cases. Future you (and others) will thank past you for writing this down.
