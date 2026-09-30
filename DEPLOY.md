# HalfGPT AWS Deployment

This guide deploys HalfGPT to one Ubuntu EC2 instance. GitHub Actions builds the Docker image, pushes it to ECR, and uses AWS Systems Manager (SSM) Run Command to replace the running container. The deployment job runs on GitHub-hosted infrastructure; no SSH connection or self-hosted runner is required. An attached EBS volume preserves chat data, Chroma's index, and uploaded files across deployments.

## Architecture and prerequisites

- An AWS account and this repository on GitHub
- A Groq API key for chat
- A Tavily API key for web search fallback
- One EC2 instance running Ubuntu 24.04 LTS
- One ECR repository named `halfgpt`
- One EBS data volume mounted at `/mnt/halfgpt`
- One Secrets Manager secret containing the app's environment file

A `t3.medium` instance and a 30 GB `gp3` data volume are reasonable starting points for a small deployment. Actual cost depends on region, uptime, storage, and network usage; check the AWS Pricing Calculator before creating resources.

The workflow deploys to port `8080`. SSM Agent uses outbound HTTPS to connect to AWS, so no inbound SSH rule is needed. For a production domain, put Nginx or an Application Load Balancer with HTTPS in front of the app.

## 1. Create the ECR repository

In AWS Console, open **Elastic Container Registry (ECR)** and create a **private** repository named:

```text
halfgpt
```

Enable image scanning on push if available. Note the AWS region; `ECR_REPO` in GitHub must be the repository name `halfgpt`, not the full registry URL.

## 2. Launch the EC2 instance

1. Launch Ubuntu Server 24.04 LTS, 64-bit x86.
2. Choose an instance size such as `t3.medium` to start.
3. No SSH key pair is required for this deployment; use Systems Manager Session Manager for administration.
4. Create a security group with TCP 8080 from **My IP** for initial testing. For production, expose HTTPS through a reverse proxy or load balancer instead. Do not add an SSH ingress rule.
5. Allocate and associate an Elastic IP if you need a stable public address.
6. Create a separate EBS `gp3` volume in the same Availability Zone as the instance, then attach it to the instance.

Keep AWS credentials out of the repository.

## 3. Format and mount the EBS data volume

Open **Systems Manager → Session Manager**, start a session to the managed instance, and identify the newly attached volume:

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

## 4. Install Docker and verify SSM Agent

```bash
sudo apt-get update
sudo apt-get install -y docker.io awscli jq curl
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
```

Ubuntu EC2 images commonly include SSM Agent. Verify that it is running:

```bash
sudo systemctl status snap.amazon-ssm-agent.amazon-ssm-agent.service
```

If that unit is not present, install and start the agent:

```bash
sudo snap install amazon-ssm-agent --classic
sudo systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent.service
```

Verify Docker and the command-line tools:

```bash
docker run --rm hello-world
aws --version
jq --version
```

## 5. Attach an IAM role to EC2 for SSM, ECR, and Secrets Manager

Create an IAM role with **EC2** as its trusted service, then attach these permissions:

- `AmazonSSMManagedInstanceCore` so SSM Agent can register and receive Run Command requests.
- `AmazonEC2ContainerRegistryReadOnly` so the instance can authenticate to ECR and pull the image.
- A custom policy granting `secretsmanager:GetSecretValue` only on the HalfGPT app secret created in the next step. If that secret uses a customer-managed KMS key, also grant `kms:Decrypt` on that key.

Attach the role to the EC2 instance using **EC2 → Instances → select instance → Actions → Security → Modify IAM role**. In Systems Manager, confirm the instance appears as an online managed node in the same Region.

The instance must have outbound HTTPS access to Systems Manager, ECR, Secrets Manager, and AWS service endpoints. No inbound SSH rule is needed. A public subnet with outbound internet access is sufficient for a small deployment; private subnets need the relevant VPC endpoints or NAT access.

## 6. Create the HalfGPT secret in Secrets Manager

Open **AWS Secrets Manager → Store a new secret → Other type of secret → Plaintext**. Set the secret name to `halfgpt/prod` and store the app environment file as the secret value:

```env
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b
TAVILY_API_KEY=your_tavily_api_key
GOOGLE_SEARCH_API_KEY=
GOOGLE_CSE_ID=
LANGSMITH_TRACING=false
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=halfgpt
```

Enter your real key values directly into Secrets Manager; do not put them in the GitHub workflow or SSM command parameters. Google Search is optional and falls back to Tavily. Google has closed the Custom Search JSON API to new customers and plans to end it on January 1, 2027; see Google's [API notice](https://developers.google.com/custom-search/v1/overview).

Add the instance role permission `secretsmanager:GetSecretValue` for this secret's ARN only. The workflow will ask SSM to retrieve the secret on the instance and write it to `/mnt/halfgpt/app.env` with mode `600`; Docker reads that file when starting the container.

## 7. Give GitHub Actions deployment permissions

The workflow uses GitHub-hosted `ubuntu-latest` runners. Create a dedicated IAM identity for the workflow with:

- ECR push permissions for the `halfgpt` repository. `AmazonEC2ContainerRegistryPowerUser` is a simple starting point; a repository-scoped policy is preferable for production.
- `ssm:SendCommand` on the `AWS-RunShellScript` document and only the target EC2 instance.
- `ssm:GetCommandInvocation` and `ssm:ListCommandInvocations` to wait for deployment and report its result.

For the SSM permissions, create an inline policy like this, replacing the placeholders:

```json
{
	"Version": "2012-10-17",
	"Statement": [
		{
			"Effect": "Allow",
			"Action": "ssm:SendCommand",
			"Resource": [
				"arn:aws:ssm:REGION::document/AWS-RunShellScript",
				"arn:aws:ec2:REGION:ACCOUNT_ID:instance/INSTANCE_ID"
			]
		},
		{
			"Effect": "Allow",
			"Action": [
				"ssm:GetCommandInvocation",
				"ssm:ListCommandInvocations"
			],
			"Resource": "*"
		}
	]
}
```

The workflow currently authenticates using access-key GitHub Secrets. Create an access key for this IAM identity and add it in the next step. Do **not** grant `AmazonEC2FullAccess`; the workflow deploys through SSM and does not need direct EC2 administration. GitHub OIDC can replace static AWS access keys later.

## 8. Configure GitHub repository secrets

Open **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
| --- | --- |
| `AWS_ACCESS_KEY_ID` | Access key ID for the GitHub deployment IAM identity |
| `AWS_SECRET_ACCESS_KEY` | Secret access key for that identity |
| `AWS_DEFAULT_REGION` | Region containing EC2 and ECR, for example `us-east-1` |
| `ECR_REPO` | `halfgpt` |
| `EC2_INSTANCE_ID` | Instance ID, for example `i-0123456789abcdef0` |
| `APP_SECRET_ID` | `halfgpt/prod` or the secret's ARN |

App API keys belong only in Secrets Manager, not GitHub Secrets. Never commit `.env`; the Docker build context excludes local env files and runtime data. Revoke and rotate any API keys previously exposed in chat or terminal output before deployment.

## 9. Deploy

The workflow is triggered by a push to the `main` branch. Push the deployment-ready code:

```bash
git add .
git commit -m "Prepare HalfGPT deployment"
git push origin main
```

Then open **GitHub → Actions** and watch the workflow. It should:

1. Build the Docker image on a GitHub-hosted runner.
2. Push the image to ECR.
3. Use SSM Run Command to deploy to the specified EC2 instance from the GitHub-hosted runner.
4. Verify the EBS mount, fetch app config from Secrets Manager, pull the image, and recreate the container with persistent mounts for `/app/data`, `/app/chroma_db`, and `/app/uploads`.

The first deployment fails intentionally if `/mnt/halfgpt` is not mounted. Fix the EBS mount rather than removing that guard.

## 10. Verify the service

Use **Systems Manager → Session Manager** to open a shell on EC2, then run:

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

## 11. Updates, persistence, and recovery

Push updates to `main`; GitHub Actions builds and deploys them. The container can be deleted and recreated without losing the three mounted data directories, as long as the EBS volume remains attached and mounted at `/mnt/halfgpt`.

Create regular EBS snapshots. Also back up the SQLite databases and the Chroma/uploads directories before major changes. EBS snapshots are not a substitute for application-aware backups of SQLite.

Useful checks:

```bash
sudo docker logs --tail 200 agentic-chatbot
sudo docker inspect agentic-chatbot --format '{{json .Mounts}}'
mountpoint /mnt/halfgpt
```

## Troubleshooting

- **SSM reports the instance is offline:** verify SSM Agent is running, the EC2 IAM role is attached, and outbound HTTPS access to SSM endpoints is allowed.
- **SSM command is denied:** check that the GitHub deployment identity can send `AWS-RunShellScript` to this instance and read command invocation results.
- **Secrets Manager access is denied:** check the EC2 role's scoped `secretsmanager:GetSecretValue` permission and the `APP_SECRET_ID` GitHub secret.
- **EBS guard fails:** run `lsblk -f`, inspect `/etc/fstab`, then `sudo mount -a`; do not format the volume again if it already has data.
- **ECR authentication/pull fails:** confirm `AWS_DEFAULT_REGION`, `ECR_REPO`, IAM ECR permissions, and that the repository is in that region.
- **Container exits:** inspect `docker logs --tail 200 agentic-chatbot` on EC2.
- **Chat reports missing Groq key:** verify `GROQ_API_KEY` and `GROQ_MODEL` are present in the Secrets Manager environment-file value and that the EC2 role can read the secret.
- **Web search fails:** verify `TAVILY_API_KEY`; Google Search settings only work for existing Custom Search API customers.
- **Site does not load:** confirm the container is running, port 8080 is published, and the security group permits inbound traffic from your client. Restrict the rule to your IP for testing.
