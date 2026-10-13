output "users_table_name" {
  description = "Name of the DynamoDB table holding user records."
  value       = aws_dynamodb_table.users.name
}

output "users_table_arn" {
  description = "ARN of the DynamoDB table holding user records."
  value       = aws_dynamodb_table.users.arn
}

output "crud_function_name" {
  description = "Name of the CRUD Lambda function."
  value       = aws_lambda_function.users.function_name
}

output "api_invoke_url" {
  description = "Base URL of the deployed API stage."
  value       = aws_api_gateway_stage.prod.invoke_url
}

output "user_pool_id" {
  description = "Id of the Cognito user pool issuing access tokens."
  value       = aws_cognito_user_pool.users.id
}

output "app_client_id" {
  description = "Id of the Cognito app client the authorizer accepts tokens for."
  value       = aws_cognito_user_pool_client.users.id
}

output "authorizer_function_name" {
  description = "Name of the Lambda token authorizer."
  value       = aws_lambda_function.authorizer.function_name
}
