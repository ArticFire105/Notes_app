# Azure and Vercel deployment

This document describes the intended deployment.
The backend runs in Azure Container Apps.
The frontend runs on Vercel.
Cloudflare hosts the DNS records.
Supabase holds application data and authentication.
Gemini provides embeddings and answers.
The backend owns the database credentials.
The browser calls only FastAPI.
The browser receives a public backend URL.
Real secrets belong in Azure's secret store.
GitHub Actions uses Azure workload federation.
The workflow builds a backend container.
GitHub Container Registry stores that container.
Azure pulls the image by commit identifier.
The image contains LibreOffice for slide previews.
The runtime uses a non-root account.
Azure supplies the public HTTPS endpoint.
The application listens on port 7860.
The frontend uses the apex domain.
The backend uses the API subdomain.
Both domains use HTTPS.
The refresh cookie is host-only.
It is limited to the backend's auth path.
It is inaccessible to browser JavaScript.
The cookie uses Secure and SameSite=Lax.
The two production domains are same-site.
Preview domains do not share that property.
Keep the Azure deployment workflow disabled until release checks pass.
Do not put secrets in source files.
Do not commit real documents or evaluation data.
Never paste credentials into a shell transcript.
Use the provider dashboards to enter secrets.
Test with a small group before wider release.
Follow the recovery and rate-limit notes below.

Background workers refresh database heartbeats every 30 seconds. Startup and periodic recovery mark processing records failed after five minutes without a heartbeat; this gives live overlapping revisions time to report their work. Apply `0010_job_heartbeats.sql` before deploying this version. An interrupted job may remain processing until the five-minute window has passed and another backend is running. A database outage longer than that window can also make live work appear stale. In-process rate limits reset on restart; durable shared limits are needed before scaling past one replica.

## Configuration names

Azure Container Apps secrets: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GOOGLE_API_KEY`. Map each secret into the Container App as an environment variable of the same name. The project URL is not secret, but keeping it with backend configuration avoids exposing it to the browser.

Azure environment variables: `APP_ENV`, `FRONTEND_ORIGINS`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `CHAT_MODEL`, `OCR_MODEL`, `MAX_OUTPUT_TOKENS`, `ALLOWED_EMAIL_DOMAIN`, `QUESTIONS_PER_DAY`, `MAX_CONTEXT_TOKENS`, `GLOBAL_DAILY_CAP`, `GLOBAL_DAILY_BUDGET_USD`, `PRICE_INPUT_PER_1M_USD`, `PRICE_OUTPUT_PER_1M_USD`. Only `FRONTEND_ORIGINS` must be set explicitly for browser CORS; the other variables have code defaults. If optional variables are omitted, do not create them as empty strings.

Vercel environment variable: `NEXT_PUBLIC_API_BASE_URL`. It is public and must point to the HTTPS API domain. Set it before the frontend build.

GitHub Actions secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. GitHub supplies `GITHUB_TOKEN` automatically. GitHub Actions variables: `AZURE_RESOURCE_GROUP`, `AZURE_CONTAINER_APP`, `ENABLE_AZURE_DEPLOY`.

## Docker Desktop check

Run from the repository root after starting Docker Desktop:

```powershell
docker build -t notes-backend:local .
docker run --name notes-backend-test --rm -d -p 7860:7860 --memory 1g --cpus 0.5 --env-file <PRIVATE_ENV_FILE> notes-backend:local
docker stats notes-backend-test
```

Replace `<PRIVATE_ENV_FILE>` with a private file you create yourself containing the required Azure backend environment variables. Stop the stats display with Ctrl+C, then run:

```powershell
curl.exe http://localhost:7860/health
docker logs notes-backend-test
docker stop notes-backend-test
```

The health endpoint checks only that the process is serving HTTP. Test an actual PowerPoint preview while observing memory; idle memory is not enough to size LibreOffice. Avoid printing or sharing private environment files or command output containing credentials.

## Ordered setup

1. In Azure for Students, create a resource group and a Container Apps environment using the Consumption workload profile. Create a Container App with external HTTPS ingress, target port 7860, 0.5 vCPU, 1 GiB memory, minimum replicas 0, maximum replicas 1, and single-revision mode. Start with an Azure sample image until the GitHub image exists. Configure an HTTP health probe for `/health`. Verify the chosen region and subscription support these resources.
2. Add the backend secrets and environment variables listed above. Set the production frontend origin exactly; do not use a wildcard. Apply all project Supabase migrations in order before using the app. Never include service credentials in Vercel.
3. Create a Microsoft Entra app or user-assigned identity with a GitHub Actions federated credential for this repository's `main` branch. Grant the identity permissions to update the Container App. Add the three Azure IDs as GitHub Actions secrets and the resource group and app names as GitHub variables. Keep `ENABLE_AZURE_DEPLOY` unset until the blocker and checks are resolved.
4. Connect the GitHub repository to Vercel with root directory `web/`. Set its public API environment variable and add `studymargin.app` as the production domain. Deploy the frontend.
5. In Cloudflare DNS, create the apex A record shown by Vercel for `studymargin.app`. For `api.studymargin.app`, add the CNAME pointing to the Azure-generated Container App hostname and the `asuid.api` TXT verification record shown by Azure. Use DNS-only during Azure managed-certificate validation and renewal; bind the custom domain and managed certificate in Azure. Preserve unrelated records, including mail records.
6. In Supabase Auth URL Configuration, set the site URL to the production frontend and add its HTTPS URL to the redirect allow list. Email-code sign-in does not need to place a token in a redirect URL. Keep the existing email-code template and college-domain enforcement.
7. Set `ENABLE_AZURE_DEPLOY` to `true` only after applying all migrations including `0010_job_heartbeats.sql`, completing the Azure, GitHub, Vercel, DNS, and Supabase configuration above, reviewing the Git history for excluded data, and passing the backend tests, frontend tests, frontend build, and Docker memory check. Then push the reviewed changes to `main`. The first workflow run publishes a GHCR package; make that package public so Azure can pull it, then rerun the workflow if the first deployment failed while the package was private. Complete the live checks in step 8 before inviting users.
8. Check the GitHub Actions run and Azure revision health. Open the API `/health` URL and the frontend over HTTPS. Request an email code, sign in, refresh the page, upload and retry a small test document, use chat and a worksheet, and test on a second browser. Restart the container during uploads and worksheet processing and verify clear retry states. Inspect Azure logs without exposing credentials or document text.

Microsoft's [custom-domain instructions](https://learn.microsoft.com/en-us/azure/container-apps/custom-domains-managed-certificates) describe the Azure validation records. Vercel supplies the actual apex record for the project in its [domain setup](https://vercel.com/docs/domains/set-up-custom-domain). Azure's [billing documentation](https://learn.microsoft.com/en-us/azure/container-apps/billing) explains the Consumption free grant and usage charges.
