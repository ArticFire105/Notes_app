# Run the FastAPI backend in Azure Container Apps.
# The frontend is deployed separately on Vercel.
# This image listens on port 7860.
# Azure routes external requests to that port.
# Python 3.12 matches the project requirement.
# The slim base avoids unnecessary system packages.
# LibreOffice converts PowerPoint previews to PDF.
# The Impress package supplies presentation conversion.
# Temporary conversion files live inside the container.
# Durable documents remain in Supabase Storage.
# The database and application secrets come from Azure.
# Secrets must never be copied into this image.
# The Docker context is restricted by .dockerignore.
# uv installs the dependencies from the lockfile.
# Development dependencies are not installed.
# The project source is copied after dependency installation.
# This keeps source changes from invalidating dependency layers.
# The app does not require a local embedding model.
# Gemini creates embeddings over the network.
# No model weights are downloaded during image creation.
# A non-root account runs the application.
# Its home directory holds temporary LibreOffice profiles.
# Python output is unbuffered for container logging.
# Python bytecode files are unnecessary in the image.
# The health command only calls the local health route.
# Azure should also configure an HTTP health probe.
# A single worker avoids duplicate in-memory job queues.
# Scale-to-zero can interrupt background jobs.
# Startup recovery must handle those interruptions.
# Uvicorn does not trust arbitrary forwarded headers here.
# Cookies use the production setting behind the proxy.
# Application logs must not contain document content.
# Azure ingress supplies HTTPS outside the container.
# Build this image from the repository root.
# Never include real credentials in the build context.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends libreoffice-impress && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 notes
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY --chown=notes:notes app ./app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/home/notes
USER notes
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/health', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--no-access-log"]
