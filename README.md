# 🚀 AutoDevOps FinTech Pipeline v2
**Real-Time Stock Analysis System with E2E Automated CI/CD, Full Observability & Infrastructure Delivery**

![Pipeline Status](https://img.shields.io/badge/build-passing-brightgreen)
![Docker Latest](https://img.shields.io/badge/docker-latest-blue)
![Kubernetes](https://img.shields.io/badge/kubernetes-v1.30-blue)
![Observability](https://img.shields.io/badge/observability-prometheus%20%7C%20grafana-orange)

This project demonstrates a full production-grade **DevOps pipeline** for a Python FinTech application. It covers everything from source code management and continuous integration to containerisation, distributed tracing, alerting, autonomous deployment, and live monitoring.

---

## 🏗️ 1. Architecture Overview

```text
[ Developer ] --> (git push) --> [ GitHub Actions (CI) ]
                                   1. Lint & Pytest
                                   2. Build Docker Image
                                   3. Push to DockerHub
                                         |
                                         v (Automated Rollout / Jenkins)
                                 [ Kubernetes Cluster ]
   [ ELK Stack ] <----logs---- (Deployment, Service, HPA) ----metrics----> [ Prometheus / Grafana ]
   (Monitoring)                         |                                     (Dashboards & Alerts)
                                        v
[ Jaeger (Traces) ] <--------- [ Web Users (OAuth) ] ---------> [ PostgreSQL / Redis ]
```

---

## 🛠️ 2. Technology Stack

| Domain | Technology / Tool Engine |
| :--- | :--- |
| **Application** | Python 3.11, Flask, yfinance, Pytest, Flask-Limiter, Google OAuth 2.0 |
| **Databases** | PostgreSQL 16 (Primary Data), Redis 7 (Caching & Rate Limiting) |
| **Containerisation** | Docker (Multi-stage builds, Distroless/Slim runtimes) |
| **CI/CD Automation** | GitHub Actions (`ci.yml`) & Jenkins (Rollback, OWASP features) |
| **Orchestration** | Kubernetes (Minikube, Deployments, Services, HPA, NetworkPolicies) |
| **Security/Scanning** | Trivy, Kubernetes Secrets, `.env` management, OAuth |
| **Monitoring Logs** | ELK Stack (Elasticsearch 8.x, Logstash, Kibana) |
| **Metrics & Alerts** | Prometheus, Grafana, Alertmanager, Node-Exporter |
| **Distributed Tracing** | OpenTelemetry SDK routing to Jaeger |

---

## 🚀 3. Quick Start (Local Development)

If you want to run the application components locally utilizing the massive 13-container observability stack:

**1. Clone the repository**
```bash
git clone https://github.com/YOUR_USER/spe-project.git
cd spe-project
```

**2. Configure Secrets**
```bash
cp .env.example .env
# Fill in your GOOGLE_CLIENT_ID, SMTP_PASS, and FINNHUB_API_KEY inside the .env file.
```

**3. Start the Full IT & App Stack**
```bash
docker-compose up -d --build
```

**4. Access the Services:**
- **Stock App & UI:** [http://localhost:5000](http://localhost:5000)
- **Grafana (Metrics):** [http://localhost:3000](http://localhost:3000) *(admin / admin)*
- **Prometheus (SQL-like metrics):** [http://localhost:9090](http://localhost:9090)
- **Jaeger (Distributed Traces):** [http://localhost:16686](http://localhost:16686)
- **Kibana (JSON Logs):** [http://localhost:5601](http://localhost:5601)

*(For detailed Database connection strings and UI tracking instructions, please refer to the `OBSERVABILITY_MANUAL.md` walkthrough available within the documentation artifact).*

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

## 📊 5. Core REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Web HTML Dashboard |
| `GET` | `/login` / `/do-login` | Authentication handling & Google OAuth |
| `GET` | `/api/stocks` | Bulk stock prices (AAPL, MSFT, GOOGL, etc.) |
| `POST` | `/api/portfolio` | Add tracked stock to a specific user's portfolio |
| `POST` | `/api/alerts` | Create an email-trigger bound for a stock asset |
| `POST` | `/api/admin/symbols` | [Admin Only] Add new global tracking symbols |
| `POST` | `/api/cache/flush` | [Admin Only] Flush the Redis Cache store |

---

## 🛡️ 6. Security Features & Scale

*   **Authentication:** Full Google OAuth 2.0 integration and Bcrypt hashed local user models.
*   **Rate Limiting:** IP-based request throttling using `Flask-Limiter` + Redis to prevent API abuse.
*   **Database Migrations:** Schema loaded automatically via `init.sql`.
*   **Background Jobs:** Multithreaded email alert processor executing separately from main web threads.
*   **Zero-Downtime Deployments:** Kubernetes HPA scales pods based on traffic metrics dynamically.

---
*Created as fully-functional, interconnected DevOps reference architecture.*
