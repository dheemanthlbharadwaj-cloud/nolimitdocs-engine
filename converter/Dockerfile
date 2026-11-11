# syntax=docker/dockerfile:1
FROM debian:bookworm-slim
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
# LibreOffice (writer, calc, impress) plus fonts that are metric-compatible with Microsoft Office fonts
# (Carlito=Calibri, Caladea=Cambria, Liberation=Arial/Times/Courier) and Noto for Indian and CJK scripts.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-uno \
      libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui \
      fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation fonts-dejavu-core \
      fonts-noto-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc/*
WORKDIR /app
COPY requirements.txt .
# The optional "ca" build secret lets the image build behind a TLS-inspecting proxy; it is not kept in the image.
RUN --mount=type=secret,id=ca sh -c 'if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; pip3 install --no-cache-dir --break-system-packages -r requirements.txt'
COPY app.py .
ENV PORT=8080
CMD exec python3 -m uvicorn app:app --host 0.0.0.0 --port ${PORT} --workers 1
