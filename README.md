# suresh-agentic-ai
Agentic AI project repository

## AWS Lambda Function Template

This repository contains a template for an AWS Lambda function located in the `aws_lambda_function` directory.

### Structure

-   `aws_lambda_function/`: Main directory for the Lambda function code.
    -   `lambda_function.py`: The main handler file for the Lambda function.
    -   `requirements.txt`: Lists the Python dependencies for the function.

### Dependencies

The template is pre-configured with the following Python libraries:

-   openai
-   boto3
-   requests
-   json
-   pandas

### Usage

1.  **Implement your logic:** Open `aws_lambda_function/lambda_function.py` and add your custom code within the `lambda_handler` function where the `# TODO:` comment is placed.
2.  **Package for deployment:**
    *   Install dependencies locally: `pip install -r aws_lambda_function/requirements.txt -t aws_lambda_function/package/`
    *   Create a zip file: `cd aws_lambda_function/package && zip -r ../deployment_package.zip . && cd .. && zip -g deployment_package.zip lambda_function.py`
    *   Alternatively, use AWS SAM CLI or Serverless Framework for more advanced deployment and packaging.
3.  **Deploy to AWS Lambda:** Upload the `deployment_package.zip` (or `aws_lambda_function/deployment_package.zip` if you ran the zip command from the root) to your AWS Lambda function via the AWS Management Console, AWS CLI, or an infrastructure-as-code tool.
