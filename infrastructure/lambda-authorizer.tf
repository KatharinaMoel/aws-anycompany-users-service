# Dependencies are installed into build/, never into src/, which holds only our
# own code. The workstation is Graviton, so these are the arm64 wheels the
# arm64 function needs.
resource "null_resource" "authorizer_dependencies" {
  triggers = {
    requirements = filesha256("${path.module}/../src/authorizer/requirements.txt")
    source       = filesha256("${path.module}/../src/authorizer/app.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      rm -rf "${path.module}/../build/authorizer"
      mkdir -p "${path.module}/../build/authorizer"
      python3.13 -m pip install -q \
        -r "${path.module}/../src/authorizer/requirements.txt" \
        -t "${path.module}/../build/authorizer"
      cp "${path.module}/../src/authorizer/app.py" "${path.module}/../build/authorizer/"
    EOT
  }
}

data "archive_file" "authorizer" {
  type        = "zip"
  source_dir  = "${path.module}/../build/authorizer"
  output_path = "${path.module}/../build/authorizer.zip"

  depends_on = [null_resource.authorizer_dependencies]
}

data "aws_iam_policy_document" "authorizer_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "authorizer" {
  name               = "${var.name_prefix}-authorizer-role"
  assume_role_policy = data.aws_iam_policy_document.authorizer_assume_role.json
}

resource "aws_iam_role_policy_attachment" "authorizer_basic" {
  role       = aws_iam_role.authorizer.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# The authorizer talks to no AWS API: it fetches the public JWKS over HTTPS and
# verifies signatures locally. X-Ray write is all it needs beyond logging.
data "aws_iam_policy_document" "authorizer" {
  statement {
    sid = "XRayWrite"

    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
    ]

    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "authorizer" {
  name   = "${var.name_prefix}-authorizer-policy"
  role   = aws_iam_role.authorizer.id
  policy = data.aws_iam_policy_document.authorizer.json
}

resource "aws_cloudwatch_log_group" "authorizer" {
  name              = "/aws/lambda/${var.name_prefix}-authorizer"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "authorizer" {
  function_name = "${var.name_prefix}-authorizer"
  role          = aws_iam_role.authorizer.arn
  handler       = "app.handler"
  runtime       = var.lambda_runtime
  architectures = ["arm64"]
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  filename         = data.archive_file.authorizer.output_path
  source_code_hash = data.archive_file.authorizer.output_base64sha256

  tracing_config {
    mode = "Active"
  }

  logging_config {
    log_format            = "JSON"
    application_log_level = "INFO"
    system_log_level      = "WARN"
    log_group             = aws_cloudwatch_log_group.authorizer.name
  }

  environment {
    variables = {
      USER_POOL_ID  = aws_cognito_user_pool.users.id
      APP_CLIENT_ID = aws_cognito_user_pool_client.users.id
      # AWS_REGION is reserved and set by the Lambda runtime itself.
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.authorizer_basic,
    aws_cloudwatch_log_group.authorizer,
  ]
}

# The authorizer is declared inside the OpenAPI body, so Terraform never sees
# its generated id - hence the wildcard on this API's authorizers.
resource "aws_lambda_permission" "api_authorizer" {
  statement_id  = "AllowAPIGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.users.execution_arn}/authorizers/*"
}
