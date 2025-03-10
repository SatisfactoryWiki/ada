FROM python:3.10

RUN apt update \
  && apt install -y --no-install-recommends graphviz

COPY . .

RUN pip3 install -r requirements.txt

ENV PYTHONUNBUFFERED=TRUE

ENTRYPOINT ["python3", "bot.py"]
