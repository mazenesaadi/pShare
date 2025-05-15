import uuid
import json
from pathlib import Path
from typing import List, Dict, Optional, Union, Any

# Get the directory where the JSON file should be stored
BASE_DIR: Path = Path(__file__).parent
CONF_DIR: Path = BASE_DIR / 'registry_conf'
JSON_FILE: Path = CONF_DIR / 'uuids.json'

# Create registry_conf directory if it doesn't exist
CONF_DIR.mkdir(exist_ok=True)

# Type aliases
UUIDEntry = Dict[str, Union[str, List[str]]]
UUIDInfo = List[UUIDEntry]

# ==== UUID FUNCTIONS ====
def generate_uuid() -> str:
    """Generate a new UUID"""
    return uuid.uuid4().hex

def store_uuid(uuid: str) -> None:
    """Store a UUID in the JSON file with empty stored_files list.
    
    Args:
        uuid: The UUID to store
    """
    # Create registry_conf directory if it doesn't exist
    CONF_DIR.mkdir(exist_ok=True)
    
    # Use the absolute path for the JSON file
    if JSON_FILE.exists():
        with JSON_FILE.open('r') as file:
            data: UUIDInfo = json.load(file)
            if not isinstance(data, list):
                data = []
    else:
        data = []
    
    new_entry: UUIDEntry = {
        "uuid": uuid,
        "stored_files": []
    }

    data.append(new_entry)
    with JSON_FILE.open('w') as file:
        json.dump(data, file, indent=2)

def get_uuid_info() -> UUIDInfo:
    """Get information about all stored UUIDs.
    
    Returns:
        List of dictionaries containing UUID information
    """
    try:
        with JSON_FILE.open('r') as file:
            data: Any = json.load(file)
            if isinstance(data, list):
                return data
    except FileNotFoundError:
        return []
    return []

def get_uuids() -> List[str]:
    """Get a list of all stored UUIDs.
    
    Returns:
        List of UUID strings
    """
    try:
        with JSON_FILE.open('r') as file:
            data: UUIDInfo = json.load(file)
            if isinstance(data, list):
                return [entry['uuid'] for entry in data]
    except FileNotFoundError:
        return []
    return []
    
def add_file_to_uuid(uuid: str, filename: str) -> None:
    """Add a filename to a UUID's stored_files list.
    
    Args:
        uuid: The UUID to add the file to
        filename: The name of the file to add
    """
    # Create registry_conf directory if it doesn't exist
    CONF_DIR.mkdir(exist_ok=True)
    
    if not JSON_FILE.exists():
        with JSON_FILE.open('w') as file:
            json.dump([], file)
    
    with JSON_FILE.open('r') as file:
        data: UUIDInfo = json.load(file)
    
    for entry in data:
        if entry['uuid'] == uuid:
            if filename not in entry['stored_files']:
                entry['stored_files'].append(filename)
            break
    
    with JSON_FILE.open('w') as file:
        json.dump(data, file, indent=2)