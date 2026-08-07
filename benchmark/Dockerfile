# Benchmark core image. Build context MUST be the repository root
# (pyproject.toml lives there): see docker-compose.yml.
FROM python:3.12-slim

WORKDIR /app

# Copy only what the install needs; benchmark/tests stays out of the image.
COPY pyproject.toml README.md ./
COPY benchmark/minemembench ./benchmark/minemembench

RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "minemembench"]
CMD ["probe"]
