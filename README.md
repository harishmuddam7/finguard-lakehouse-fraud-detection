# FinGuard: Operational Fraud Detection & Lakehouse Triage Platform

FinGuard is an end-to-end lakehouse platform built on **Databricks**, **Unity Catalog**, **Delta Lake**, and **Streamlit**. It models a financial fraud pipeline by pairing streaming ingestion and medallion layer data transformations with distributed machine learning and a human-in-the-loop audit console.

The primary design goal of FinGuard is operational realism: raw card transactions land continuously, advance through structured medallion quality boundaries, receive real-time unsupervised anomaly scores, and surface immediately for forensic analyst review with change audit logging.

## High-Level Architecture

<img width="3430" height="1216" alt="architecture_diagram" src="https://github.com/user-attachments/assets/ee6d99cb-a107-45c6-8ede-799703b9a42b" />

### Medallion Workflow

* **1. Bronze Layer (`bronze_transactions`)**
  * Ingests JSON transaction payloads directly from cloud object storage via Databricks Auto Loader (`cloudFiles`).
  * Enforces schema constraints on arrival while capturing ingestion metadata (file path, arrival timestamp) in an append-only Delta table.

* **2. Silver Layer (`silver_transactions`)**
  * Performs data hygiene: cleans null identifiers, aligns timezone standards, and casts data types.
  * Computes temporal aggregations and velocity metrics, such as rolling customer transaction frequency and rapid cross-city hops indicating impossible travel speed.
  * Joins transactions with baseline risk indicators and merchant profile attributes.

* **3. Gold Layer (`gold_fraud_alerts`)**
  * Applies an unsupervised Isolation Forest anomaly detection model trained on historical normal spend distributions.
  * Translates raw decision function values into normalized anomaly scores and assigns risk tiers (`CRITICAL`, `ELEVATED`, `STANDARD`).
  * Generates explainable risk flags (e.g., sudden volume spikes, unfamiliar merchant categories) to provide context for downstream investigation.

* **4. Human-in-the-Loop Operational Loop (`gold_analyst_dispositions`)**
  * Interfaces directly with a lightweight Streamlit application through the Databricks SQL Connector.
  * Fraud investigators can review prioritized incidents, inspect transaction features, and log dispositions (`Confirmed Fraud`, `False Positive`, `Requires Escalation`).
  * Writes verdicts to Delta Lake with Change Data Feed (CDF) enabled to maintain an immutable audit trail.

## Repository Structure

```text
finguard-lakehouse-fraud-detection/
├── assets/
│   ├── app_analyst_triage.png
│   ├── app_analytics_overview.png
│   ├── app_origin_cities.png
│   ├── architecture_diagram.png
│   ├── lakehouse_bi_dashboard.png
│   ├── pipeline_dag_orchestration.png
│   └── pipeline_timeline_execution.png
├── notebooks/
│   ├── 01_env_and_reference_data.ipynb
│   ├── 02_model_baseline_training.ipynb
│   ├── 03_bronze_silver_pipeline.ipynb
│   └── 04_ai_scoring_and_triage.ipynb
├── streamlit/
│   └── app.py
├── .streamlit/
│   └── secrets.toml.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Local Setup & Deployment

### Prerequisites
* Python 3.10 or higher installed locally
* Access to a Databricks Workspace with an active SQL Warehouse or cluster
* Unity Catalog enabled with read/write access on target schema

### 1. Clone the Project
```bash
git clone https://github.com/harishmuddam7/finguard-lakehouse-fraud-detection.git
cd finguard-lakehouse-fraud-detection
```

### 2. Configure Local Secrets
Create your private configuration file from the template:
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Open `.streamlit/secrets.toml` and supply your connection details:
```toml
DATABRICKS_SERVER_HOSTNAME = "your-workspace-url.cloud.databricks.com"
DATABRICKS_HTTP_PATH = "/sql/1.0/warehouses/xxxxxxxxxxxx"
DATABRICKS_TOKEN = "dapi_your_personal_access_token"
```

> **Security Note:** `.streamlit/secrets.toml` is ignored by git. Never commit live tokens or credentials.

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Streamlit Triage Console
```bash
streamlit run streamlit/app.py
```

---

## Security & Governance Standards

* **Unity Catalog Governance:** All tabular data resides in managed or external Delta tables governed by Unity Catalog access policies.
* **Separation of Concerns:** Cloud execution logic runs within Databricks compute resources; presentation and triage logic run independently via the client application using parameterized queries.
* **Immutable Change Audits:** Disposition entries append directly to Delta tables tracked by Change Data Feed (CDF), providing an auditable trail for financial compliance reviews.
