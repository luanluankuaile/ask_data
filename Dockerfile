FROM python:3.11-slim-bookworm

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install -r /code/requirements.txt

COPY ./app /code/app

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "app/main.py"]
