import logging
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



def update_card_description(card_id: str, added_description: str) -> bool:
    url_get = f"https://api.trello.com/1/cards/{card_id}"
    
    # Fetch the current description first
    get_data = {
        'key': TRELLO_API_KEY,
        'token': TRELLO_TOKEN,
        'fields': 'desc'  # We only want the description
    }
    response_get = requests.get(url_get, params=get_data)
    
    # Check if request was successful
    if response_get.status_code != 200:
        print(f"Failed to get current description for card {card_id}. HTTP Error: {response_get.text}")
        return False

    # Append the new data to the existing description
    current_description = response_get.json().get('desc', '')
    new_description = current_description + "\n" + added_description
    
    # Now, update the card with the new description
    url_update = f"https://api.trello.com/1/cards/{card_id}"
    update_data = {
        'key': TRELLO_API_KEY,
        'token': TRELLO_TOKEN,
        'desc': new_description
    }
    response_update = requests.put(url_update, json=update_data)
    
    if response_update.status_code != 200:
        print(f"Failed to update card {card_id}. HTTP Error: {response_update.text}")
        return False

    return True


def move_card_to_list(card_id: str, new_list_id: str) -> bool:
    """
    Moves a card to a new list on Trello using the Trello API.

    Args:
        card_id (str): The ID of the card to be moved.
        new_list_id (str): The ID of the new list where the card should be moved to.
        api_key (str): The Trello API key.
        token (str): The Trello API token.

    Returns:
        bool: True if the card was successfully moved to the new list, False otherwise.
    """

    if not card_id or not new_list_id:
      raise ValueError(f"Invalid card_id ({card_id}) or new_list_id ({new_list_id})")

    
    url = f"https://api.trello.com/1/cards/{card_id}"
    
    data = {
        'key': TRELLO_API_KEY,
        'token': TRELLO_TOKEN,
        'idList': new_list_id
    }
    
    try:
        response = requests.put(url, json=data)
        if response.status_code != 200:
            return False
        if response.json().get('idList') != new_list_id:
            return False
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to move card {card_id} to list {new_list_id}. Error: {str(e)}")
        return False
