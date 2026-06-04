# RaceTrack — Setup Guide

Manual steps required before the CI/CD pipeline is fully operational.
Do these once, in order, after merging the CI/CD PR into staging.

---

## 1. GitHub — Branch Protection

Go to **Settings → Branches → Add branch protection rule** for each branch.

### `staging`
| Setting | Value |
|---|---|
| Require a pull request before merging | ✅ |
| Required approving reviews | **1** |
| Dismiss stale approvals on new commits | ✅ |
| Require status checks to pass | ✅ |
| Required checks | `Install, build & test`, `Terraform plan (staging)` |
| Require branch to be up to date | ✅ |
| Do not allow bypassing (applies to admins) | ✅ |

Also set in **Settings → General → Pull Requests**: allow **Squash merging only** (disable merge commits and rebase).

### `main`
| Setting | Value |
|---|---|
| Require a pull request before merging | ✅ |
| Required approving reviews | **1** |
| Dismiss stale approvals on new commits | ✅ |
| Require status checks to pass | ✅ |
| Required checks | `Install, build & test`, `Terraform plan (prod)` |
| Require branch to be up to date | ✅ |
| Do not allow bypassing | ✅ |
| Restrict direct pushes | ✅ (no force push) |

---

## 2. GitHub — Environments & Secrets

Go to **Settings → Environments** and create two environments: `staging` and `prod`.

For **each** environment, add the following secrets:

| Secret | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` | IAM user or role access key for that environment's AWS account |
| `AWS_SECRET_ACCESS_KEY` | Corresponding secret key |
| `TF_VAR_DB_PASSWORD` | PostgreSQL password for that environment's RDS instance |

And the following variable (not secret):

| Variable | Example value |
|---|---|
| `AWS_REGION` | `us-east-1` |

> **Recommended:** Use IAM OIDC instead of long-lived keys (see "OIDC setup" section below).

---

## 3. AWS — Bootstrap Terraform State

Run this **once** from your local machine with admin credentials.
Creates the S3 bucket and DynamoDB table that store Terraform state.

```bash
cd terraform/bootstrap
terraform init
terraform apply
```

Note the outputs — they give you the bucket and table names (should match what's in `terraform/backend.tf`).

---

## 4. AWS — Provision Databases

The Terraform code manages Lambda, API Gateway, S3, EventBridge, and IAM.
**PostgreSQL (RDS) must be provisioned separately** — Terraform does not create it.

After provisioning, update the `db_host` placeholders:

- `terraform/environments/staging.tfvars` → set `db_host`
- `terraform/environments/prod.tfvars` → set `db_host`

Commit and push these changes on your feature branch.

---

## 5. First Deploy — Staging

After the CI/CD PR is approved and squash-merged into `staging`:

1. The `Deploy → Staging` workflow triggers automatically.
2. It runs `terraform apply` (creates all infrastructure) then deploys Lambda code.
3. After deploy, e2e tests run against the staging API endpoint.
4. Find the API URL in the GitHub Actions logs or run:
   ```bash
   cd terraform
   terraform init -backend-config="key=staging/terraform.tfstate"
   terraform output api_endpoint
   ```

---

## 6. First Deploy — Prod

When a release is ready:

1. Open a PR from `staging` → `main`.
2. Checks run: unit tests + `terraform plan` for prod (plan is posted as a PR comment).
3. Review the plan carefully. Get 1 approval.
4. Merge manually (merge commit, not squash — both methods work for main).
5. `Deploy → Prod` triggers automatically: `terraform apply` → Lambda deploy → e2e tests.

---

## Running Tests Locally

```bash
cd project

# Unit tests (no live infrastructure needed)
python -m pytest tests/ -m "not e2e" -v

# E2E tests (requires a deployed environment)
API_BASE_URL=https://<your-api-id>.execute-api.us-east-1.amazonaws.com \
  python -m pytest tests/ -m "e2e" -v
```

Install dev dependencies first:
```bash
pip install -r requirements-dev.txt psycopg2-binary requests boto3
```

---

## OIDC Setup (Recommended — Avoids Long-Lived AWS Keys)

Instead of `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`, you can use GitHub's OIDC provider so GitHub Actions assumes an IAM role directly.

1. In each AWS account, create an **IAM Identity Provider** for `token.actions.githubusercontent.com`.
2. Create an IAM role with a trust policy scoped to this repo:
   ```json
   {
     "Effect": "Allow",
     "Principal": { "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com" },
     "Action": "sts:AssumeRoleWithWebIdentity",
     "Condition": {
       "StringLike": {
         "token.actions.githubusercontent.com:sub": "repo:camila20ferreira03/RaceTrack:*"
       }
     }
   }
   ```
3. Attach the necessary permissions to the role (Lambda, API Gateway, S3, EventBridge, IAM, CloudWatch Logs).
4. In the GitHub environment secrets, replace `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` with a single secret `AWS_ROLE_ARN` (the role ARN).
5. In the workflow files, replace the `aws-actions/configure-aws-credentials` step with:
   ```yaml
   - uses: aws-actions/configure-aws-credentials@v4
     with:
       role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
       aws-region: ${{ vars.AWS_REGION || 'us-east-1' }}
   ```
