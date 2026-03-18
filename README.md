# 🚀 AutoDevOps FinTech Pipeline
**Real-Time Stock Analysis System with E2E Automated CI/CD & Infrastructure Delivery**

![Pipeline Status](https://img.shields.io/badge/build-passing-brightgreen)
![Docker Latest](https://img.shields.io/badge/docker-latest-blue)
![Kubernetes](https://img.shields.io/badge/kubernetes-v1.30-blue)
![Trivy Scale](https://img.shields.io/badge/security-trivy_scanned-success)

This project demonstrates a full production-grade **DevOps pipeline** for a Python FinTech application. It covers everything from source code management and continuous integration to containerisation, vulnerability scanning, autonomous deployment, and live monitoring.

---

## 🏗️ 1. Architecture Overview

```text
[ Developer ] --> (git push) --> [ GitHub Repository ]
                                        |
                                        v (Webhook Trigger)
                                 [ Jenkins CI/CD ]
                                   1. Checkout Code
                                   2. Run Pytest (Unit/Int)
                                   3. Trivy FS Scan (Secrets)
                                   4. Build Docker Image
                                   5. Trivy Image Scan (Vulns)
                                        |
     [ DockerHub Registry ] <-----------+ 6. Push Image
                                        |
                                        v 7. Update K8s Manifests
                                 [ Kubernetes Cluster ]
  [ ELK Stack ] <----logs---- (Deployment, Service, HPA)
  (Monitoring)                          |
                                        v
                                  [ Web Users ]
```

---

## 🛠️ 2. Technology Stack

| Domain | Technology / Tool Engine |
| :--- | :--- |
| **Application** | Python 3.11, Flask, yfinance, Pytest, Vanilla JS/HTML Dash |
| **Containerisation** | Docker (Multi-stage builds, Distroless/Slim runtimes) |
| **CI/CD Automation** | Jenkins (Declarative Pipeline `Jenkinsfile`) |
| **Orchestration** | Kubernetes (Minikube, Deployments, Services, HPA) |
| **Config Management** | Ansible (Playbooks, Roles, Inventory) |
| **Security/Scanning** | Trivy (FS & Image), Kubernetes Secrets, `.env` management |
| **Monitoring** | ELK Stack (Elasticsearch 8.x, Logstash, Kibana) |

---

## 🚀 3. Quick Start (Local Development)

If you only want to run the application components locally without Kubernetes:

**1. Clone the repository**
```bash
git clone https://github.com/YOUR_USER/spe-project.git
cd spe-project
```

**2. Start the App & Monitoring Stack via Docker Compose**
```bash
cp .env.example .env     # (Optional: Add actual secrets here)
docker-compose up -d --build
```

**3. Access the Services:**
- **App Dashboard:** [http://localhost:5000](http://localhost:5000)
- **App Health Check:** [http://localhost:5000/health](http://localhost:5000/health)
- **Kibana (Metrics):** [http://localhost:5601](http://localhost:5601)

---

## 🚢 4. Full Infrastructure Deployment

To deploy the entire production stack (Docker, Kubernetes, Application) to raw VMs, use the provided Ansible playbooks:

```bash
cd ansible
# Edit inventory.ini with your target server IPs
sudo ansible-playbook -i inventory.ini site.yml
```
*Note: Make sure your target machines have Ubuntu and your SSH key is authorized.*

---

## 📊 5. REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Web HTML Dashboard |
| `GET` | `/health` | Kubernetes Liveness/Readiness Probe |
| `GET` | `/api/stocks` | Bulk stock prices (AAPL, MSFT, GOOGL, etc.) |
| `GET` | `/api/stock/<symbol>` | Single stock quote (e.g. `/api/stock/TSLA`) |
| `GET` | `/api/stock/<symbol>/history` | 7-day OHLCV trace (append `?days=14`) |

---

## 🛡️ 6. Security Features

*   **Multi-Stage Dockerfile:** Reduces attack surface (150MB output image).
*   **Non-Root User (`appuser` UID 1001):** Prevents container breakout vulnerabilities.
*   **Trivy Integration (`trivy-scan.sh`):** Fails CI build if `HIGH` or `CRITICAL` CVEs exist.
*   **No Baked Secrets:** Environment variables are strictly ignored in `.dockerignore` and `.gitignore`.

---

## 📈 7. Scalability & Monitoring
*   **Kubernetes HPA (Horizontal Pod Autoscaler):** Automatically scales the app between `2` and `10` pods based on CPU/Memory pressure (`k8s/hpa.yaml`).
*   **Zero-Downtime Deployments:** Defined `RollingUpdate` strategy ensures new pods are ready before killing old ones.
*   **Structured JSON Logs:** Flask outputs raw JSON formatting directly to standard out, perfectly mapped for Logstash consumption without grok/regex overhead.

---
*Created as the final submission for the SPE Project Pipeline. All configurations are production-ready concepts.*
