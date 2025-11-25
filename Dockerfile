FROM python:3.11-slim-bookworm

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install -r /code/requirements.txt

COPY ./* /code/*

EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "app.py"]
