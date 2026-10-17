FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION=1.0.14

RUN apk add --no-cache python3 py3-pip \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --disable-pip-version-check \
        "paho-mqtt==2.1.0" \
    && rm -rf /root/.cache

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED="1" \
    TECNOHEAD_DATA_DIR="/data"

COPY app /opt/tecnohead_hp/app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL io.hass.type="app" \
      io.hass.version="${BUILD_VERSION}" \
      org.opencontainers.image.title="TecnoHead HP"

CMD ["/run.sh"]
