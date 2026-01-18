#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""
cdk8s app for local Kubernetes deployment of Spin WASM workloads.

This allows testing the Spin container locally without AWS costs, using
a local Kubernetes cluster (kind, k3d, minikube, Docker Desktop, etc.).

Usage:
    cd k8s
    uv run python app.py
    kubectl apply -f dist/

For Flux GitOps:
    uv run python app.py
    git add dist/
    git commit -m "Update k8s manifests"
    git push  # Flux will pick up the changes
"""

from constructs import Construct
from cdk8s import App, Chart, Duration, Size
import cdk8s_plus_30 as kplus


class SpinWasmChart(Chart):
    """
    Kubernetes chart for deploying Spin WASM workloads locally.
    
    This chart creates:
    - A Deployment running the Spin container
    - A Service to expose the Spin HTTP endpoint
    """

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        image: str = "spin-wasm-demo:latest",
        replicas: int = 1,
        port: int = 3000,
    ):
        super().__init__(scope, id)

        # Create the Deployment with pod labels for selection
        deployment = kplus.Deployment(
            self,
            "SpinDeployment",
            replicas=replicas,
            metadata={"labels": {"app": "spin-wasm", "component": "backend"}},
            pod_metadata={"labels": {"app": "spin-wasm", "component": "backend"}},
        )

        # Add the Spin container
        # Use IfNotPresent for local development (image pre-loaded into cluster)
        deployment.add_container(
            image=image,
            image_pull_policy=kplus.ImagePullPolicy.IF_NOT_PRESENT,
            name="spin",
            port_number=port,
            security_context=kplus.ContainerSecurityContextProps(
                user=65532,
                group=65532,
                read_only_root_filesystem=True,
            ),
            liveness=kplus.Probe.from_http_get(
                path="/healthz",
                port=port,
            ),
            readiness=kplus.Probe.from_http_get(
                path="/healthz",
                port=port,
            ),
            resources=kplus.ContainerResources(
                cpu=kplus.CpuResources(
                    limit=kplus.Cpu.millis(500),
                    request=kplus.Cpu.millis(100),
                ),
                memory=kplus.MemoryResources(
                    limit=Size.mebibytes(256),
                    request=Size.mebibytes(64),
                ),
            ),
        )

        # Add emptyDir volume for /tmp (needed for readOnlyRootFilesystem)
        tmp_volume = kplus.Volume.from_empty_dir(
            self,
            "TmpVolume",
            name="tmp",
            medium=kplus.EmptyDirMedium.DEFAULT,
        )
        deployment.add_volume(tmp_volume)
        # Mount /tmp in the container
        for container in deployment.containers:
            container.mount("/tmp", tmp_volume)

        # Add emptyDir volume for Spin cache
        cache_volume = kplus.Volume.from_empty_dir(
            self,
            "CacheVolume",
            name="spin-cache",
            medium=kplus.EmptyDirMedium.DEFAULT,
        )
        deployment.add_volume(cache_volume)
        for container in deployment.containers:
            container.mount("/home/spin/.cache", cache_volume)

        # Add emptyDir volume for .spin (Spin runtime state)
        spin_dir_volume = kplus.Volume.from_empty_dir(
            self,
            "SpinDirVolume",
            name="spin-dir",
            medium=kplus.EmptyDirMedium.DEFAULT,
        )
        deployment.add_volume(spin_dir_volume)
        for container in deployment.containers:
            container.mount("/app/.spin", spin_dir_volume)

        # Expose via service
        deployment.expose_via_service(
            name="spin-wasm-service",
            service_type=kplus.ServiceType.CLUSTER_IP,
            ports=[
                kplus.ServicePort(
                    port=80,
                    target_port=port,
                ),
            ],
        )


class LocalDevChart(SpinWasmChart):
    """
    Chart configured for local development with Docker Desktop / kind / k3d.
    """

    def __init__(self, scope: Construct, id: str):
        super().__init__(
            scope,
            id,
            image="spin-wasm-demo:latest",
            replicas=1,
            port=3000,
        )


# Create the cdk8s app
app = App()

# Local development chart
LocalDevChart(app, "spin-wasm-local")

# Synthesize to dist/ directory
app.synth()

print("""
✅ Kubernetes manifests generated in dist/

To deploy locally:
    kubectl apply -f dist/

To build and load the container image (for kind):
    docker build -t spin-wasm-demo:latest backend/compute/runtime/
    kind load docker-image spin-wasm-demo:latest

To port-forward and test:
    kubectl port-forward svc/spin-wasm-service 8080:80
    curl http://localhost:8080/

For Flux GitOps, commit the dist/ directory to your repo.
""")
