# Deployment Guide - DigitalOcean Droplet

Follow these steps to deploy your Gold Rate application to a DigitalOcean Droplet with automatic SSL.

## Prerequisites
1.  **DigitalOcean Account**: [Sign up here](https://www.digitalocean.com/).
2.  **Domain Name**: You need a domain (e.g., `goldratelive.com`) pointing to your Droplet's IP.

## Step 1: Create a Droplet
1.  Log in to DigitalOcean and click **Create -> Droplets**.
2.  **Region**: Choose the one closest to your users (e.g., Bangalore or London).
3.  **OS**: Ubuntu 24.04 (LTS) x64.
4.  **Droplet Type**: Basic -> Regular -> **$6/month** (1GB RAM, 1 CPU) is sufficient for starting.
5.  **Authentication**: Select **SSH Key** (recommended) or Password.
6.  Click **Create Droplet**.

## Step 2: Configure DNS
1.  Copy your new Droplet's **IP Address**.
2.  Go to your Domain Registrar (GoDaddy, Namecheap, etc.).
3.  Add an **A Record**:
    *   **Host**: `@` (or `www`)
    *   **Value**: Your Droplet's IP Address.
    *   **TTL**: Lowest possible (e.g., 1 min or 1 hour).

## Step 3: Server Setup
Open your terminal and SSH into the server:
```bash
ssh root@<YOUR_DROPLET_IP>
```

Run the following commands to install Docker:
```bash
# Update packages
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin -y
```

## Step 4: Deploy Application
1.  **Clone the Repository** (or copy files):
    ```bash
    git clone <YOUR_REPO_URL> app
    cd app
    ```
    *If you don't have a git repo yet, you can copy the files from your local machine:*
    ```bash
    # On your LOCAL machine
    scp -r . root@<YOUR_DROPLET_IP>:~/app
    ```

2.  **Configure Environment**:
    Create a `.env` file:
    ```bash
    nano .env
    ```
    Paste the following (update with your values):
    ```env
    # Database
    POSTGRES_USER=user
    POSTGRES_PASSWORD=secure_password
    POSTGRES_DB=goldrate
    DATABASE_URL=postgresql://user:secure_password@db:5432/goldrate

    # Domain for SSL (IMPORTANT)
    DOMAIN_NAME=yourdomain.com
    ACME_EMAIL=your-email@example.com
    ```
    Press `Ctrl+X`, then `Y`, then `Enter` to save.

3.  **Start the Application**:
    ```bash
    docker compose up -d --build
    ```

## Step 5: Verify
Visit `https://yourdomain.com`.
-   Caddy will automatically obtain an SSL certificate.
-   Your app should be live and secure! 🔒

## Troubleshooting
-   **Check Logs**: `docker compose logs -f`
-   **Restart**: `docker compose restart`
-   **Update**: `git pull && docker compose up -d --build`
