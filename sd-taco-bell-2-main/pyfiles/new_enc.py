import os
import json
import random
import string
import base64
import shutil
from cryptography.fernet import Fernet
from pathlib import Path

# directory definitions
REGISTRY_DIR = "registry_conf"
MAPPING_FILE = os.path.join(REGISTRY_DIR, "file_mappings", "key_name_mappings.json")
DOWNLOADS_DIR = os.path.join(REGISTRY_DIR, "downloads")


def reconstruct_chunk_name_to_file_name(chunk_name:str):
    comp_list = chunk_name.split(".")
    original_name = ""
    len_list = len(comp_list)
    if  len_list > 2:
        len_list -= 1
    for i in range(len_list):
        if i != 0:
            original_name += f".{comp_list[i]}"
        else: original_name += comp_list[i]
    return original_name


def setup_registry_directories():
    """Create the registry_conf directory structure"""
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

def generate_random_filename(length=10):
    # Randomize file name
    valid_chars = string.ascii_letters + string.digits
    return ''.join(random.choice(valid_chars) for _ in range(length))

def generate_random_key():
    # Standard key generation, this is secure
    return Fernet.generate_key().decode()


def decrypt_filename(file_name):
    """ Provided an encrypted file name, returns the decrypted version """
    try:
        with open(MAPPING_FILE, 'r') as f:
            map_filename = json.load(f)

        return map_filename[file_name]
    except Exception as e:
        print(e)

def encrypt_filename(file_name):
    """ Provided a plaintext file name, returns the encrypted version """
    try:
        with open(MAPPING_FILE, 'r') as f:
            map_filename = json.load(f)
        
        for k, v in map_filename.items(): # encryptname: {dic with "original_filename" and "key"}
            if v["original_filename"] == file_name:
                return k
        
        return None

    except Exception as e:
        print(e)

def update_key_mapping(encrypted_filename, original_filename, key):
    """Map file to original file name + key"""
    if os.path.exists(MAPPING_FILE):
        with open(MAPPING_FILE, 'r') as f:
            try:
                mappings = json.load(f)
            except json.JSONDecodeError:
                mappings = {}
    else:
        mappings = {}
    
    # Store mapping
    mappings[encrypted_filename] = {
        "original_filename": original_filename,
        "key": key
    }
    
    # Write mapping
    with open(MAPPING_FILE, 'w') as f:
        json.dump(mappings, f, indent=4)


def encrypt_file(input_file):
    """Encrypt a file with a random key and save it with a random name in the registry_conf directory so it can be chained with upload and erasure coding function"""
    random_filename = generate_random_filename(10) + '.enc'
    encrypted_path = os.path.join(REGISTRY_DIR, random_filename)
    
    key = generate_random_key()
        
    cipher = Fernet(key.encode())
    
    try:
        with open(input_file, 'rb') as f:
            file_data = f.read()
        
        encrypted_data = cipher.encrypt(file_data)
        
        original_filename = os.path.basename(input_file)
        
        with open(encrypted_path, 'wb') as f:
            f.write(encrypted_data)
        
        update_key_mapping(random_filename, original_filename, key)
        
    except Exception as e:
        print(f"Error encrypting file: {e}")
    
    return random_filename


def decrypt_file(encrypted_file_name):

    try:
        if not os.path.exists(MAPPING_FILE):
            print(f"Mapping file {MAPPING_FILE} not found. Cannot decrypt.")
            return
        
        with open(MAPPING_FILE, 'r') as f:
            mappings = json.load(f)
        
        if encrypted_file_name not in mappings:
            print(f"No mapping found for {encrypted_file_name}. Cannot decrypt.")
            return
        
        encrypted_file_path = os.path.join("downloaded_files", encrypted_file_name)
        
        if not os.path.exists(encrypted_file_path):
            print(f"Encrypted file {encrypted_file_path} not found.")
            return
        
        file_info = mappings[encrypted_file_name]
        original_filename = file_info["original_filename"]
        key = file_info["key"]
        
        cipher = Fernet(key.encode())
        
        with open(encrypted_file_path, 'rb') as f:
            encrypted_data = f.read()
        
        decrypted_data = cipher.decrypt(encrypted_data)
        
        output_path = os.path.join(DOWNLOADS_DIR, original_filename)
        
        with open(output_path, 'wb') as f:
            f.write(decrypted_data)
        
        print(f"File decrypted successfully.")
        print(f"Saved to: {output_path}")
        
    except Exception as e:
        print(f"Error decrypting file: {e}")

def list_encrypted_files():
    """List all encrypted file data from the mapping file and return as dictionary."""
    result = {}
    
    if not os.path.exists(MAPPING_FILE):
        return result
    
    try:
        with open(MAPPING_FILE, 'r') as f:
            mappings = json.load(f)
        
        if not mappings:
            return result
        
        for encrypted_file, info in mappings.items():
            encrypted_path = os.path.join(REGISTRY_DIR, encrypted_file)
            file_exists = os.path.exists(encrypted_path)
            
            result[encrypted_file] = {
                "path": encrypted_path,
                "original_filename": info['original_filename'],
                "file_exists": file_exists
            }
            
        return result
            
    except Exception as e:
        print(f"Error listing encrypted files: {e}")
        return result