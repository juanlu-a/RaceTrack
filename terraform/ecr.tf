# ── ECR: container image repositories ────────────────────────────────────────
# One repo per long-running service. CI builds + pushes images here (tagged with
# the git SHA and `latest`); ECS pulls from them. force_delete lets `terraform
# destroy` remove repos that still hold images.

resource "aws_ecr_repository" "services" {
  for_each = local.ecr_repos

  name         = each.value
  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = local.common_tags
}

# Keep only the most recent N images per repo to bound storage cost.
resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep only the last ${var.ecr_keep_last_images} images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.ecr_keep_last_images
      }
      action = { type = "expire" }
    }]
  })
}
