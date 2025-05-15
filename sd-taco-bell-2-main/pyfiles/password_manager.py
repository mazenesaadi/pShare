import hashlib
import os
import binascii
from checksum import load_stored_salt  # Import the function to retrieve the salt
from checksum import store_checksum_and_salt

PASSWORD_FILE = "password_hash.txt"

class PasswordManager:
    def __init__(self):
        self.master_password = None  # Stores hashed password in memory

    def set_password(self, password: str):
        """Hash and store the user's password."""
        hashed_pw = hashlib.sha256(password).hexdigest()
        self.master_password = hashed_pw
        with open(PASSWORD_FILE, "w") as f:
            f.write(hashed_pw)
        print("Password set and saved.")

    def load_password(self):
        """Load the stored password hash from file or prompt user for a new one if missing."""
        if os.path.exists(PASSWORD_FILE):
            with open(PASSWORD_FILE, "r") as f:
                stored_hash = f.read().strip()
                if stored_hash:  # Ensure the file is not empty
                    self.master_password = stored_hash
                else:
                    print("Warning: Password file is empty. Resetting.")
                    os.remove(PASSWORD_FILE)

    def verify_password(self, password: str) -> bool:
        """Check if entered password matches stored hash."""
        if self.master_password is None:
            print("No stored password found.")
            return False
        return hashlib.sha256(password.encode()).hexdigest() == self.master_password

    def clear_password(self):
        """Manually erase the master password from memory and storage."""
        self.master_password = None
        if os.path.exists(PASSWORD_FILE):
            os.remove(PASSWORD_FILE)
        print("Password has been cleared.")

    def derive_key(self, file_path: str, salt_size=16):
        """Generate a unique encryption key for each file using the master password + stored salt."""
        if self.master_password is None:
            raise ValueError("Master password is not set")

        # Retrieve salt from hashes.json
        salt = load_stored_salt(file_path)

        # If no salt is found, generate a new one and store it
        if salt is None:
            print(f"Warning: No salt found for {file_path}. Generating a new one.")
            salt = os.urandom(salt_size)
            store_checksum_and_salt(file_path, salt)  # Store the newly generated salt

        print(f"Using stored salt for {file_path}: {binascii.hexlify(salt)}")

        key = hashlib.pbkdf2_hmac('sha256', self.master_password.encode(), salt, 100000, 32)

        return key, salt


# Initialize password manager at import
password_manager = PasswordManager()
password_manager.load_password()  # Load password at startup
