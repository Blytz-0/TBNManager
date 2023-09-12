import os
import requests
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

TRELLO_API_KEY = os.getenv('TRELLO_API_KEY')
TRELLO_TOKEN = os.getenv('TRELLO_TOKEN')
TRELLO_LIST_ID = os.getenv('TRELLO_LIST_ID')
TRELLO_BOARD_ID = os.getenv("TRELLO_BOARD_ID")

def get_label_id_by_color(board_id: str, color: str) -> Optional[str]:
    url = f"https://api.trello.com/1/boards/{board_id}/labels"
    
    query = {
        'key': TRELLO_API_KEY,
        'token': TRELLO_TOKEN
    }

    response = requests.get(url, params=query)
    response.raise_for_status()

    labels = response.json()
    for label in labels:
        if label.get('color') == color:
            return label.get('id')

    return None

def add_strike_to_trello(player_name: str, in_game_id: str, admin_name: str, rule_breach: str, color_label: Optional[str] = None) -> bool:
    card_name = f"{player_name} | {in_game_id}"
    card_desc = f"Admin: {admin_name}\nRule break - {rule_breach}"
    url = f"https://api.trello.com/1/cards"
    
    data = {
        "name": card_name,
        "desc": card_desc,
        "idList": TRELLO_LIST_ID,
        'key': TRELLO_API_KEY,
        'token': TRELLO_TOKEN
    }

    if color_label:
        label_id = get_label_id_by_color(TRELLO_BOARD_ID, color_label)
        if label_id:
            data['idLabels'] = [label_id]

    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        return True
    except requests.HTTPError:
        print(f"Failed to add card for {card_name}. HTTP Error: {response.text}")
        return False


def search_for_card(in_game_id: str) -> Optional[dict]:
    url = f"https://api.trello.com/1/boards/{TRELLO_BOARD_ID}/cards"
    
    query = {
        'key': TRELLO_API_KEY,
        'token': TRELLO_TOKEN
    }

    response = requests.get(url, params=query)
    
    # Handling potential HTTP errors first
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"HTTP error occurred: {err}")
        # Handle the exception or exit the script
        exit()

    
    cards = response.json()

    # Print each card's name
    for card in cards:
        print(card.get('name'))

    # Return the card that matches the in_game_id
    return next((card for card in cards if in_game_id in card.get('name')), None)



def update_card_description(card_id: str, new_description: str) -> bool:
    url = f"https://api.trello.com/1/cards/{card_id}"
    
    data = {
        'key': TRELLO_API_KEY,
        'token': TRELLO_TOKEN,
        'desc': new_description
    }

    response = requests.put(url, json=data)
    response.raise_for_status()

    return True

def move_card_to_list(card_id: str, new_list_id: str) -> bool:
    url = f"https://api.trello.com/1/cards/{card_id}"
    
    data = {
        'key': TRELLO_API_KEY,
        'token': TRELLO_TOKEN,
        'idList': new_list_id
    }

    response = requests.put(url, json=data)
    response.raise_for_status()

    return True

print(f"Trello API Key: {TRELLO_API_KEY}")
print(f"Trello Token: {TRELLO_TOKEN}")
print(f"Trello List ID: {TRELLO_LIST_ID}")
print(f"Trello Board ID: {TRELLO_BOARD_ID}")