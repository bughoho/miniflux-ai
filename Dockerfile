FROM python:3.11-alpine
LABEL authors="qetesh"
WORKDIR /app
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt
COPY ./main.py ./
COPY ./custom_table.py ./
COPY ./default.css ./
CMD [ "python3","-u","main.py" ]