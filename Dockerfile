FROM python:3.11-slim-bookworm

WORKDIR /code

COPY ./back_end/requirements.txt /code/back_end/requirements.txt

RUN pip install -r /code/back_end/requirements.txt

COPY . /code/

EXPOSE 8000

CMD ["python", "start.py"]
