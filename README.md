# HalfGPT

HalfGPT is an open-source **agentic AI chatbot** built with **Python, FastAPI, LangGraph, LangChain, Groq, Tavily, ChromaDB, and SQLite**. Chroma uses local embeddings for document search.

It supports real-time streaming chat, document uploads, retrieval-augmented generation (RAG), web search, conversation memory, and a simple web UI.

---

## Features

* Chat with Groq-hosted OpenAI GPT-OSS 20B
* Stream responses in real time
* Upload documents such as PDF, DOCX, TXT, MD, PY, and CSV
* Use uploaded files as context through RAG
* Search the web with Google when configured, with Tavily fallback
* Store and recall conversation history
* Simple FastAPI-based web interface
* Docker-ready deployment
* AWS CI/CD deployment through GitHub Actions, ECR, EC2, and Systems Manager

---

## Project Overview

This project combines:

* **FastAPI** for the backend server and API endpoints
* **Jinja2** for rendering the frontend UI
* **LangGraph** for agent orchestration
* **LangChain** for tools, messages, and RAG workflow
* **Groq** for chat completions
* **ChromaDB's local embedding model** for document search
* **Google Search**, with **Tavily** fallback
* **ChromaDB** for vector search over uploaded documents
* **SQLite** for conversation and persistence
* **Docker** for containerized deployment

---

## Prerequisites

Make sure you have the following installed:

* Python 3.11
* pip or conda
* Git
* Groq API key for chat
* Tavily API key for web search

Optional for deployment:

* Docker
* AWS account
* Amazon ECR repository
* EC2 instance
* AWS Systems Manager (SSM) Run Command

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/entbappy/BappyGPT.git HalfGPT
```

### 2. Navigate to the project directory

```bash
cd HalfGPT
```

### 3. Create a virtual environment

Using conda:

```bash
conda create -n halfgpt python=3.11 -y
```

### 4. Activate the virtual environment

```bash
conda activate halfgpt
```

### 5. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Environment Variables

Create a `.env` file in the project root directory.

```env
# Required for chat
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b

# Optional: Google Custom Search JSON API (existing customers only)
GOOGLE_SEARCH_API_KEY=your_google_search_api_key
GOOGLE_CSE_ID=your_programmable_search_engine_id

# Fallback web search
TAVILY_API_KEY=your_tavily_api_key

LANGSMITH_TRACING=false
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=halfgpt
```

Current-information queries use Google Search when configured and fall back to Tavily otherwise. Google has closed the Custom Search JSON API to new customers and plans to end the service on January 1, 2027; see the [Google API notice](https://developers.google.com/custom-search/v1/overview).

If you do not want to use LangSmith tracing, keep:

```env
LANGSMITH_TRACING=false
```

---

## Run Locally

Start the FastAPI app:

```bash
python app.py
```

The app will be available at:

```text
http://127.0.0.1:8080
```

---

## Project Structure

```text
HalfGPT/
│
├── app.py                  # FastAPI app and streaming chat endpoints
├── agent.py                # LangGraph agent setup and tool orchestration
├── database.py             # Conversation and persistence logic
├── rag.py                  # Document ingestion and RAG logic
├── tools.py                # Agent tools such as web search, memory, and RAG
├── requirements.txt        # Python dependencies
├── Dockerfile              # Docker image configuration
├── .dockerignore           # Docker ignore rules
│
├── templates/
│   └── index.html          # Frontend UI
│
├── uploads/                # Uploaded documents
├── data/                   # SQLite database and app data
└── chroma_db/              # ChromaDB vector database storage
```

---

## Docker Deployment

### 1. Build the Docker image

```bash
docker build -t halfgpt .
```

### 2. Run the Docker container

```bash
docker run -d \
  --name halfgpt \
  --restart always \
  -p 8080:8080 \
  --env-file .env \
  halfgpt
```

The app will be available at:

```text
http://localhost:8080
```

---

## AWS Deployment

The GitHub Actions workflow builds and pushes the Docker image to ECR, then deploys to EC2 through AWS Systems Manager Run Command. It uses a GitHub-hosted runner, so no SSH access or GitHub self-hosted runner is required. Chat, Chroma, and uploads persist on an attached EBS volume.

Follow [DEPLOY.md](DEPLOY.md) for the complete setup, including the EC2 instance role, SSM, EBS mount, Secrets Manager, GitHub permissions, and verification steps.

---

## Usage

After running locally or deploying to AWS:

1. Open the app in your browser.
2. Start chatting with the AI assistant.
3. Upload documents to use them as context.
4. Ask questions about uploaded files.
5. Ask current-information questions to trigger web search.
6. Continue conversations with saved chat history.

---

## Example Questions

```text
Summarize the uploaded PDF.
```

```text
Search the web for the latest AI agent news.
```

```text
Based on my uploaded document, what are the key points?
```

```text
Calculate 125 * 48 / 6.
```

---

## Notes

* Do not commit your `.env` file to GitHub.
* Keep API keys inside GitHub Secrets for deployment.
* For production, avoid using `reload=True` in Uvicorn.
* Make sure port `8080` is open in your EC2 security group.
* Rotate any API keys that were accidentally exposed publicly.

---

## Contributing

Contributions are welcome.

To contribute:

1. Fork the repository.
2. Create a new branch.
3. Make your changes.
4. Submit a pull request.

---

## License

This project is open source. Please check the repository license for usage terms.
