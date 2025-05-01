FROM python:3.11-alpine

WORKDIR /ssmart
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .


EXPOSE 8000

CMD ["python", "-m", "app.run"]
