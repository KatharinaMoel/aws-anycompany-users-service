resource "aws_cognito_user_pool" "users" {
  name                     = "${var.name_prefix}-pool"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = "INACTIVE" # everything is torn down with terraform destroy

  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_numbers   = true
    require_uppercase = true
    require_symbols   = false
  }

  # Workshop users are created with admin-create-user; no public sign-up.
  admin_create_user_config {
    allow_admin_create_user_only = true
  }
}

resource "aws_cognito_user_pool_client" "users" {
  name            = "${var.name_prefix}-client"
  user_pool_id    = aws_cognito_user_pool.users.id
  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH", # how the workshop fetches a token from the CLI
    "ALLOW_USER_SRP_AUTH",      # what a real client would use
    "ALLOW_REFRESH_TOKEN_AUTH", # needed to refresh without re-authenticating
  ]
}
