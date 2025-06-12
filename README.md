# Gmail to S3 Lambda Processor

This project contains an AWS Lambda function written in Python that fetches emails from a Gmail account based on a specified query and stores them as JSON files in an Amazon S3 bucket.

## Features

- Authenticates with Gmail using OAuth 2.0 (with a refresh token).
- Fetches emails based on a user-provided Gmail search query.
- Stores each email as a separate JSON file in S3.
- Organizes emails in S3 under `gmail/GMAIL_USER_ID_S3_FOLDER/message_MESSAGE_ID.json`.
- Configurable via Lambda environment variables.

## Project Structure

```
.
├── lambda_function.py      # The main Lambda function code
├── requirements.txt        # Python dependencies
├── credentials.json        # (Locally) Google OAuth client credentials - DO NOT COMMIT
├── token.json              # (Locally) Google OAuth tokens (contains refresh_token) - DO NOT COMMIT
└── README.md               # This documentation file
```

## Setup Instructions

### 1. Prerequisites

- Python 3.9+ installed locally.
- An AWS account with permissions to create Lambda functions, IAM roles, and S3 buckets.
- A Google Cloud Platform (GCP) project.

### 2. Configure Google Cloud Project & Gmail API

1.  **Go to the Google Cloud Console:** [https://console.cloud.google.com/](https://console.cloud.google.com/)
2.  **Create a new project** or select an existing one.
3.  **Enable the Gmail API:**
    -   Navigation menu > "APIs & Services" > "Library".
    -   Search for "Gmail API", select it, and click "ENABLE".
4.  **Create OAuth 2.0 Credentials:**
    -   Navigation menu > "APIs & Services" > "Credentials".
    -   Click "CREATE CREDENTIALS" > "OAuth client ID".
    -   **Application type:** Select "Desktop app".
    -   **Name:** (e.g., "Gmail S3 Lambda Client").
    -   Click "CREATE".
    -   Download the JSON file and save it as `credentials.json` in your project root directory. **Do not commit this file to version control.**
5.  **Configure OAuth Consent Screen:**
    -   Navigation menu > "APIs & Services" > "OAuth consent screen".
    -   **User Type:** Choose "External" (unless you have a Google Workspace account and want it internal).
    -   Fill in the required app information (app name, user support email, developer contact).
    -   **Scopes:** Add the `.../auth/gmail.readonly` scope.
    -   **Test users:** Add the Gmail account(s) you'll be accessing if your app is in "testing" publishing status. If "In production", this might not be needed for all users.

### 3. Generate `token.json` (Locally)

This step generates the `refresh_token` needed for the Lambda to run without manual intervention.

1.  **Clone this repository (if applicable) or ensure `lambda_function.py` and `requirements.txt` are in your project directory.**
2.  **Place `credentials.json`** (downloaded in the previous step) in the root of your project directory.
3.  **Install local dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Run the token generation script:**
    ```bash
    python lambda_function.py
    ```
    - This will likely open a browser window asking you to log in to your Google account and authorize the application.
    - After authorization, a `token.json` file will be created in your project root. This file contains your `refresh_token`. **Do not commit `token.json` to version control.**
5.  **Note down the `refresh_token`** from `token.json`, and the `client_id` and `client_secret` from `credentials.json`. You'll need these for the Lambda environment variables.

### 4. Deploy to AWS Lambda

1.  **Package the Lambda function:**
    -   Create a deployment package (ZIP file) containing `lambda_function.py` and its dependencies from `requirements.txt`.
    -   One way to do this:
        ```bash
        mkdir lambda_package
        cp lambda_function.py lambda_package/
        pip install -r requirements.txt -t ./lambda_package/
        cd lambda_package
        zip -r ../lambda_function.zip .
        cd ..
        ```
    -   The `lambda_function.zip` will be created in your project root.

2.  **Create S3 Bucket:**
    -   In the AWS S3 console, create a new S3 bucket.
    -   Ensure it's in the same region as your Lambda.
    -   Keep "Block all public access" enabled.
    -   Note the bucket name.

3.  **Create Lambda Function:**
    -   In the AWS Lambda console, click "Create function".
    -   **Function name:** e.g., `GmailToS3Processor`.
    -   **Runtime:** Python 3.9 (or newer).
    -   **Permissions:** "Create a new role with basic Lambda permissions".
    -   Upload the `lambda_function.zip` file.
    -   **Handler:** Set to `lambda_function.lambda_handler`.

4.  **Configure Lambda:**
    -   **Environment Variables:**
        -   `S3_BUCKET_NAME`: Your S3 bucket name.
        -   `GMAIL_USER_ID`: `me` (to use the authenticated user).
        -   `REFRESH_TOKEN`: The `refresh_token` from `token.json`.
        -   `CLIENT_ID`: The `client_id` from `credentials.json`.
        -   `CLIENT_SECRET`: The `client_secret` from `credentials.json`.
    -   **Basic Settings:**
        -   Adjust Memory (e.g., 256MB) and Timeout (e.g., 5 minutes) as needed.
    -   **IAM Role Permissions:**
        -   Navigate to the IAM role created for the Lambda.
        -   Attach a policy to allow S3 PutObject access to your specific bucket:
            ```json
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "s3:PutObject",
                        "Resource": "arn:aws:s3:::YOUR_S3_BUCKET_NAME/gmail/*"
                    }
                ]
            }
            ```
            (Replace `YOUR_S3_BUCKET_NAME`).
        -   Ensure it also has `AWSLambdaBasicExecutionRole` policy for CloudWatch logging.

### 5. Testing

1.  In the Lambda console, configure a test event in the "Test" tab:
    ```json
    {
      "gmail_query": "in:inbox is:unread newer_than:1d",
      "gmail_user_id_s3_folder": "your_user_id_for_s3_path"
    }
    ```
    - Replace `gmail_query` with a valid Gmail search query.
    - Replace `your_user_id_for_s3_path` with a string to be used as a subfolder in S3 (e.g., `john_doe_gmail_com`).
2.  Run the test and check CloudWatch Logs for output and errors.
3.  Verify that JSON files appear in your S3 bucket under `gmail/your_user_id_for_s3_path/`.

### 6. Set up a Trigger (Optional)

-   To run the Lambda on a schedule, add an **EventBridge (CloudWatch Events)** trigger.
-   Configure the schedule (e.g., `cron(0 2 * * ? *)` for daily at 2 AM UTC).
-   Provide the same JSON input structure for the "Constant (JSON text)" target input.

## Security Notes

-   **NEVER commit `credentials.json` or `token.json` to version control.** Add them to your `.gitignore` file.
-   The `REFRESH_TOKEN`, `CLIENT_ID`, and `CLIENT_SECRET` environment variables in Lambda should be treated as sensitive data. Consider using AWS Secrets Manager for storing these and have the Lambda fetch them at runtime for enhanced security.
-   Ensure your S3 bucket remains private and accessible only by the Lambda IAM role.

## `lambda_function.py` Overview

-   `get_gmail_service()`: Handles authentication with Google using the refresh token.
-   `list_messages()`: Lists email IDs matching the query.
-   `get_message_detail()`: Fetches the full content of an email.
-   `upload_to_s3()`: Uploads the email data as JSON to S3.
-   `lambda_handler()`: Main entry point, orchestrates the process.
-   `generate_token_locally()`: (within `if __name__ == '__main__':`) Helper to run locally for initial token generation. Not used by Lambda directly.
