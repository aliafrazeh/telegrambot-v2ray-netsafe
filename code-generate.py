# code-generate.py (Corrected Version)
from cryptography.fernet import Fernet

# Generate a key (which is in bytes)
key_in_bytes = Fernet.generate_key()

# Decode it to a simple string for easy copy-pasting
key_as_string = key_in_bytes.decode('utf-8')

# Print only the clean string
print(key_as_string)