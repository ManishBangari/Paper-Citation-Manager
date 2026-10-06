FROM python:3.12-slim

WORKDIR /usr/src/ui

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./

# run as a normal user instead of root
RUN useradd --create-home appuser
USER appuser

# the compose files override this; it is where the API container is reachable inside the compose network
ENV API_URL=http://app:8000

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
