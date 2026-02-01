FROM python:3.12-slim

WORKDIR /app

# 1. Install uv
RUN pip install --no-cache-dir uv==0.4.22

# 2. Copy ALL code first (required for the install step to find your package)
COPY . /app

# 3. Install dependencies + your app into the system Python
# '--system' ensures it installs globally in the container, avoiding venv complexity
RUN uv pip install --system --no-cache .

# 4. Run directly
# Since we installed to system, we can call uvicorn directly. 
# 'uv run' is great locally but can complicate Docker paths.
CMD ["uvicorn", "safeloop_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]