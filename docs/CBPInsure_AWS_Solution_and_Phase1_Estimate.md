# CBPInsure Claims Automation
## AWS Solution Architecture, Phased Plan & Cost Model

**Prepared as:** AWS Solution Architect + Application Architect
**Delivery model:** Offshore (India) development & maintenance
**Rate card:** Trigent Offshore Rates – India (updated 7-Apr-2026); rates are **hourly USD**, converted at 8 hrs/person-day
**Status of product:** ~70% of the claims intake + extraction workflow is working today. Payout decisioning (Step 3) and enterprise hardening are the remaining build.
**Note:** AWS figures are planning estimates (us-east-1), not quotes. Effort figures are computed from the rate card and are draft, to be adjusted with the team.

---

## 1. Executive Summary

The CBPInsure POC ingests scanned Accident & Health (A&H) claim packages (CMS-1500, UB-04, EOB/ERA, policy certificates, claim forms, claims-accumulator spreadsheets), runs OCR, classifies each document, extracts the 19 import fields, auto-fills a structured claim record, and provides an examiner review workbench with a document library and per-page viewer. It runs on a portable stack (Python/Streamlit, containerized) with a database-abstraction layer that already supports SQL Server (local) and PostgreSQL (cloud).

This document defines:
1. The **target AWS solution architecture** with actual services, designed for **scale, multi-tenancy and a SaaS model**.
2. A **phased plan** — minimal-change AWS demo first, production managed service next, SaaS expansion later.
3. A **cost model split into two areas**: (A) Infrastructure (AWS, month-on-month) and (B) Development & Maintenance effort (offshore, rate-card driven).
4. A **draft Phase 1 estimate**, including the **pending Rules Engine discovery (Step 3 — claim authorization)** as a discrete work-stream.
5. An **optional, fully isolated Agentic Framework section** that can be added or removed at any time with no impact on the rest of the plan.

---

## 2. Current State — what "70%" means

| Capability (scoped with client) | State | Approx. completeness |
|---|---|---|
| Step 1 — Intelligent document extraction (OCR, classify, 19 fields, per-page index) | Working | ~90% |
| Step 2 — Auto-fill claim record + examiner review workflow | Working | ~85% |
| Step 3 — Payout adjudication / authorization rules engine | Designed, partially built; needs CBP rule tables | ~25% |
| Non-functional: security/BAA, multi-tenant, autoscale, audit, SaaS controls | Not started | ~15% |

**Defensible positioning:** *"~70% of the claims-intake and extraction workflow is working today; payout decisioning and enterprise hardening are the remaining build."*

**POC facts (for the sample-results slide):** 3 sample cases loaded (Klein-GAIC, Newsom-AXIS, Kabilizya-AXIS GAP) → 8 claims, 17 service lines, 29 documents, 118 indexed pages. Accumulator cross-check available on the Klein case (the only package shipped with the adjudicated spreadsheet).

---

## 3. Target AWS Solution Architecture

### 3.1 Design principles
- **Minimal change now:** reuse the existing container and DB-abstraction; swap the database to managed PostgreSQL and wrap with AWS platform services.
- **Scalable later:** decouple slow OCR from the UI via an async pipeline; scale workers to volume.
- **HIPAA-aligned:** use only HIPAA-eligible AWS services; AWS signs a BAA; encryption, private networking, and audit logging throughout.
- **Multi-tenant SaaS-ready:** tenant isolation in data and access from the start, even if the demo is single-tenant.

### 3.2 Logical architecture (Phase 2 target; Phase 1 is a subset)

```
Browser (CBP examiners)
      |  HTTPS
   CloudFront + WAF
      |
   Application Load Balancer
      |
 ┌───────────────────────────── VPC (private) ─────────────────────────────┐
 │  Examiner Workbench            Async extraction pipeline                 │
 │  ECS Fargate (Streamlit/UI     S3 (docs + page images)                   │
 │   + API)  ───────────────────▶ SQS queue ──▶ ECS Fargate / AWS Batch     │
 │     │                               workers ──▶ Amazon Textract          │
 │     │                                      └──▶ Adjudication/Rules Engine │
 │     ▼                                                 │                   │
 │  RDS PostgreSQL (Multi-AZ, KMS-encrypted) ◀───────────┘                   │
 │  Cognito (auth, per-tenant)   Secrets Manager   KMS                       │
 │  CloudTrail  CloudWatch  AWS Config                                       │
 └───────────────────────────────────────────────────────────────────────── ┘
```

### 3.3 Component mapping (actual AWS services)

| Concern | Phase 1 (demo) | Phase 2 (production SaaS) | HIPAA-eligible |
|---|---|---|---|
| App hosting | AWS App Runner (or 1 ECS Fargate task) | ECS Fargate service, autoscaled, behind ALB + CloudFront + WAF | Yes |
| OCR / extraction | In-app RapidOCR (container) | Async workers (Fargate/Batch) + Amazon Textract (selective) | Yes |
| Database | RDS PostgreSQL single-AZ (db.t4g.micro) | RDS PostgreSQL Multi-AZ, optional read replica | Yes |
| Object storage | DB blobs (as today) | S3 for documents + page images, lifecycle policies | Yes |
| Queue / eventing | — | SQS (+ optional EventBridge) | Yes |
| Auth | Cognito or app password gate | Cognito user pools, per-tenant groups, SSO option | Yes |
| Secrets | Secrets Manager | Secrets Manager + rotation | Yes |
| Encryption | KMS (at rest), TLS (in transit) | KMS CMKs per tenant / data class | Yes |
| Audit & logging | CloudWatch + CloudTrail | CloudWatch + CloudTrail + Config, centralized | Yes |
| Rules engine (Step 3) | Module in app | Dedicated adjudication service + CBP rule tables in RDS | Yes |
| CI/CD | Manual / basic | CodePipeline + CodeBuild + ECR | n/a |

### 3.4 Multi-tenancy & SaaS model (future expansion)
- **Isolation model:** start with a **pooled database + `tenant_id` on every row + PostgreSQL Row-Level Security (RLS)** — lowest cost, fits a per-package service. Offer a **silo option (dedicated schema/DB or dedicated environment)** for security-sensitive clients such as CBP under Brown & Brown vendor-risk review.
- **Tenant onboarding:** Cognito user pool/group per tenant; per-tenant config (rule tables, page caps, volume bands); per-tenant KMS key for silo clients.
- **Metering & billing:** emit per-claim and per-page usage events to a usage table; aggregate monthly for invoicing and service-credit calculation.
- **Commercial fit:** this directly enables the proposed base price + decision-support add-on, monthly volume bands, page cap, monthly accuracy audit / service credits, and a per-system integration fee — all as configuration + metering, not per-client custom code.

---

## 4. Phased Plan

### Phase 0 — AWS foundation (prereq, ~1 week)
AWS Organization/account, VPC, IAM baseline, KMS, request AWS BAA, HIPAA-eligible guardrails, ECR, CI/CD skeleton.

### Phase 1 — Demo on AWS + Rules-Engine discovery (focus of this estimate)
1. **Lift the app to AWS** (App Runner/Fargate, RDS PostgreSQL, Secrets Manager, Cognito/auth gate, HTTPS, restricted access). Minimal code change — the DB layer is already PostgreSQL-capable.
2. **Dedicated demo environment** populated with the sample packages; produce the two deck slides (sample results, decision logic).
3. **Rules Engine discovery & first build (Step 3 — claim authorization):**
   - *Discovery:* workshop CBP's six adjudication checkpoints (DOL within policy term; DOS within benefit period; covered diagnosis; exclusions; service/benefit limits; COB/other insurance). Capture the rule input tables CBP must supply (exclusion code lists, sub-limits, waiting periods, accumulator feed, TIN/provider master).
   - *Build:* configurable engine running the rules the data supports; unsupported rules explicitly flagged "awaiting CBP configuration"; compute net payable + decision (auto-approve / manual review / deny) with a per-rule audit trace; validate against the Klein accumulator.

### Phase 2 — Production managed service (on CBP commitment)
Async OCR pipeline (S3 → SQS → workers), Amazon Textract integration, Multi-AZ RDS, full multi-tenant + metering/billing, monthly accuracy audit + service-credit reporting, per-system integration adapters, security review / pen-test, BAA go-live.

### Phase 3 — SaaS expansion
Self-service tenant onboarding, admin console, per-carrier/policy rule-pack library, analytics & SLA dashboards.

---

## 5. Cost Model — Area A: Infrastructure (AWS, month-on-month)

Planning estimates, us-east-1, USD.

### 5.1 Phase 1 — dedicated demo environment
| Service | Config | Monthly (USD) |
|---|---|---|
| App Runner (or 1 Fargate task) | 1 vCPU / 2 GB, low traffic | 25–50 |
| RDS PostgreSQL | db.t4g.micro, 20 GB, single-AZ | 15–25 |
| Secrets Manager | few secrets | 1–2 |
| S3 + transfer | minimal | 1–5 |
| CloudWatch + CloudTrail | minimal | 4–8 |
| Cognito | < 50 users (free tier) | 0–2 |
| **Phase 1 infrastructure total** | | **≈ $50–95 / month** |

### 5.2 Phase 2 — production steady-state (excluding Textract)
| Service | Config | Monthly (USD) |
|---|---|---|
| ECS Fargate (web) | 2 tasks, autoscaled | 70–140 |
| ECS Fargate / AWS Batch (OCR workers) | scale-to-zero, bursty | 100–300 |
| RDS PostgreSQL | Multi-AZ, backups | 90–180 |
| S3 + lifecycle | documents + images | 10–40 |
| SQS / EventBridge | volume-based | 5–20 |
| CloudFront + WAF | moderate | 20–60 |
| Cognito, Secrets, KMS, Config | — | 15–40 |
| CloudWatch / CloudTrail (centralized) | — | 20–50 |
| **Phase 2 subtotal (excl. Textract)** | | **≈ $330–830 / month** |

### 5.3 Amazon Textract — key variable cost (model against the page cap)
- Forms/tables extraction ≈ **$15–65 per 1,000 pages** (feature-dependent).
- **Open question that must be confirmed with CBP:** does "1,000–1,500 / week" mean **claims** or **documents**? In the samples, one claim = 7–12 documents and up to ~75 pages.
  - ~1,500 **documents**/week ≈ 6,000/month; at ~10 pages/doc ≈ 60,000 pages/month → Textract ≈ **$900–3,900 / month**.
  - If it means **claims**, multiply document/page counts several-fold.
- **Mitigation:** use RapidOCR for the bulk and route only hard forms to Textract; enforce the page cap. This keeps Textract controllable and per-package priceable.

---

## 6. Cost Model — Area B: Development & Maintenance Effort (offshore)

### 6.1 Rate card applied (Trigent Offshore – India, hourly USD)
| Role | Rate-card entry | USD / hr |
|---|---|---|
| AWS Architect | Cloud → AWS Architect | 48 |
| Application Architect | Other Technical Roles → Application Architect | 45 |
| DevOps Engineer | Other Technical Roles → DevOps Engineer | 42 |
| Python Developer (3–5y) | Server-side → Python (Developer) | 36 |
| Python Jr Engineer (1–2y) | Server-side → Python (Jr) | 33 |
| Business Analyst | Other Roles → Business Analyst | 38 |
| QA Engineer (Sr, Manual) | Testing → Manual Test Engineer (Sr) | 30 |
| Project Manager | Manager → Project Manager | 45 |

### 6.2 Phase 1 effort & cost (computed, 8 hrs/day)
| Role | Rate/hr | Person-days | Hours | Cost (USD) |
|---|---:|---:|---:|---:|
| AWS Architect | 48 | 2 | 16 | 768 |
| Application Architect | 45 | 3 | 24 | 1,080 |
| DevOps Engineer | 42 | 13 | 104 | 4,368 |
| Python Developer (3–5y) | 36 | 30 | 240 | 8,640 |
| Python Jr Engineer (1–2y) | 33 | 8 | 64 | 2,112 |
| Business Analyst | 38 | 9 | 72 | 2,736 |
| QA Engineer (Sr Manual) | 30 | 8 | 64 | 1,920 |
| Project Manager (part-time) | 45 | 6 | 48 | 2,160 |
| **Subtotal** | | **79** | **632** | **23,784** |
| Contingency (15%) | | | | 3,568 |
| **Phase 1 total** | | **~91** | | **≈ $27,352** |

Indicative duration: **5–6 weeks**, 4–5 person team.

### 6.3 Work-stream breakdown (person-days)
| Work-stream | Role(s) | Days |
|---|---|---:|
| AWS foundation (VPC, IAM, KMS, ECR, BAA request) | DevOps, Architect | 8 |
| Lift app to AWS (App Runner/Fargate, RDS, Secrets, HTTPS) | DevOps, Python | 10 |
| Auth gate (Cognito/app login) + access restriction | Python | 5 |
| Demo data load + 2 deck slides | Python, BA | 4 |
| **Rules Engine discovery (Step 3)** | BA, Architect, Python | 12 |
| **Rules Engine first build** (config rules, payout calc, audit trace, Klein validation) | Python ×2, QA | 22 |
| Security baseline (encryption, logging, least-privilege) | DevOps, Architect | 6 |
| QA, UAT support, demo hardening | QA, Python | 8 |
| PM / coordination (part-time) | PM | 6 |
| **Subtotal** | | **~79** (+15% contingency ≈ 91) |

### 6.4 Maintenance (steady-state, offshore, per month)
| Activity | Role | Days/mo | Rate/hr | Cost (USD) |
|---|---|---:|---:|---:|
| Platform ops, patching, monitoring | DevOps | 3.5 | 42 | 1,176 |
| Rule-table updates, small enhancements | Python | 4 | 36 | 1,152 |
| Monthly accuracy audit + service-credit report | Business Analyst | 2.5 | 38 | 760 |
| Support / incident | QA | 2.5 | 30 | 600 |
| **Maintenance total** | | **12.5** | | **≈ $3,688 / month** |

---

## 7. Phase 1 — Rules Engine (Claim Authorization) Draft Estimate (isolated)

The pending Step 3 is priced on its own so it can be approved independently.

| Item | Detail |
|---|---|
| Discovery | 6-checkpoint workshop; define required CBP rule inputs (exclusions, sub-limits, waiting periods, accumulator feed, provider/TIN master); sign-off on decision logic |
| Build | Config-driven engine; runnable rules implemented; unsupported rules flagged "awaiting CBP config"; net payable + decision + per-rule audit trail; Klein accumulator validation harness |
| Effort | Discovery 12 pd + Build 22 pd = **34 person-days** (subset of Phase 1) |
| Computed cost | BA 6d, App Architect 3d, Python Dev 18d, Python Jr 4d, QA 3d → **≈ $9,864** |
| Infra impact | None beyond Phase 1 (runs as a module; promoted to a service in Phase 2) |
| Dependency / risk | Blocked without CBP's rule tables; estimate assumes CBP provides them during discovery |

---

## 8. Optional — Agentic Framework (fully isolated; add/remove anytime)

> **Isolation guarantee:** nothing elsewhere in this plan, architecture, or cost depends on this section. It is feature-flagged; if disabled, the deterministic pipeline in Sections 3–7 runs exactly as specified. It can be added or removed at any time with zero impact on other items.

### 8.1 Where it adds value (opt-in)
1. **Extraction agent** — reconciles noisy OCR fields (e.g., resolve a mis-read TIN against the provider master), reducing `needs_review` volume.
2. **Adjudication co-pilot** — drafts the claim note and explains the rule-by-rule decision for the examiner (maps directly to "Tier 2 value = decision + claim note").
3. **Document triage agent** — routes/labels incoming packages, flags anomalies and duplicates.

### 8.2 AWS fit
- **Amazon Bedrock** (HIPAA-eligible) with guardrails, PII redaction, and a human-in-the-loop gate.
- Runs as a **separate microservice** invoked by the pipeline; no change to the core extraction or rules engine.

### 8.3 Indicative cost (only if enabled)
- **Infrastructure:** Bedrock is per-token — a few hundred USD/month at demo volume, volume-driven in production; modeled separately so it never contaminates the base cost.
- **Effort (first agent — adjudication co-pilot, computed from rate card):**

| Role | Rate-card entry | USD/hr | Days | Cost (USD) |
|---|---|---:|---:|---:|
| AI Solution / Platform Architect | AI Roles | 50 | 3 | 1,200 |
| AI Engineer (Bedrock) | AI Roles → AI Engineer | 55 | 10 | 4,400 |
| Python Developer (3–5y) | Server-side → Python | 36 | 4 | 1,152 |
| AI QA Engineer | AI Roles → AI QA | 40 | 3 | 960 |
| **Agentic co-pilot add-on** | | | **20** | **≈ $7,712** |

---

## 9. Consolidated Cost Snapshot

| Line | One-time (USD) | Monthly (USD) |
|---|---:|---:|
| Phase 1 development (incl. 15% contingency) | ≈ 27,352 | — |
| — of which: Rules Engine (Step 3) | ≈ 9,864 | — |
| Phase 1 AWS infrastructure (demo) | — | ≈ 50–95 |
| Maintenance (offshore) | — | ≈ 3,688 |
| Phase 2 AWS infrastructure (excl. Textract) | — | ≈ 330–830 |
| Amazon Textract (production, volume-driven) | — | ≈ 900–3,900+ (confirm claims vs documents) |
| Optional Agentic co-pilot (one-time build) | ≈ 7,712 | + Bedrock usage |

---

## 10. Assumptions, Risks & Open Questions
1. **Claims vs documents** for "1,000–1,500/week" — swings Textract cost and per-unit pricing; confirm with CBP.
2. **BAA & Brown & Brown vendor-risk** are gating items before any live PHI; Phase 1 demos on CBP's shared samples only.
3. **OCR accuracy** on noisy scans is uneven today; Textract and/or the agentic option improve it at added cost — a real tradeoff.
4. **CBP must supply rule tables** for Step 3; without them the engine runs partial and flags the rest.
5. **Rate card** rates are hourly (India offshore, 7-Apr-2026) converted at 8 hrs/day; blended team and effort to be confirmed with the delivery team.
6. **AWS figures** are planning estimates (us-east-1); finalize with a detailed calculator once volume and region are fixed.

---

*Document generated for internal review; effort and infrastructure figures are draft and to be adjusted after team discussion.*
