# Example LLM Application

This application uses DeepSeek API for LLM and HuggingFace embeddings for document vectorization.

## Configuration

Create a `.env` file in the project root with your DeepSeek API key:

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

You can get your API key from [DeepSeek Platform](https://platform.deepseek.com/).

## How to run

To run the app, use the following command:

```bash
streamlit run app/main.py
```

To build the Docker image, use the following command:

```bash
docker build -t streamlit .
```

To run the container, use the following command:

```bash
docker run -d --name streamlit -p 8501:8501 -e DEEPSEEK_API_KEY=your_api_key streamlit
```

Or with an env file:

```bash
docker run -d --name streamlit -p 8501:8501 --env-file .env streamlit
```
