variable "name_prefix" {
  description = "Prefix for every resource name, to avoid collisions in a shared account."
  type        = string
  default     = "anycompany-users"
}

variable "lambda_runtime" {
  description = "Lambda runtime for both functions."
  type        = string
  default     = "python3.13"
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds. Above the 3 s default because the authorizer's cold start includes an HTTPS fetch of the Cognito JWKS."
  type        = number
  default     = 10
}

variable "lambda_memory_size" {
  description = "Lambda memory in MB. Above the 128 MB default so importing cryptography does not drag out the cold start."
  type        = number
  default     = 256
}

variable "stage_name" {
  description = "API Gateway stage name."
  type        = string
  default     = "prod"
}

variable "log_retention_days" {
  description = "Retention for every CloudWatch log group this stack creates."
  type        = number
  default     = 30
}

variable "cors_allow_origin" {
  description = "Value for the Access-Control-Allow-Origin header on API responses."
  type        = string
  default     = "*"
}
