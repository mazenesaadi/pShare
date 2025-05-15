import hashlib
import os
import json
import argparse

HASH_FILE = 'hashes.json'  # JSON file to store checksums and salts

def calculate_checksum(file_path):
    sha512 = hashlib.sha512()
    with open(file_path, 'rb') as file:
        while chunk := file.read(4096):
            sha512.update(chunk)
    return sha512.hexdigest()

def store_checksum_and_salt(file_path, salt):
    checksum = calculate_checksum(file_path)

    # Try loading the existing data from hashes.json
    try:
        if os.path.exists(HASH_FILE):
            with open(HASH_FILE, 'r') as f:
                data = json.load(f)
        else:
            data = {}
    except (json.JSONDecodeError, ValueError):
        data = {}  # Reset if the JSON is corrupted

    # Store both the checksum and salt
    data[file_path] = {"checksum": checksum, "salt": salt.hex()}  # Store salt in hex format

    # Write the updated data back to the JSON file
    with open(HASH_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def load_stored_salt(file_path):
    """Retrieve the salt from hashes.json for a given file."""
    if not os.path.exists(HASH_FILE):
        return None

    # Load the hashes from JSON file
    try:
        with open(HASH_FILE, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return None

    # Check if the file salt is stored
    if file_path in data and "salt" in data[file_path]:
        return bytes.fromhex(data[file_path]["salt"])  # Convert hex string back to bytes
    return None

def load_stored_checksum(file_path):
    """Retrieve the checksum from hashes.json for a given file."""
    if not os.path.exists(HASH_FILE):
        return None

    try:
        with open(HASH_FILE, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return None

    # Check if the file checksum is stored
    if file_path in data and "checksum" in data[file_path]:
        return data[file_path]["checksum"]
    return None  # Return None if no checksum is found

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Store checksum and salt for a file.")
    parser.add_argument('filepath', type=str, help="Path to the file being checked")
    args = parser.parse_args()
    print("Checksum:", calculate_checksum(args.filepath))
