FROM python:3.12-slim-bookworm

LABEL maintainer="H&Rsolucionesweb.com"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/project/src \
    SONORA_DATOS=mvp

WORKDIR /project

COPY requirements.txt ./
RUN python -m pip install -r requirements.txt \
    && useradd --create-home data-user

COPY --chown=data-user:data-user . .
RUN python -m health_data.publicar_mvp --verificar

USER data-user

EXPOSE 8501

HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=5 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2).close()"]

CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
