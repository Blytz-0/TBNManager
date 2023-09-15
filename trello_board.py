import requests
import os
from dotenv import load_dotenv

load_dotenv()
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_TOKEN = os.getenv("TRELLO_TOKEN")

url = "https://api.trello.com/1/members/me/boards"

query = {
    'key': TRELLO_API_KEY,
    'token': TRELLO_TOKEN
}

response = requests.get(url, params=query)  # Use a GET request directly

print("Response status code:", response.status_code)
print("Response text:", response.text)  # Print this immediately after request

# Now, if the status code is 200 (indicating success), then you can attempt to decode the JSON
if response.status_code == 200:
    boards = response.json()
    for board in boards:
        print(f"Board Name: {board['name']}, Board ID: {board['id']}")

    # If you're looking for a specific board ID, say "Staff Management", you can also do:
    for board in boards:
        if board['name'] == "Strike System Board":
            print(f"Board ID for 'Staff Management' is: {board['id']}")
