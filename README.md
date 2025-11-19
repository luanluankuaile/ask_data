# Example LLM Application

This application uses DeepSeek API for LLM and HuggingFace embeddings for document vectorization.

## Configuration

Create a `.env` file in the project root with your DeepSeek API key:

```bash
AZURE_OPENAI_API_KEY="********************"
AZURE_OPENAI_ENDPOINT=https://ai-proxy.lab.epam.com
OPENAI_API_VERSION=2023-12-01-preview

```

## How to run

To run the app, use the following command:

```bash
streamlit run app.py
```

To build the Docker image, use the following command:

```bash
docker build -t streamlit .
```

To run the container, use the following command with an env file:

```bash
docker run -d --name streamlit -p 8501:8501 --env-file .env streamlit
```
