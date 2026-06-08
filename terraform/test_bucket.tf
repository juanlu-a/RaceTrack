# Scratch bucket for ad-hoc testing and debugging per environment.
# Safe to destroy at any time — no application data stored here.
resource "aws_s3_bucket" "test" {
  bucket = "${local.prefix}-test"
  tags   = merge(local.common_tags, { Purpose = "testing" })
}

resource "aws_s3_bucket_public_access_block" "test" {
  bucket                  = aws_s3_bucket.test.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
