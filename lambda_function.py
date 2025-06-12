import os
import json
import base64
import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow # For local token generation
import boto3

# --- Configuration ---
# These will ideally be set as environment variables in Lambda
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'your-s3-bucket-name')
GMAIL_USER_ID = os.environ.get('GMAIL_USER_ID', 'me') # 'me' refers to the authenticated user
REFRESH_TOKEN = os.environ.get('REFRESH_TOKEN') # Store this securely!
CLIENT_ID = os.environ.get('CLIENT_ID') # From credentials.json
CLIENT_SECRET = os.environ.get('CLIENT_SECRET') # From credentials.json
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
TOKEN_FILE_PATH = '/tmp/token.json' # Writable path in Lambda

s3_client = boto3.client('s3')

def get_gmail_service():
    """Authenticates and returns a Gmail API service client."""
    creds = None

    # Construct credentials from environment variables
    if REFRESH_TOKEN and CLIENT_ID and CLIENT_SECRET:
        creds_data = {
            "token": None, # Access token will be fetched using refresh_token
            "refresh_token": REFRESH_TOKEN,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scopes": SCOPES
        }
        creds = Credentials.from_authorized_user_info(creds_data, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("Refreshing access token...")
                creds.refresh(Request())
                # Persist the new token info if needed (though for Lambda, refreshing per invocation is fine)
            except Exception as e:
                print(f"Error refreshing access token: {e}")
                # If refresh fails, we might need to re-authenticate, which is not possible in Lambda directly.
                # This indicates an issue with the REFRESH_TOKEN or client credentials.
                raise Exception("Failed to refresh Gmail token. Check REFRESH_TOKEN and credentials.")
        else:
            # This block should ideally not be hit in Lambda if REFRESH_TOKEN is provided and valid.
            # It's more for local execution or initial setup.
            # For Lambda, ensure REFRESH_TOKEN, CLIENT_ID, and CLIENT_SECRET are correctly set.
            print("Missing valid credentials or refresh token. Please ensure REFRESH_TOKEN, CLIENT_ID, and CLIENT_SECRET are set in environment variables.")
            raise Exception("Gmail authentication failed. Missing credentials.")

    service = build('gmail', 'v1', credentials=creds)
    return service

def list_messages(service, user_id, query=''):
    """Lists messages in the user's mailbox matching the query."""
    try:
        response = service.users().messages().list(userId=user_id, q=query).execute()
        messages = []
        if 'messages' in response:
            messages.extend(response['messages'])
        # Handle pagination if there are many messages
        while 'nextPageToken' in response:
            page_token = response['nextPageToken']
            response = service.users().messages().list(userId=user_id, q=query, pageToken=page_token).execute()
            if 'messages' in response:
                messages.extend(response['messages'])
        print(f"Found {len(messages)} messages for query: '{query}'")
        return messages
    except Exception as e:
        print(f"Error listing messages: {e}")
        raise

def get_message_detail(service, user_id, message_id):
    """Gets the full details of a specific message."""
    try:
        # Requesting 'full' format to get headers, body, etc.
        # You can use 'raw' to get the raw RFC 2822 message and parse it yourself
        # or 'metadata' for just headers.
        message = service.users().messages().get(userId=user_id, id=message_id, format='full').execute()
        return message
    except Exception as e:
        print(f"Error getting message detail for ID {message_id}: {e}")
        raise

def upload_to_s3(bucket_name, gmail_user_id_folder, message_id, message_data):
    """Uploads message data to S3 as a JSON file."""
    file_key = f"gmail/{gmail_user_id_folder}/message_{message_id}.json"
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=file_key,
            Body=json.dumps(message_data, indent=4),
            ContentType='application/json'
        )
        print(f"Successfully uploaded message {message_id} to S3: s3://{bucket_name}/{file_key}")
    except Exception as e:
        print(f"Error uploading message {message_id} to S3: {e}")
        raise

def lambda_handler(event, context):
    """
    Main Lambda handler function.
    Expected event format (example):
    {
        "gmail_query": "in:inbox is:unread newer_than:7d",
        "gmail_user_id_s3_folder": "user_xyz_gmail_com" // The part of the email before @, sanitized for S3 path
    }
    """
    print(f"Received event: {json.dumps(event)}")

    gmail_query = event.get('gmail_query')
    gmail_user_id_s3_folder = event.get('gmail_user_id_s3_folder') # e.g., 'xyz' from 'xyz@gmail.com'

    if not gmail_query:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'gmail_query not provided in event'})
        }
    if not gmail_user_id_s3_folder:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'gmail_user_id_s3_folder not provided in event'})
        }

    if not REFRESH_TOKEN or not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: Missing one or more required environment variables: REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Lambda configuration error: Missing Gmail auth environment variables.'})
        }

    processed_messages = 0
    failed_messages = 0

    try:
        print("Attempting to get Gmail service...")
        service = get_gmail_service()
        print("Gmail service obtained successfully.")

        print(f"Listing messages for user '{GMAIL_USER_ID}' with query: '{gmail_query}'")
        messages = list_messages(service, GMAIL_USER_ID, query=gmail_query)

        if not messages:
            print("No messages found matching the query.")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'No messages found matching the query.', 'processed_messages': 0})
            }

        for msg_summary in messages:
            msg_id = msg_summary['id']
            try:
                print(f"Fetching details for message ID: {msg_id}")
                message_detail = get_message_detail(service, GMAIL_USER_ID, msg_id)

                # We can simplify the data stored or store the whole object
                # For now, storing the important parts.
                # The actual email body might be in message_detail['payload']['parts']
                # and might need decoding from base64.

                # Basic structure for storage
                email_data_to_store = {
                    'id': message_detail.get('id'),
                    'threadId': message_detail.get('threadId'),
                    'labelIds': message_detail.get('labelIds'),
                    'snippet': message_detail.get('snippet'),
                    'historyId': message_detail.get('historyId'),
                    'internalDate': message_detail.get('internalDate'),
                    'payload': {
                        'headers': message_detail.get('payload', {}).get('headers'),
                        # Add more payload details if needed, e.g., body, parts
                    },
                    'sizeEstimate': message_detail.get('sizeEstimate')
                }

                # A more robust way to extract body:
                body_data = ""
                if 'payload' in message_detail:
                    payload = message_detail['payload']
                    if 'parts' in payload:
                        for part in payload['parts']:
                            if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                                body_data = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                                break
                            elif part['mimeType'] == 'text/html' and 'data' in part['body'] and not body_data: # fallback to html if no plain text
                                # Potentially decode HTML or store as is
                                body_data = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    elif 'body' in payload and 'data' in payload['body']: # For non-multipart messages
                         body_data = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

                email_data_to_store['payload']['decoded_body_plain_or_html'] = body_data

                print(f"Uploading message {msg_id} to S3 bucket {S3_BUCKET_NAME}...")
                upload_to_s3(S3_BUCKET_NAME, gmail_user_id_s3_folder, msg_id, email_data_to_store)
                processed_messages += 1
            except Exception as e:
                print(f"Failed to process or upload message ID {msg_id}: {e}")
                failed_messages +=1
                # Continue processing other messages

        summary_message = f"Processing complete. Processed: {processed_messages}, Failed: {failed_messages}."
        print(summary_message)
        return {
            'statusCode': 200,
            'body': json.dumps({'message': summary_message, 'processed_messages': processed_messages, 'failed_messages': failed_messages})
        }

    except Exception as e:
        print(f"Error in lambda_handler: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

# --- Helper for local token generation (NOT FOR LAMBDA DIRECTLY) ---
def generate_token_locally(credentials_file_path='credentials.json', token_output_path='token.json'):
    """
    Runs the OAuth flow locally to generate a token.json file with a refresh_token.
    The 'credentials.json' should be downloaded from Google Cloud Console.
    The resulting 'token.json' (specifically the refresh_token within it)
    will be used by the Lambda function.
    """
    flow = InstalledAppFlow.from_client_secrets_file(credentials_file_path, SCOPES)
    # The user will be directed to their browser to authorize the application.
    # For server environments without a browser, consider other OAuth flows if needed,
    # but for this setup, generating token.json locally first is standard.
    creds = flow.run_local_server(port=0) # port=0 finds an available port

    # Save the credentials for the next run
    token_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }
    with open(token_output_path, 'w') as token_file:
        json.dump(token_data, token_file)
    print(f"Token data saved to {token_output_path}")
    print(f"IMPORTANT: Securely store the 'refresh_token' from this file. You will need it for the Lambda environment variable.")

if __name__ == '__main__':
    # This section is for local testing or to generate the initial token.json
    # Make sure 'credentials.json' is in the same directory or provide the correct path.
    print("Running local token generation utility...")
    print("You will be prompted to authorize access to your Gmail account via a web browser.")

    # Check if credentials.json exists
    if not os.path.exists('credentials.json'):
        print("\nERROR: 'credentials.json' not found in the current directory.")
        print("Please download it from your Google Cloud Console OAuth 2.0 Client ID settings and place it here.")
        print("Refer to Step 1 of the plan (Set up Gmail API access).")
    else:
        # Example of how to run the local token generation:
        generate_token_locally()
        print("\n--- Instructions for Lambda ---")
        print(f"1. Open the generated 'token.json' file.")
        print(f"2. Copy the value of 'refresh_token'.")
        print(f"3. In your Lambda function's environment variables, set:")
        print(f"   - REFRESH_TOKEN = <the copied refresh_token>")
        print(f"   - CLIENT_ID = <your client_id from credentials.json>")
        print(f"   - CLIENT_SECRET = <your client_secret from credentials.json>")
        print(f"   - S3_BUCKET_NAME = <your target S3 bucket name>")
        print(f"   - GMAIL_USER_ID = 'me' (or the specific Gmail user ID if not 'me')")

        # Example of how to simulate a Lambda call locally (after setting up token.json and env vars)
        # print("\n--- Simulating Lambda call (for local testing after token generation) ---")
        # mock_event = {
        #     "gmail_query": "in:inbox is:unread newer_than:1d", # Example query
        #     "gmail_user_id_s3_folder": "test_user_gmail_com"
        # }
        # print(f"Simulating event: {mock_event}")
        # # For local simulation, you'd need to set environment variables for
        # # REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET, S3_BUCKET_NAME.
        # # os.environ['REFRESH_TOKEN'] = "your_actual_refresh_token_from_token.json"
        # # os.environ['CLIENT_ID'] = "your_client_id"
        # # os.environ['CLIENT_SECRET'] = "your_client_secret"
        # # os.environ['S3_BUCKET_NAME'] = "your-s3-bucket"
        # # if os.environ.get('REFRESH_TOKEN') and os.environ.get('CLIENT_ID') and os.environ.get('CLIENT_SECRET') and os.environ.get('S3_BUCKET_NAME'):
        # #     lambda_handler(mock_event, None)
        # # else:
        # #     print("Skipping local Lambda simulation as environment variables for auth are not set.")
