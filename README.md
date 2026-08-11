<div align="center">

# ✈️ AI Travel Agent
 
**A full-stack, AI-powered travel recommendation and planning application**  
*Natural language travel queries · AI-driven recommendations · Synthetic dataset generation · Cloud-deployed database*
 
[![Next.js](https://img.shields.io/badge/Next.js_15-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![MariaDB](https://img.shields.io/badge/MariaDB-003545?style=for-the-badge&logo=mariadb&logoColor=white)](https://mariadb.org/)
[![MindsDB](https://img.shields.io/badge/MindsDB-AI_Layer-6B4FBB?style=for-the-badge)](https://mindsdb.com/)
[![AWS EC2](https://img.shields.io/badge/AWS-EC2-FF9900?style=for-the-badge&logo=amazonaws&logoColor=white)](https://aws.amazon.com/ec2/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Jupyter](https://img.shields.io/badge/Jupyter-F37626?style=for-the-badge&logo=jupyter&logoColor=white)](https://jupyter.org/)
 
</div>

---
 
## 📌 Overview
 
**AI Travel Agent** is a full-stack application that combines a **Next.js** frontend, a **FastAPI** Python backend, and an **AI layer powered by MindsDB and the Gemini API** to deliver intelligent travel recommendations. The system stores and queries travel data from a **MariaDB** database deployed on **AWS EC2** via Docker, and uses **Gretel** to generate realistic synthetic travel datasets for training and testing.
 
The project also includes a suite of **Jupyter Notebooks** for data exploration, preprocessing, and ML experimentation — making it a complete end-to-end AI application from data generation through to a production-ready web interface.
 
> This project demonstrates the ability to architect and connect a multi-service AI application — integrating a Python REST API, a React/Next.js frontend, a cloud-hosted relational database, an AI query layer (MindsDB), a generative AI API (Gemini), and a data synthesis pipeline (Gretel) — deployed on real cloud infrastructure (AWS EC2 + Docker).
 
---
 
## 🛠️ Services & Technologies Used
 
### Backend & AI
| Technology | Role |
|---|---|
| **Python** | Primary backend language |
| **FastAPI** | REST API framework serving the backend on port 8080 |
| **Uvicorn** | ASGI server for running FastAPI |
| **MindsDB** | AI layer — natural language queries, ML predictions over SQL databases |
| **Gemini API** | Google's generative AI API for intelligent travel responses |
| **Gretel** | Synthetic travel dataset generation |
| **SQLAlchemy** | ORM for database interaction |
| **Pydantic** | Data validation and schema enforcement |
| **Pandas / NumPy / Dask** | Data manipulation and processing |
| **NLTK** | Natural language processing utilities |
| **airportsdata** | Airport and travel data lookup library |
 
### Frontend
| Technology | Role |
|---|---|
| **Next.js 15** (with Turbopack) | React framework for the web UI |
| **Tailwind CSS v4** | Utility-first styling |
| **SWR** | Data fetching and caching for React |
| **Flowbite** | UI component library |
 
### Infrastructure & Data
| Technology | Role |
|---|---|
| **MariaDB** | Relational database for travel data |
| **Docker / Docker Compose** | Containerised MariaDB deployment |
| **AWS EC2** | Cloud server hosting the MariaDB container |
| **Jupyter Notebooks** | Data exploration, preprocessing, and ML experimentation |
 
---
 
## 📂 Project Structure
 
```
AI-Travel-Agent/
│
├── 📁 backend/               # FastAPI application — routes, models, database logic
├── 📁 config/                # Docker Compose file for MariaDB (compose.yaml)
├── 📁 datasets/              # Travel datasets (raw and Gretel-generated synthetic data)
├── 📁 notebooks/             # Jupyter Notebooks for data exploration and ML experiments
├── 📁 public/                # Static assets for the Next.js frontend
├── 📁 src/app/               # Next.js App Router — pages and UI components
│
├── 📄 connect.sh             # SSH helper script for connecting to the EC2 instance
├── 📄 requirements.txt       # Python dependencies (FastAPI, SQLAlchemy, Pandas, etc.)
├── 📄 package.json           # Node.js dependencies (Next.js, SWR, Tailwind CSS)
├── 📄 next.config.mjs        # Next.js configuration
├── 📄 jsconfig.json          # JavaScript path configuration
└── 📄 ai-travel-agent.code-workspace  # VS Code multi-root workspace file
```
 
---
 
## 🏗️ Architecture Overview
 
```
┌─────────────────────┐        ┌─────────────────────┐
│   Next.js Frontend  │◄──────►│   FastAPI Backend   │
│   (Next.js 15 +     │  HTTP  │   (Python, port     │
│    Tailwind + SWR)  │        │    8080, Uvicorn)   │
└─────────────────────┘        └──────────┬──────────┘
                                           │
                          ┌────────────────┼────────────────┐
                          │                │                │
               ┌──────────▼──────┐  ┌─────▼──────┐  ┌─────▼──────┐
               │    MindsDB      │  │  Gemini API │  │ SQLAlchemy │
               │ (AI/ML queries) │  │  (Google AI)│  │    ORM     │
               └─────────────────┘  └────────────┘  └─────┬──────┘
                                                           │
                                              ┌────────────▼────────────┐
                                              │  MariaDB on AWS EC2     │
                                              │  (Dockerised, port 3306)│
                                              └─────────────────────────┘
```
 
---
 
## ⚠️ Security Notice
 
The file `connect.sh` currently contains a **hardcoded EC2 public IP address** and a reference to a private SSH key path. Since this repository is public, it is strongly recommended to:
 
1. **Remove or replace** the IP address in `connect.sh` with a placeholder (e.g. `<your-ec2-public-ip>`).
2. **Verify** that the referenced private key (`private/ssh-key.pem`) is listed in `.gitignore` and has never been committed to the repository.
3. **Rotate** the EC2 instance's security group or elastic IP if this exposure is a concern.
---
 
## 🚀 Getting Started
 
There are three components to set up: the **MariaDB database on AWS EC2**, the **MindsDB AI layer**, and the **application itself** (backend + frontend). Follow the steps below in order.
 
---
 
## Part 1 — Launch a Docker-Based MariaDB Instance on AWS EC2
 
### Step 1: Create an AWS EC2 Instance
 
Create an EC2 instance (Ubuntu recommended) and configure its security group to allow inbound access on port `3306` for MariaDB connections.
 
### Step 2: Install Docker on the EC2 Instance
 
Open a terminal on your local machine and SSH into the EC2 instance using your private key and the `ubuntu` user:
 
```bash
ssh -i your-private-key.pem ubuntu@<your-ec2-instance-public-ip>
```
 
Escalate to root:
 
```bash
sudo su
```
 
Install Docker:
 
```bash
curl -fsSL https://get.docker.com | sudo sh
```
 
### Step 3: Set Up the MariaDB Root User Password
 
On the EC2 instance, create a `.env` file and add the following line with your own password:
 
```
MARIADB_ROOT_PASSWORD=your-secret-password
```
 
Or generate a secure random password automatically:
 
```bash
echo "MARIADB_ROOT_PASSWORD=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" >> .env
```
 
### Step 4: Run MariaDB with Docker Compose
 
Copy the contents of `config/compose.yaml` to your EC2 instance and start the container:
 
```bash
curl https://raw.githubusercontent.com/AndreasPr/ai-travel-agent/main/config/compose.yaml -o compose.yaml
docker compose -f compose.yaml up -d
```
 
### Step 5: Note the MariaDB Connection String
 
Get the EC2 instance public IP address so you can reuse it as the database connection string anywhere in the application:
 
```
mariadb://root:your-secret-password@<your-ec2-instance-public-ip>:3306
```
 
---
 
## Part 2 — Run MindsDB
 
> You can also refer to the [official MindsDB Docker setup documentation](https://docs.mindsdb.com/setup/self-hosted/docker).
 
### Step 1: Ensure Docker Is Installed
 
Before proceeding, ensure you have installed Docker by following the [official Docker documentation](https://docs.docker.com/install).
 
### Step 2: Install and Start MindsDB
 
Run the following command to create a Docker container with MindsDB:
 
```bash
docker run --name mindsdb_container -p 47334:47334 -p 47335:47335 mindsdb/mindsdb
```
 
### Step 3: Stop and Restart the Container
 
Once the container is created, you can manage it with:
 
```bash
docker stop mindsdb_container     # stop the container
docker start mindsdb_container    # restart a stopped container with all previous changes intact
```
 
> **Tip:** For easier management, it is recommended to use [Docker Desktop](https://www.docker.com/products/docker-desktop/), which provides a user-friendly platform for container management, allowing you to start and stop containers conveniently.
 
### Step 4: Access the MindsDB Editor
 
Once the container is running, access the MindsDB editor in your browser at:
 
```
http://127.0.0.1:47334
```
 
---
 
## Part 3 — Run the Application
 
### Step 1: Create a Python Virtual Environment
 
Open a terminal in the `ai-travel-agent` directory and create a virtual environment:
 
```bash
python -m venv venv
```
 
### Step 2: Activate the Virtual Environment
 
```bash
source venv/bin/activate
```
 
### Step 3: Install Python Dependencies
 
```bash
pip install -r requirements.txt
```
 
### Step 4: Run FastAPI (Backend)
 
```bash
uvicorn backend.main:app --reload --port 8080
```
 
### Step 5: Run Next.js (Frontend)
 
Open a **new terminal**, activate the virtual environment, then start the Next.js development server:
 
```bash
npm run dev
```
 
> **Note:** If you want to run the Jupyter Notebooks, open another terminal, activate the virtual environment, and run:
>
> ```bash
> jupyter notebook
> ```