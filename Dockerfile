# Hugging Face Spaces — Docker SDK
# Runs the Streamlit app on the HF-required port 7860.

FROM python:3.10-slim

# System packages:
#   git       → forecaster.py clones the Kronos repo at startup
#   build-essential / curl → needed for some Python wheel builds (curl_cffi, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces best practice: run as a non-root user.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:${PATH}"

WORKDIR /home/user/app

# Install Python dependencies first (better Docker layer caching).
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application.
COPY --chown=user:user . .

# Streamlit server config for Spaces.
ENV STREAMLIT_SERVER_PORT=7860 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    HF_HOME=/home/user/.cache/huggingface

EXPOSE 7860

CMD ["streamlit", "run", "app.py"]
