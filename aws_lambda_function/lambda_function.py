import json
import openai
import boto3
import requests
import pandas

def lambda_handler(event, context):
    # TODO: Implement your Lambda function logic here

    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }
