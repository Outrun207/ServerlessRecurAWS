import hmac
import hashlib
import time
import base64
import requests
import os
import boto3
from requests.auth import AuthBase

#setup keys 
api_key = os.environ['API_KEY']
secret_key = os.environ['SECRET_KEY']
passphrase = os.environ['PASSPHRASE']

#how much crypto to buy
buyAmount = os.environ['BUY_AMOUNT'] #$env:BUY_AMOUNT=100
#which currency to buy crypto with 
currency = os.environ['CURRENCY'] #$env:CURRENCY='USD'
#which crypto to buy 
cryptoToBuy = os.environ['CRYPTO_TO_BUY'] #$env:CRYPTO_TO_BUY='BTC-USD'

runtime_region = os.environ['AWS_REGION']

api_url = 'https://api-public.sandbox.pro.coinbase.com/'

#sign the message and setup auth
class CoinbaseExchangeAuth(AuthBase):
    # Provided by CBPro: https://docs.pro.coinbase.com/#signing-a-message
    def __init__(self, api_key, secret_key, passphrase):
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

    def __call__(self, request):
        timestamp = str(time.time())
        message = timestamp + request.method + request.path_url
        message = message.encode('utf-8')
        if request.body:
            message = message + request.body
        hmac_key = base64.b64decode(self.secret_key)
        signature = hmac.new(hmac_key, message, hashlib.sha256)
        signature_b64 = base64.b64encode(signature.digest()).decode('utf-8')

        request.headers.update({
            'CB-ACCESS-SIGN': signature_b64,
            'CB-ACCESS-TIMESTAMP': timestamp,
            'CB-ACCESS-KEY': self.api_key,
            'CB-ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        })
        return request
auth = CoinbaseExchangeAuth(api_key, secret_key, passphrase)

#send returned messages or errors to SNS 
def sendUpdate(alert):
  client = boto3.client('sns')
  response = client.publish(
  TopicArn = ('arn:aws:sns:' + runtime_region + ':' + aws_account_id + ':' + 'CoinbaseProAutoBuyAlerts'),
  Message = str(alert),
  Subject = 'AWS Serverles Recur Alerts'
  )

#get payment account
def getPaymentMethod():
    #get the id of the payment method linked to coinbase
    r = requests.get(api_url + 'payment-methods', auth=auth)
    for paymentMethod in r.json():
      try: 
        if paymentMethod['primary_buy'] == True:
          return paymentMethod['id']
      except: 
        sendUpdate("could not locate primary payment method")

#deposit funds into the account
def depositFunds():
    try:
      deposit = {
        "amount": buyAmount,
        "currency": currency,
        "payment_method_id": getPaymentMethod()
      }
      r = requests.post(api_url + 'deposits/payment-method', json=deposit, auth=auth)
      sendUpdate(r.json())
    except: 
      sendUpdate("could not deposit funds" + r.json())

#make sure there is enough available funds for the buy
def checkFunds():
    r = requests.get(api_url + 'accounts', auth=auth)
    print(r.json())
    for account in r.json():
      if account['currency'] == currency:
        if float(account['balance']) < int(buyAmount):
          depositFunds()
        else:
          return

# Place a market order
def order():
    checkFunds()
    order = {
        'type': 'market',
        'funds': buyAmount,
        'side': 'buy',
        'product_id': cryptoToBuy
    }
    r = requests.post(api_url + 'orders', json=order, auth=auth)
    sendUpdate(r.json())

def lambda_handler(event, context):
  global aws_account_id
  aws_account_id = context.invoked_function_arn.split(":")[4]
  order()
  return {
      "statusCode": 200,
      "headers": {
          "Content-Type": "application/json"
     }
  }