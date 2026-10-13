resource "aws_dynamodb_table" "users" {
  name         = var.name_prefix # the specs pin this to "anycompany-users"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userid"

  attribute {
    name = "userid"
    type = "S"
  }
}
