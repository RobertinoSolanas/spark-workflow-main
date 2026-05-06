# https://github.com/unoconv/unoserver-docker/blob/c81c0729924750e346e237b89f8ff062d7597a35/Dockerfile
# Modified to use the latest version of unoserver

FROM alpine:3.21

# Explicit numeric UID/GID are required by Kubernetes runAsNonRoot enforcement
ARG UID=100
ARG GID=101
ARG USERNAME=worker
# renovate: pypi: unoserver
ARG VERSION_UNOSERVER=3.5

LABEL org.opencontainers.image.title="unoserver-docker"
LABEL org.opencontainers.image.description="Container image that contains unoserver and libreoffice including large set of fonts for file format conversions"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.documentation="https://github.com/unoconv/unoserver-docker/blob/main/README.adoc"
LABEL org.opencontainers.image.source="https://github.com/unoconv/unoserver-docker"
LABEL org.opencontainers.image.url="https://github.com/unoconv/unoserver-docker"

WORKDIR /

RUN addgroup -S -g ${GID} ${USERNAME} && adduser -S -u ${UID} -G ${USERNAME} ${USERNAME}

RUN apk upgrade --no-cache

RUN apk add --no-cache \
    bash curl \
    py3-pip \
    libreoffice

# fonts - https://wiki.alpinelinux.org/wiki/Fonts
RUN apk add --no-cache \
    font-noto font-noto-cjk font-noto-extra \
    terminus-font \
    ttf-font-awesome \
    ttf-dejavu \
    ttf-freefont \
    ttf-hack \
    ttf-inconsolata \
    ttf-liberation \
    ttf-mononoki  \
    ttf-opensans   \
    fontconfig && \
    fc-cache -f

RUN rm -rf /var/cache/apk/* /tmp/*

# https://github.com/unoconv/unoserver/
RUN pip install --break-system-packages -U unoserver==${VERSION_UNOSERVER}

RUN chown -R ${UID}:0 /run && \
    chmod -R g=u /run

USER ${UID}
WORKDIR /home/worker
ENV HOME="/home/worker"

VOLUME ["/data"]
EXPOSE 2003
COPY --chown=${UID}:${GID} entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
