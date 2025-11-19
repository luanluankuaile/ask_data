# Example LLM Application

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
docker run -d --name streamlit -p 8501:8501 streamlit --env-file .env
```
