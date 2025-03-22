# AI Travel Agent 


### Services & Software used

- MariaDB

- MindsDB

- Gretel

- Gemini API

- AWS EC2

- MariaDB Docker Image

- Docker Engine

- Python

- Node.js

- FastAPI

- Next.js

- Pandas

- Jupyter Notebooks

- Pydantic

- Flowbite





## Steps to Launch a Docker-based MariaDB Instance on AWS EC2

### Step 1: Create an AWS EC2 Instance.

Set up the security groups to allow port `3306` access for MariaDB.

### Step 2: Install Docker Compose
Open a terminal on your local maching and SSH into EC2 Instance with your private key and the  `ubuntu`  user:
```
ssh -i your-private-key.pem ubuntu@<your-ec2-instance-public-ip>
```

Escalate to Root:
```
sudo su
```

Install Docker:
```
curl -fsSL https://get.docker.com | sudo sh
```

### Step 3: Setup MariaDB Root User Password

On the EC2 instance create the  `.env`  add the following line with your own password:
```
MARIADB_ROOT_PASSWORD=your-secret-password
```
Such as:
```
echo "MARIADB_ROOT_PASSWORD=$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')" >> .env
```

### Step 4: Run MariaDB with Docker Compose

Copy the contents of  `config/compose.yaml` file to your EC2 instance to run MariaDB with:

```
curl https://raw.githubusercontent.com/AndreasPr/ai-travel-agent/main/config/compose.yaml -o compose.yaml
docker compose -f compose.yaml up -d
```

### Step 5: Connection String to MariaDB

Get the EC2 instance public IP address so as to re-use it anywhere with the following database connection string:
```
mariadb://root:your-secret-password@<your-ec2-instance-public-ip>:3306
```

# Instructions for running the program
Step 1: Open a terminal in the directory `ai-travel-agent` and create a virtual environment:
```
python -m venv venv  
```
Step 2: Activate the virtual environment:
```
source venv/bin/activate 
```
Step 3: Install dependencies:
```
pip install -r requirements.txt
```

Step 4: Run FastAPI (backend):
```
uvicorn backend.main:app --reload --port 8080
```
Step 5: Open another terminal, activate the virtual environment, and run Next.js (frontend):
```
npm run dev
```

Note: If you want to run the notebooks, open another terminal, activate the virtual environment, and run:
```
jupyter notebook
```

# Instructions for running MindsDB:
You could direct to the official link for running MindsDB in the Docker container:
https://docs.mindsdb.com/setup/self-hosted/docker

Step 1: Before proceeding, ensure you have installed Docker, following the [official Docker documentation](https://docs.docker.com/install).


Step 2: Install MindsDB by run the following command to create a Docker container with MindsDB:
```
docker run --name mindsdb_container -p 47334:47334 -p 47335:47335 mindsdb/mindsdb
```

Step 3: Once the container is created, you could run:

-   `docker stop mindsdb_container`  to stop the container. 
-   `docker start mindsdb_container`  to restart a stopped container with all its previous changes intact.

Note: For easier management, it is recommended to use [Docker Desktop](https://www.docker.com/products/docker-desktop/), which enhances your development experience by offering a powerful, user-friendly platform for container management. In this way, you would be capable of starting/stopping your containers in a convenient way.

Step 4: Now you can access the MindsDB editor by going to  `127.0.0.1:47334`  in your browser.



