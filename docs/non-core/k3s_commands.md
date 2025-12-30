text
# K3s Useful Commands Reference

This document provides essential commands to verify if k3s is working properly and to check running containers in a k3s Kubernetes cluster.

---

## Check if k3s Service is Running

Check the status of the k3s service using systemd:

sudo systemctl status k3s

text

---

## Verify Cluster Nodes Status

Use kubectl bundled with k3s to list cluster nodes and check their status:

sudo k3s kubectl get nodes

text

---

## Check Logs for Troubleshooting

Stream k3s service logs to diagnose issues:

sudo journalctl -u k3s -f

text

---

## Verify System Configuration for k3s

Check the system configuration compatibility for k3s:

k3s check-config

text

---

## List All Running Pods and Containers

View all pods running across all namespaces (Pods contain containers):

sudo k3s kubectl get pods --all-namespaces

text

---

## Describe a Specific Pod

Get detailed status and container information for a specific pod:

sudo k3s kubectl describe pod <pod-name> -n <namespace>

text

---

## List Running Containers from Container Runtime (containerd)

View all running containers managed by containerd (k3s default runtime):

sudo k3s crictl ps

text

---

## List Container Images Available to containerd

Check container images downloaded and available to containerd:

sudo k3s crictl images

text

---

## (If using Docker runtime) List Docker Containers

If k3s is configured with Docker as runtime, list running Docker containers:

sudo docker ps

text

---

### Notes

- Replace `<pod-name>` and `<namespace>` with actual pod name and namespace in your cluster.
- `k3s kubectl` is a lightweight fix for `kubectl` bundled in k3s to avoid separate Kubernetes client installation.
- `crictl` is a CLI for container runtimes compatible with Kubernetes Container Runtime Interface.

---

This concise reference should help you quickly check k3s status and inspect running containers on your cluster.