ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM
RUN apk add --no-cache python3
COPY druckbruecke.py /app/druckbruecke.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh
CMD [ "/run.sh" ]
