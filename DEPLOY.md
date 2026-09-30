# HalfGPT AWS Deployment

This guide deploys HalfGPT to one Ubuntu EC2 instance. GitHub Actions builds the Docker image, pushes it to ECR, and asks a self-hosted runner on EC2 to replace the running container. An attached EBS volume preserves chat data, Chroma's index, and uploaded files across deployments.

## Architecture and prerequisites

- An AWS account and this repository on GitHub
- A Groq API key for chat
- A Tavily API key for web search fallback
- One EC2 instance running Ubuntu 24.04 LTS
- One ECR repository named `halfgpt`
- One EBS data volume mounted at `/mnt/halfgpt`

A `t3.medium` instance and a 30 GB `gp3` data volume are reasonable starting points for a small deployment. Actual cost depends on region, uptime, storage, and network usage; check the AWS Pricing Calculator before creating resources.

The workflow deploys to port `8080`. For a production domain, put Nginx or an Application Load Balancer with HTTPS in front of it. Do not leave SSH open to the entire internet.

## 1. Create the ECR repository

In AWS Console, open **Elastic Container Registry (ECR)** and create a **private** repository named:

```text
halfgpt
```

Enable image scanning on push if available. Note the AWS region; `ECR_REPO` in GitHub must be the repository name `halfgpt`, not the full registry URL.

## 2. Launch the EC2 instance

1. Launch Ubuntu Server 24.04 LTS, 64-bit x86.
2. Choose an instance size such as `t3.medium` to start.
3. Create or select an SSH key pair and download it securely.
4. Create a security group with:
   - SSH, TCP 22, source set to **My IP** only.
   - TCP 8080 for initial testing. Restrict it to your IP if possible; for production, expose HTTPS through a reverse proxy or load balancer instead.
5. Allocate and associate an Elastic IP if you need a stable public address.
6. Create a separate EBS `gp3` volume in the same Availability Zone as the instance, then attach it to the instance.

Keep the SSH private key and AWS credentials out of the repository.

## 3. Format and mount the EBS data volume

Connect to the instance and identify the newly attached volume:

```bash
lsblk -f
```

On Nitro-based instances the device may appear as `/dev/nvme1n1`; another instance may show a different name. Confirm the device is the new, empty EBS volume and **not** the root disk before formatting it. Formatting erases the selected device, and should only be done once for a new empty volume.

Replace `/dev/nvme1n1` below with the confirmed device name:

```bash
sudo mkfs -t ext4 /dev/nvme1n1
sudo mkdir -p /mnt/halfgpt
sudo mount /dev/nvme1n1 /mnt/halfgpt
sudo blkid /dev/nvme1n1
```

Copy the UUID printed by `blkid`, then add it to `/etc/fstab` so it mounts after reboot:

```bash
sudo nano /etc/fstab
```

Add this line, replacing the placeholder with the actual UUID:

```text
UUID=REPLACE_WITH_EBS_UUID /mnt/halfgpt ext4 defaults,nofail 0 2
```

Verify the entry and create the persistent directories:

```bash
sudo mount -a
mountpoint -q /mnt/halfgpt && echo "EBS mounted"
sudo mkdir -p /mnt/halfgpt/data /mnt/halfgpt/chroma_db /mnt/halfgpt/uploads
sudo chown -R ubuntu:ubuntu /mnt/halfgpt
```

The GitHub Actions workflow checks that `/mnt/halfgpt` is mounted before replacing the container. This prevents deployment from silently writing data to the instance's root disk if EBS is unavailable.

## 4. Install Docker

```bash
sudo apt-get update
sudo apt-get install -y docker.io git curl
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
```

Log out and reconnect so the `ubuntu` user's Docker group membership takes effect, then verify:

```bash
docker run --rm hello-world
```

## 5. Give GitHub Actions access to ECR

The existing workflow uses AWS access-key secrets with `aws-actions/configure-aws-credentials`. Create a dedicated IAM identity for this workflow and grant only the ECR permissions it needs. The AWS managed `AmazonEC2ContainerRegistryPowerUser` policy is a simple starting point; a repository-scoped custom policy is better for production. The workflow does not need broad EC2 administrator access because it deploys through the runner on the instance.

Create an access key for the IAM identity and add it to GitHub Secrets in the next step. Never commit the key or put it in the Docker image. GitHub OIDC is a stronger long-term alternative to static access keys, but requires changing the workflow's AWS credential configuration.

## 6. Install the GitHub self-hosted runner on EC2

The deployment job in `.github/workflows/cicd.yaml` uses `runs-on: self-hosted`, so a runner must be online on the EC2 instance.

1. In GitHub, open the repository's **Settings → Actions → Runners → New self-hosted runner**.
2. Select Linux x64 and follow GitHub's current download/configuration commands on EC2 as the `ubuntu` user. GitHub generates a temporary registration token; do not put it in the repository.
3. Install and start the runner service using the commands shown by GitHub. Common commands from the runner directory are:

```bash
sudo ./svc.sh install ubuntu
sudo ./svc.sh start
sudo ./svc.sh status
```

4. Confirm the runner appears **Idle** in the repository's Runners page.

The runner account needs Docker access and permission to read/write `/mnt/halfgpt`. Restart the runner service after changing group membership. Since this is a self-hosted runner with access to production data, do not run untrusted pull-request workflows on it.

## 7. Configure GitHub repository secrets

Open **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
| --- | --- |
| `AWS_ACCESS_KEY_ID` | Access key ID for the dedicated ECR IAM identity |
| `AWS_SECRET_ACCESS_KEY` | Secret access key for that identity |
| `AWS_DEFAULT_REGION` | Region containing the ECR repository, for example `us-east-1` |
| `ECR_REPO` | `halfgpt` |
| `GROQ_API_KEY` | Groq API key for chat |
| `GROQ_MODEL` | `openai/gpt-oss-20b` |
| `TAVILY_API_KEY` | Tavily key used as web-search fallback |

These are optional:

| Secret | When needed |
| --- | --- |
| `GOOGLE_SEARCH_API_KEY` | Only if you already have access to Google's Custom Search JSON API |
| `GOOGLE_CSE_ID` | Search engine ID paired with the Google Search API key |
| `LANGSMITH_TRACING` | Set to `true` only when enabling tracing; otherwise `false` |
| `LANGSMITH_ENDPOINT` | Usually `https://api.smith.langchain.com` when tracing is enabled |
| `LANGSMITH_API_KEY` | LangSmith key when tracing is enabled |
| `LANGSMITH_PROJECT` | Optional LangSmith project name |

Google has closed the Custom Search JSON API to new customers and plans to end it on January 1, 2027. Without existing Google API access, HalfGPT falls back to Tavily. See Google's [Custom Search JSON API notice](https://developers.google.com/custom-search/v1/overview).

Do not commit `.env`. The Docker build context excludes local `.env` files and local runtime data.
If you have not already done so, revoke and rotate API keys that were previously exposed in chat or terminal output before adding replacement keys to GitHub Secrets.

## 8. Deploy

The workflow is triggered by a push to the `main` branch. Push the deployment-ready code:

```bash
git add .
git commit -m "Prepare HalfGPT deployment"
git push origin main
```

Then open **GitHub → Actions** and watch the workflow. It should:

1. Build the Docker image on a GitHub-hosted runner.
2. Push the image to ECR.
3. Run the deployment job on the EC2 self-hosted runner.
4. Verify the EBS mount, pull the image, and recreate the container with persistent mounts for `/app/data`, `/app/chroma_db`, and `/app/uploads`.

The first deployment fails intentionally if `/mnt/halfgpt` is not mounted. Fix the EBS mount rather than removing that guard.

## 9. Verify the service

On EC2:

```bash
docker ps --filter name=agentic-chatbot
docker logs --tail 100 agentic-chatbot
curl -f http://localhost:8080/
mountpoint -q /mnt/halfgpt && echo "Persistent storage is mounted"
```

Open the instance's public address in a browser:

```text
http://EC2_PUBLIC_IP:8080/
```

If you associated an Elastic IP, use that address. For a public production site, configure a domain and HTTPS rather than leaving port 8080 broadly exposed.

## 10. Updates, persistence, and recovery

Push updates to `main`; GitHub Actions builds and deploys them. The container can be deleted and recreated without losing the three mounted data directories, as long as the EBS volume remains attached and mounted at `/mnt/halfgpt`.

Create regular EBS snapshots. Also back up the SQLite databases and the Chroma/uploads directories before major changes. EBS snapshots are not a substitute for application-aware backups of SQLite.

Useful checks:

```bash
# Runner/service logs are available from the runner's service setup.
sudo docker logs --tail 200 agentic-chatbot
sudo docker inspect agentic-chatbot --format '{{json .Mounts}}'
mountpoint /mnt/halfgpt
```

## Troubleshooting

- **Workflow waits for a runner:** make sure the EC2 runner service is online and shows **Idle** in GitHub.
- **EBS guard fails:** run `lsblk -f`, inspect `/etc/fstab`, then `sudo mount -a`; do not format the volume again if it already has data.
- **ECR authentication/pull fails:** confirm `AWS_DEFAULT_REGION`, `ECR_REPO`, IAM ECR permissions, and that the repository is in that region.
- **Container exits:** inspect `docker logs --tail 200 agentic-chatbot` on EC2.
- **Chat reports missing Groq key:** verify `GROQ_API_KEY` and `GROQ_MODEL` are configured as GitHub Actions secrets.
- **Web search fails:** verify `TAVILY_API_KEY`; Google Search settings only work for existing Custom Search API customers.
- **Site does not load:** confirm the container is running, port 8080 is published, and the security group permits inbound traffic from your client. Restrict the rule to your IP for testing.
