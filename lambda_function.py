import json
import boto3
import uuid
from datetime import datetime
from decimal import Decimal
import hashlib
import random



#This is from vs code !!!!!!

# Initialize a session using Amazon DynamoDB
dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    # Simulate bank failure 10% of the time
    # if random.random() < 0.1:
    #     log_failure('Bank not available')
    #     return {
    #         "statusCode": 503,
    #         "body": json.dumps({"message": "Bank not available"})
    #     }
        
    # Parse the incoming event body
    if 'body' in event and event['body'] is not None:
        body = json.loads(event['body'])
        merchant_name = body.get('merchant_name')
        token = body.get('merchant_token')
        bank_name = body.get('bank')
        account_num = body.get("cc_num")  # Assume account_num is a string
        account_num = str(account_num)
        amount = Decimal(body.get('amount'))
        card_type = body.get('card_type')

        # Get the current date and time
        date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Hash function for account number
        def hash_account_number(num):
            return hashlib.sha256(num.encode()).hexdigest()[:8]

        # Access DynamoDB tables
        merchant_table = dynamodb.Table('merchant')
        bank_table = dynamodb.Table('bank')
        transaction_table = dynamodb.Table('transaction')

        # Scan the merchant table to authenticate the merchant
        response = merchant_table.scan()
        items = response['Items']
        actual_token = None
        for item in items:
            if item.get('MerchantName') == merchant_name:
                actual_token = item.get('Token')
                break

        # If the provided token matches the one in the database
        if token == actual_token:
            # Retrieve the bank information
            bank_response = bank_table.get_item(
                Key={
                    'BankName': bank_name,
                    'AccountNum': Decimal(account_num)  # Convert string to Decimal
                }
            )
            bank_item = bank_response.get('Item')
            if not bank_item:
                transaction_table.put_item(
                    Item={
                        'TransactionID': str(uuid.uuid4()),
                        'MerchantName': merchant_name,
                        'MerchantID': str(uuid.uuid4()),
                        'Last4Card': account_num[-4:],
                        'HashedAccountNum': hash_account_number(account_num),
                        'Amount': amount,
                        'DateTime': date_time,
                        'Status': "Error - Bad Bank or Account Number"
                    }
                )
                return echo_back('Error - Bad Bank or Account Number.')

            if card_type == 'Credit':
                credit_limit = Decimal(bank_item.get('CreditLimit'))
                credit_used = Decimal(bank_item.get('CreditUsed'))
                new_credit_used = credit_used + amount
                if new_credit_used > credit_limit:
                    transaction_table.put_item(
                        Item={
                            'TransactionID': str(uuid.uuid4()),
                            'MerchantName': merchant_name,
                            'MerchantID': str(uuid.uuid4()),
                            'Last4Card': account_num[-4:],
                            'HashedAccountNum': hash_account_number(account_num),
                            'Amount': amount,
                            'DateTime': date_time,
                            'Status': "Declined - Insufficient Credit"
                        }
                    )
                    return echo_back('Declined. Insufficient Funds.')
                else:
                    bank_table.update_item(
                        Key={'BankName': bank_name, 'AccountNum': Decimal(account_num)},
                        UpdateExpression='SET CreditUsed = :val',
                        ExpressionAttributeValues={':val': new_credit_used}
                    )
                    transaction_table.put_item(
                        Item={
                            'TransactionID': str(uuid.uuid4()),
                            'MerchantName': merchant_name,
                            'MerchantID': str(uuid.uuid4()),
                            'Last4Card': account_num[-4:],
                            'HashedAccountNum': hash_account_number(account_num),
                            'Amount': amount,
                            'DateTime': date_time,
                            'Status': "Approved"
                        }
                    )
                    return echo_back(f'Approved! Transaction from Merchant({merchant_name}) was Approved for Bank Name({bank_name}) and Account Number({account_num}). Updated Credit Balance: {new_credit_used}')

            if card_type == 'Debit':
                balance = Decimal(bank_item.get('Balance'))
                new_balance = balance - amount
                if new_balance < 0:
                    transaction_table.put_item(
                        Item={
                            'TransactionID': str(uuid.uuid4()),
                            'MerchantName': merchant_name,
                            'MerchantID': str(uuid.uuid4()),
                            'Last4Card': account_num[-4:],
                            'HashedAccountNum': hash_account_number(account_num),
                            'Amount': amount,
                            'DateTime': date_time,
                            'Status': "Declined - Insufficient Funds"
                        }
                    )
                    return echo_back('Declined. Insufficient Funds.')
                else:
                    bank_table.update_item(
                        Key={'BankName': bank_name, 'AccountNum': Decimal(account_num)},
                        UpdateExpression='SET Balance = :val',
                        ExpressionAttributeValues={':val': new_balance}
                    )
                    transaction_table.put_item(
                        Item={
                            'TransactionID': str(uuid.uuid4()),
                            'MerchantName': merchant_name,
                            'MerchantID': str(uuid.uuid4()),
                            'Last4Card': account_num[-4:],
                            'HashedAccountNum': hash_account_number(account_num),
                            'Amount': amount,
                            'DateTime': date_time,
                            'Status': "Approved"
                        }
                    )
                    return echo_back(f'Approved! Transaction from Merchant({merchant_name}) was Approved for Bank Name({bank_name}) and Account Number({account_num}). Updated Balance: {new_balance}')
        else:
            transaction_table.put_item(
                Item={
                    'TransactionID': str(uuid.uuid4()),
                    'MerchantName': merchant_name,
                    'MerchantID': str(uuid.uuid4()),
                    'Last4Card': account_num[-4:],
                    'HashedAccountNum': hash_account_number(account_num),
                    'Amount': amount,
                    'DateTime': date_time,
                    'Status': "Access Denied - Incorrect Merchant Token"
                }
            )
            return echo_back(f"Access denied. Incorrect Merchant Token for {merchant_name}")

    return ok()

# Helper function to return a standard response for no body in event
def ok():
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/html"
        },
        "body": "No body passed"
    }

# Helper function to format and return the response
def echo_back(response, code=200):
    return {
        "statusCode": code,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({"message": response})
    }



def log_failure(message):
    transaction_table.put_item(
        Item={
            'TransactionID': str(uuid.uuid4()),
            'DateTime': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'Status': message
        }
    )