# permits

Hourly-ingested, geocoded, queryable dataset of **Budapest public-space-use permits**,
served over a public FastAPI bbox endpoint and
visualised on an internationalised Vue + MapLibre map.

The source — [`einfoszab.budapest.hu`](https://einfoszab.budapest.hu/publicSpaceUsing?key=kozterulet-hasznalati-hatarozatok)
— only exposes a paginated DataTables feed with Hungarian free-text fields and no
geometry. This project ingests it, **enriches** each permit, and stores it in PostGIS:

- **City / client identity** from Wikidata (P1448 official name, P939 KSH code, P421 timezone).
- **Geometry** from the OENY parcel registry (conscription number → parcel outline,
  reprojected EOV→WGS84), falling back to QLever/OSM address geocoding.
- **Timezone-correct dates** (00:00 in the city's timezone).

Licensed **GPL-3.0** (see [`license.txt`](license.txt)).

---

## Repository layout

```
backend/    FastAPI + SQLAlchemy + GeoAlchemy2 ingestion/enrichment API (Python 3.14, uv)
frontend/   Vue 3 + Vite + MapLibre viewer (pnpm), hosted on AWS Amplify
infra/
  tofu/     OpenTofu: Hetzner k3s cluster (CX23 / AMD64)
  k8s/      Manifests: Postgres StatefulSet, backend, CronJobs, ingress, autoscaler
compose.yaml  Local stack: db + backend + frontend
```

---

## Data model (`permits.permits`)

| column | type | notes |
|---|---|---|
| `id` | bigint PK | |
| `queried_at` | timestamptz | budapest.hu query time |
| `city_wikidata_id` | text | `Q1781` (Budapest) |
| `city_ksh_code` | text | `budap` for Budapest (Wikidata P939 otherwise) |
| `reference_number` | text (unique) | `regNum`; dedup key |
| `client_is_natural_person` | bool | true when requester is `Magánszemély` |
| `client` | text | requester, NULL for natural persons |
| `client_wikidata_id` | text | Wikidata P1448 match |
| `location_source_text` | text | raw `place` |
| `location_conscription_number` | text | `parcelNum` |
| `location` | geometry(Geometry, 4326) | MultiPolygon (OENY) or Point (QLever) |
| `usage_type` | enum | translated `purposeOfUse`; `Egyéb`/unknown → `uncategorized` |
| `occupied_area_in_square_metres` | int | `size` |
| `time_from` / `time_to` | timestamptz | `startOfUse`/`endOfUse` at 00:00 city time |

The whole hourly import runs in **one transaction**: if any enrichment lookup keeps
failing past its tenacity retry budget (`PERMITS_ENRICH_TIMEOUT`, default 600 s) the
transaction rolls back, so the DB is never left with partially-enriched data. A *no
match* (empty lookup) is not a failure — that field is simply left `NULL`.

---

## API

- `GET /permits?bbox=minLon,minLat,maxLon,maxLat[&in_effect_on=YYYY-MM-DD][&usage_type=…][&client=…]`
  — every column of all permits whose geometry intersects the bbox; `in_effect_on`
  omitted ⇒ all dates. **Public, no auth.**
- `GET /permits/coverage` — earliest `queried_at`/`time_from`, latest `time_to`, count
  (drives the timeline).
- `POST /permits/fetch` — runs one import. **Not exposed publicly** (the ingress allows
  only `GET`); invoked by the in-cluster CronJob.

---

## Configuration

The backend is configured entirely through environment variables (see `.env.example`).

| variable | description |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Database credentials. Compose builds the backend's async SQLAlchemy DSN (`DB_CONNECTION_STRING`) from these. |
| `PERMITS_CORS_ORIGINS` | CORS origins for the public read API (comma-separated, or `*`). |
| `PERMITS_ENRICH_TIMEOUT` | Per-lookup total retry budget (seconds) before the enrichment — and the whole import transaction — fails. |
| `PERMITS_BACKUP_S3_URI` | Destination for `POST /permits/backup` dumps, e.g. `s3://my-permits-backups` (an optional key prefix may follow the bucket). AWS credentials are read from the standard `AWS_*` environment variables. Empty disables the endpoint. |

---

## 1. Run locally (Docker Compose)

```bash
cp .env.example .env          # set POSTGRES_PASSWORD etc.
docker compose up --build
```

- Backend: <http://localhost:8000> (`/docs` for Swagger). Migrations run on start.
- Frontend: <http://localhost:5173>
- Trigger a first import:

```bash
curl -X POST http://localhost:8000/permits/fetch
curl "http://localhost:8000/permits?bbox=19.0,47.45,19.12,47.55&in_effect_on=$(date +%F)"
```

Backend tests:

```bash
cd backend && uv sync --no-install-project --extra dev && uv run pytest
```

---

## 2. Build & push images (AMD64)

CX23 is x86, so images are `linux/amd64`. CI (`.github/workflows/build-images.yaml`)
builds `permits-backend` on push to `main`. PostGIS uses the official
`postgis/postgis:18-3.6` image from Docker Hub — nothing to build.

---

## 3. Provision the cluster (OpenTofu)

The OpenTofu inputs live in `.env` (the single source of truth) as `TF_VAR_*` entries
— `tofu` picks them up automatically once they're exported. Fill them in:

- **`TF_VAR_hcloud_token`** — Hetzner Cloud API token (read/write). Create an account
  and a project at <https://console.hetzner.com>, open the project, go to *Security →
  API tokens → Generate API token*, description `Terraform`, permissions *Read & Write*,
  generate, and copy the token.
- **`TF_VAR_cloudflare_api_token`** — Cloudflare API token scoped to Zone:DNS:Edit. Buy
  a domain and point its nameservers at Cloudflare, then in <https://dash.cloudflare.com>
  go to *Manage account → Account API tokens → Create token*, name it
  `permits_terraform`, select *Entire Account → Specified Domains → Select domains…* and
  your domain, enable *DNS & Zones → DNS → Edit*, review, create, and copy the token.
  (cert-manager's DNS-01 solver reuses this token.)
- **`TF_VAR_cloudflare_zone_id`** — in <https://dash.cloudflare.com> open *Domains →
  Overview*, select your domain, scroll to the bottom, and copy the *Zone ID*.
- **`TF_VAR_ssh_public_key`** — generate an ed25519 key and paste the contents of the
  `.pub` file (used to access the nodes).
- **`TF_VAR_k3s_token`** — a strong random secret joining k3s agents to the server.
- **`TF_VAR_lb_ipv4` / `TF_VAR_lb_ipv6`** — leave empty for now; set them after the
  ingress LoadBalancer exists (see step 5).

```bash
cd infra/tofu
set -a; . ../../.env; set +a   # export TF_VAR_* (and the rest of .env)
tofu init
tofu apply
```

This creates the private network, firewall, and a **CX23 master** running k3s (Traefik
and servicelb disabled; cloud-controller external). Fetch the kubeconfig (see the
`kubeconfig_hint` output):

```bash
scp root@$(tofu output -raw master_ipv4):/etc/rancher/k3s/k3s.yaml ./kubeconfig
sed -i '' "s/127.0.0.1/$(tofu output -raw master_ipv4)/" ./kubeconfig
export KUBECONFIG=$PWD/kubeconfig
```

## 4. Cluster add-ons

Install, in order (Helm):

```bash
# Hetzner Cloud Controller Manager (LoadBalancers + node lifecycle)
kubectl -n kube-system create secret generic hcloud --from-literal=token=$TF_VAR_hcloud_token --from-literal=network=permits
helm repo add hcloud https://charts.hetzner.cloud && helm repo update
helm install hccm hcloud/hcloud-cloud-controller-manager -n kube-system --set networking.enabled=true

# Hetzner CSI (PVCs for the Postgres StatefulSet)
helm install hcloud-csi hcloud/hcloud-csi -n kube-system

# ingress-nginx (fronted by a Hetzner LB) + cert-manager
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx -n ingress-nginx --create-namespace \
  --set controller.service.annotations."load-balancer\.hetzner\.cloud/location"=fsn1 \
  --set controller.service.annotations."load-balancer\.hetzner\.cloud/use-private-ip"="true"
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager -n cert-manager --create-namespace --set crds.enabled=true
```

## 5. Cloudflare DNS record for your hostname

Set `TF_VAR_hostname` in `.env` to the hostname you want to serve the API on — a
subdomain like `permits.example.com` or a root domain like `example.com`.

1. Get the ingress LB IPs once the CCM provisions them:
   `kubectl -n ingress-nginx get svc ingress-nginx-controller -o wide`.
2. **Via OpenTofu:** set `TF_VAR_lb_ipv4` (and `TF_VAR_lb_ipv6`) in `.env`, re-export
   (`set -a; . ./.env; set +a`), and `tofu apply` — this creates DNS-only (grey-cloud)
   `A`/`AAAA` records for `TF_VAR_hostname`.
   **Or manually** in the Cloudflare dashboard: *DNS → Add record →* `A` → your
   hostname (or `@` for the root domain) → the LB IPv4, *Proxy status: DNS only*.
   (Grey-cloud keeps the LB + DNS-01 simple.)
3. Create a Cloudflare API token scoped **Zone → DNS → Edit** for your domain; it is
   used both by OpenTofu and by cert-manager's DNS-01 solver.

## 6. Deploy the app

```bash
# Secrets come entirely from .env (the single source of truth).
set -a; . ./.env; set +a

kubectl apply -f infra/k8s/00-namespace.yaml
envsubst < infra/k8s/10-postgres.yaml | kubectl apply -f -
envsubst < infra/k8s/20-backend.yaml | kubectl apply -f -
kubectl apply -f infra/k8s/30-cronjobs.yaml
envsubst < infra/k8s/40-ingress.yaml | kubectl apply -f -

# The cluster-autoscaler needs the worker cloud-init base64-encoded. Render it
# from worker-cloud-init.yaml (envsubst fills in $TF_VAR_k3s_token) and encode it —
# no hand-encoding or pasting into .env required.
export HCLOUD_CLOUD_INIT=$(envsubst < infra/k8s/worker-cloud-init.yaml | base64 | tr -d '\n')
envsubst < infra/k8s/50-cluster-autoscaler.yaml | kubectl apply -f -
```

Verify:

```bash
kubectl -n permits get pods
curl https://$TF_VAR_hostname/permits?bbox=19.0,47.45,19.12,47.55   # valid Let's Encrypt cert
```

### Autoscaling

The backend **HPA** targets **90% CPU**; its stabilization windows are tuned so scaling
reacts to *sustained* (~30 min) load (Kubernetes cannot express an exact "for 30
minutes" rule). When new pods don't fit, the **cluster-autoscaler** adds CX23 **worker
nodes up to 3** (cluster total ≤ 4 CX23) and removes them when idle.

---

## 7. Manage with Nautik

[Nautik](https://nautik.io) is a native Kubernetes client for Mac/iOS.

1. **Add cluster:** Nautik → *Clusters → Add → Import kubeconfig* and select
   `infra/tofu/kubeconfig` (it already points at the master's public IP).
2. **Watch workloads:** open the `permits` namespace to see the `permits-backend`
   Deployment, `permits-db` StatefulSet, and the HPA's current replica count.
3. **Logs / exec:** tap a pod → *Logs* (e.g. tail the backend during a fetch) or
   *Terminal* to `psql` into the DB pod.
4. **Trigger a manual fetch:** Nautik → `permits-fetch` CronJob → *Run now*, or
   `kubectl -n permits create job --from=cronjob/permits-fetch fetch-manual`.
5. **Scaling:** watch nodes appear/disappear under *Nodes* as the cluster-autoscaler
   reacts; inspect the `cluster-autoscaler` Deployment logs in `kube-system`.
6. **Backups:** inspect the `permits-backup` CronJob and its last job's logs.

---

## 8. Backups & restore

A `permits-backup` CronJob runs **daily at 02:53 UTC**. It just calls
`POST /permits/backup` on the in-cluster backend, which runs `pg_dumpall`, wraps the
dump in a `.tar.zst` and uploads it to S3 (`PERMITS_BACKUP_S3_URI` + `AWS_*` from the
`permits-backend` Secret; `infra/k8s/30-cronjobs.yaml`). Restore:

```bash
aws s3 cp s3://your-permits-backups/permits-YYYYMMDDThhmmssZ.tar.zst .
zstd -d permits-*.tar.zst -c | tar -xO permits.sql | \
  kubectl -n permits exec -i permits-db-0 -- psql -U permits
```

---

## 9. Frontend (the map viewer)

Vue 3 + Vite + MapLibre, package-managed with **pnpm**. It reuses the self-hosted
VersaTiles style + OSM assets (`frontend/public/OSM/`, copied from the homepage project)
and the `loadStyle`/colour-scheme logic.

Features:
- **i18n** (vue-i18n): **Hungarian by default**, English available; usage-type labels
  and the legend localised.
- Opens on the **Budapest City Hall**; queries permits **in effect today** in a
  **buffered bbox** (larger than the viewport) so panning/zooming rarely refetches.
- Geometries coloured by `usage_type`; large polygons get the **client name** label
  (or the **permit type** for natural persons); too-small extents become **circles**,
  and dense circles collapse into a **counter** marker (cluster).
- **Legend** + **type/client filters** (persisted automatically via pinia + localStorage).
- **Click** a permit → all fields + the client's **logo (Wikidata P154)** when available.
- **Timeline** (date resolution, logarithmic scale) drags back to the earliest
  in-effect date; opening it **queries all dates**, and dates **before the earliest
  `queried_at`** are flagged (and coloured) as partial.

### Local

Runs as the `frontend` service in `compose.yaml`, or:

```bash
cd frontend && pnpm install && pnpm dev
```

### Hosting (AWS Amplify)

1. Amplify Console → *New app → Host web app* → connect this GitHub repo.
2. **Monorepo:** set the app root to `frontend` (Amplify reads `frontend/amplify.yml`,
   which runs `pnpm install && pnpm run build` and publishes `dist/`).
3. Set the env var `VITE_API_BASE_URL=https://<your-hostname>` (matching `TF_VAR_hostname`).
4. Pushes to `main` auto-deploy via Amplify's GitHub integration.
