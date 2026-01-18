.PHONY: all build import restart logs port-forward clean

# Main workflow for local k3s development
all: build import restart logs

# Build the local Spin image for arm64 (Apple Silicon)
build:
	cd k8s && docker build -f Dockerfile.local --build-arg TARGETARCH=aarch64 -t spin-wasm-demo:latest .

# Import the image into k3s via Lima
import:
	docker save spin-wasm-demo:latest | limactl shell default sudo k3s ctr images import -

# Restart the deployment in the monitoring namespace
restart:
	kubectl rollout restart deployment -l app=spin-wasm -n monitoring

# Tail logs from the Spin pod
logs:
	kubectl logs -l app=spin-wasm -n monitoring --tail=20

# Port-forward to localhost:8080
port-forward:
	kubectl port-forward svc/spin-wasm-service 8080:80 -n monitoring

# Clean up generated images (optional)
clean:
	docker rmi spin-wasm-demo:latest || true

# Full redeploy (build, import, restart, logs)
redeploy: all

# Usage:
#   make build         # Build the image
#   make import        # Import image into k3s
#   make restart       # Restart deployment
#   make logs          # Tail logs
#   make port-forward  # Port-forward to localhost:8080
#   make redeploy      # Full workflow
