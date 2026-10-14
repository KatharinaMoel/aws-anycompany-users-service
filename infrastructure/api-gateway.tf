locals {
  # Proxy integration shared by all five operations.
  lambda_integration = {
    type                = "aws_proxy"
    httpMethod          = "POST" # always POST for a Lambda proxy integration
    uri                 = "arn:aws:apigateway:${data.aws_region.current.region}:lambda:path/2015-03-31/functions/${aws_lambda_function.users.arn}/invocations"
    passthroughBehavior = "when_no_match"
  }

  # Phase 2 authorization (Task 4). Phase 1 used
  # x-amazon-apigateway-auth = { type = "AWS_IAM" } on every operation, so the
  # API was closed from its first deployment and never served a method with
  # authorization NONE.
  cognito_security = [{
    CognitoAuthorizer = []
  }]

  userid_path_parameter = [{
    name        = "userid"
    in          = "path"
    required    = true
    description = "Server-generated uuid4 identifying the user."
    schema      = { type = "string" }
  }]

  # CORS preflight, one operation per path.
  #
  # This is the only method on the API that carries no authorizer, and the
  # exception is unavoidable rather than convenient: a browser deliberately
  # sends no Authorization header on a preflight, so an authorizer here would
  # deny it and the browser would never send the real request - the API would be
  # unreachable from any web page while looking correctly secured. The exposure
  # is bounded: a MOCK integration is answered by API Gateway itself, so it
  # reaches no backend, reads nothing, and returns headers plus an empty object.
  # The only thing it discloses is which methods a path has, which the OpenAPI
  # document below already states.
  #
  # Each path advertises only the methods it really has; a blanket
  # GET,POST,PUT,DELETE,OPTIONS everywhere would claim DELETE /users exists.
  preflight = {
    for path, methods in {
      "/users"          = "GET,POST,OPTIONS"
      "/users/search"   = "GET,OPTIONS"
      "/users/{userid}" = "GET,PUT,DELETE,OPTIONS"
      } : path => {
      options = {
        summary = "CORS preflight; returns headers only."

        # A response parameter can only be set on a header the method response
        # declares, so these three names have to appear here as well.
        responses = {
          "200" = {
            description = "Allowed origin, methods, and headers."
            headers = {
              "Access-Control-Allow-Origin"  = { schema = { type = "string" } }
              "Access-Control-Allow-Methods" = { schema = { type = "string" } }
              "Access-Control-Allow-Headers" = { schema = { type = "string" } }
            }
          }
        }

        # No security key: authorization is declared per operation in this
        # document and never globally, so leaving it out is what makes the
        # method unauthenticated. There is no inherited requirement to switch off.
        "x-amazon-apigateway-integration" = {
          type = "mock"

          # Without this template API Gateway has nothing to answer the request
          # with and returns 500.
          requestTemplates = {
            "application/json" = "{\"statusCode\": 200}"
          }

          responses = {
            default = {
              statusCode = "200"

              # The inner single quotes are required. Without them API Gateway
              # reads the value as a mapping expression rather than a literal
              # and sends the header empty.
              responseParameters = {
                "method.response.header.Access-Control-Allow-Origin"  = "'${var.cors_allow_origin}'"
                "method.response.header.Access-Control-Allow-Methods" = "'${methods}'"
                "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
              }

              responseTemplates = {
                "application/json" = "{}"
              }
            }
          }
        }
      }
    }
  }

  openapi_body = {
    openapi = "3.0.1"

    info = {
      title       = "${var.name_prefix}-api"
      description = "RESTful API for managing AnyCompany user records."
      version     = "1.0.0"
    }

    # CORS headers on the errors API Gateway generates itself, before any
    # integration runs - including the 403 of the AWS_IAM phase and the 401 the
    # authorizer produces. The templates reproduce API Gateway's own default, so
    # these errors keep their JSON body.
    "x-amazon-apigateway-gateway-responses" = {
      DEFAULT_4XX = {
        responseParameters = {
          "gatewayresponse.header.Access-Control-Allow-Origin"  = "'${var.cors_allow_origin}'"
          "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
          "gatewayresponse.header.Access-Control-Allow-Methods" = "'GET,POST,PUT,DELETE,OPTIONS'"
        }
        responseTemplates = {
          "application/json" = "{\"message\":$context.error.messageString}"
        }
      }

      DEFAULT_5XX = {
        responseParameters = {
          "gatewayresponse.header.Access-Control-Allow-Origin"  = "'${var.cors_allow_origin}'"
          "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
          "gatewayresponse.header.Access-Control-Allow-Methods" = "'GET,POST,PUT,DELETE,OPTIONS'"
        }
        responseTemplates = {
          "application/json" = "{\"message\":$context.error.messageString}"
        }
      }
    }

    paths = {
      "/users" = merge(local.preflight["/users"], {
        get = {
          operationId                       = "listUsers"
          summary                           = "List every user record."
          responses                         = { "200" = { description = "A users array." } }
          security                          = local.cognito_security
          "x-amazon-apigateway-integration" = local.lambda_integration
        }

        post = {
          operationId = "createUser"
          summary     = "Create a user record from a name and email."
          requestBody = {
            required = true
            content = {
              "application/json" = {
                schema = { "$ref" = "#/components/schemas/UserInput" }
              }
            }
          }
          responses = {
            "201" = { description = "The created user record." }
            "400" = { description = "The name or email is missing or empty." }
          }
          security                          = local.cognito_security
          "x-amazon-apigateway-integration" = local.lambda_integration
        }
      })

      # API Gateway matches a literal segment ahead of a path variable whatever
      # order the paths appear in here, so /users/search reaches this operation
      # and never get_user with userid = "search".
      "/users/search" = merge(local.preflight["/users/search"], {
        get = {
          operationId = "searchUsers"
          summary     = "Find users by exact email address."

          parameters = [{
            name        = "email"
            in          = "query"
            required    = true
            description = "Exact, case-sensitive email address to match."
            schema      = { type = "string" }
          }]

          responses = {
            "200" = { description = "A users array, empty when nothing matches." }
            "400" = { description = "The email query parameter is missing or blank." }
          }

          security                          = local.cognito_security
          "x-amazon-apigateway-integration" = local.lambda_integration
        }
      })

      "/users/{userid}" = merge(local.preflight["/users/{userid}"], {
        get = {
          operationId = "getUser"
          summary     = "Fetch one user record by id."
          parameters  = local.userid_path_parameter
          responses = {
            "200" = { description = "The user record." }
            "404" = { description = "No user with that id." }
          }
          security                          = local.cognito_security
          "x-amazon-apigateway-integration" = local.lambda_integration
        }

        put = {
          operationId = "updateUser"
          summary     = "Replace a user record's name and email."
          parameters  = local.userid_path_parameter
          requestBody = {
            required = true
            content = {
              "application/json" = {
                schema = { "$ref" = "#/components/schemas/UserInput" }
              }
            }
          }
          responses = {
            "200" = { description = "The updated user record." }
            "400" = { description = "The name or email is missing or empty." }
            "404" = { description = "No user with that id." }
          }
          security                          = local.cognito_security
          "x-amazon-apigateway-integration" = local.lambda_integration
        }

        delete = {
          operationId = "deleteUser"
          summary     = "Remove a user record."
          parameters  = local.userid_path_parameter
          responses = {
            "200" = { description = "An empty JSON object." }
            "404" = { description = "No user with that id." }
          }
          security                          = local.cognito_security
          "x-amazon-apigateway-integration" = local.lambda_integration
        }
      })
    }

    components = {
      securitySchemes = {
        CognitoAuthorizer = {
          # A TOKEN authorizer's identity source is this header.
          type                           = "apiKey"
          name                           = "Authorization"
          in                             = "header"
          "x-amazon-apigateway-authtype" = "custom"

          "x-amazon-apigateway-authorizer" = {
            type          = "token"
            authorizerUri = "arn:aws:apigateway:${data.aws_region.current.region}:lambda:path/2015-03-31/functions/${aws_lambda_function.authorizer.arn}/invocations"

            # API Gateway replays the cached policy across routes for this long,
            # which is why the authorizer returns a stage-wide resource.
            authorizerResultTtlInSeconds = 300
          }
        }
      }

      schemas = {
        UserInput = {
          type     = "object"
          required = ["name", "email"]
          properties = {
            name  = { type = "string", description = "Non-empty display name." }
            email = { type = "string", description = "Non-empty email address." }
          }
        }

        User = {
          type = "object"
          properties = {
            userid    = { type = "string", description = "Server-generated uuid4." }
            name      = { type = "string" }
            email     = { type = "string" }
            createdAt = { type = "string", description = "ISO 8601 timestamp, UTC." }
            updatedAt = { type = "string", description = "ISO 8601 timestamp, UTC." }
          }
        }
      }
    }
  }
}

resource "aws_api_gateway_rest_api" "users" {
  name        = "${var.name_prefix}-api"
  description = "RESTful API for managing AnyCompany user records."
  body        = jsonencode(local.openapi_body)

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_lambda_permission" "api_users" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.users.function_name
  principal     = "apigateway.amazonaws.com"

  # Any method of any resource in any stage of this API.
  source_arn = "${aws_api_gateway_rest_api.users.execution_arn}/*/*"
}

# ---------------------------------------------------------------------------
# Access logging prerequisite.
#
# A REST API stage cannot write access logs until the account's API Gateway
# settings carry a CloudWatch Logs role ARN. Note that aws_api_gateway_account
# is account- and region-wide singleton state, not per-stack: in a shared
# account the last apply wins, and a destroy here removes the role for every
# other REST API in this region.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "apigw_cloudwatch_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apigw_cloudwatch" {
  name               = "${var.name_prefix}-apigw-cloudwatch-role"
  assume_role_policy = data.aws_iam_policy_document.apigw_cloudwatch_assume_role.json
}

resource "aws_iam_role_policy_attachment" "apigw_cloudwatch" {
  role       = aws_iam_role.apigw_cloudwatch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

resource "aws_api_gateway_account" "main" {
  cloudwatch_role_arn = aws_iam_role.apigw_cloudwatch.arn

  depends_on = [aws_iam_role_policy_attachment.apigw_cloudwatch]
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = "/aws/apigateway/${var.name_prefix}-api/${var.stage_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_api_gateway_deployment" "users" {
  rest_api_id = aws_api_gateway_rest_api.users.id

  # Redeploy whenever the rendered OpenAPI body changes - this is what picks up
  # the Task 4 switch from AWS_IAM to the Cognito authorizer.
  triggers = {
    redeployment = sha1(aws_api_gateway_rest_api.users.body)
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "prod" {
  rest_api_id          = aws_api_gateway_rest_api.users.id
  deployment_id        = aws_api_gateway_deployment.users.id
  stage_name           = var.stage_name
  xray_tracing_enabled = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn

    format = jsonencode({
      requestId          = "$context.requestId"
      ip                 = "$context.identity.sourceIp"
      requestTime        = "$context.requestTime"
      httpMethod         = "$context.httpMethod"
      resourcePath       = "$context.resourcePath"
      status             = "$context.status"
      protocol           = "$context.protocol"
      responseLength     = "$context.responseLength"
      integrationStatus  = "$context.integration.status"
      integrationLatency = "$context.integration.latency"
      authorizerError    = "$context.authorizer.error"
    })
  }

  depends_on = [aws_api_gateway_account.main]
}

# The gateway responses are declared inside the OpenAPI body above, not as
# standalone aws_api_gateway_gateway_response resources. A body change is
# imported with put_rest_api in overwrite mode, which replaces the whole API
# definition and discards any gateway response that is not part of the imported
# document - so out-of-body resources are silently wiped on the next body
# change. Keeping them in the body makes that structurally impossible.
