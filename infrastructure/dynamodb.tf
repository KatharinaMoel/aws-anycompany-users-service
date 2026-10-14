resource "aws_dynamodb_table" "users" {
  name         = var.name_prefix # the specs pin this to "anycompany-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userid"

  attribute {
    name = "userid"
    type = "S"
  }

  # A GSI key must also be declared as an attribute on the table.
  attribute {
    name = "email"
    type = "S"
  }

  # Lets GET /users/search query by email instead of scanning the table.
  # DynamoDB allows one GSI per table update, so a second index would need its
  # own apply.
  global_secondary_index {
    name            = var.email_index_name
    hash_key        = "email"
    projection_type = "ALL"
  }
}
