FROM python:3.12-alpine
RUN apk add --no-cache ffmpeg font-dejavu
COPY seed.py /seed.py
CMD ["python3", "-u", "/seed.py"]
