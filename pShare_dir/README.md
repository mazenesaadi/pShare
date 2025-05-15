# This project was a group effort and has been moved into this publicly viewable repository
Credits to the following contributors of this project:

- https://github.com/willm13
- https://github.com/jsherwood00
- https://github.com/JamesX111



# pShare Documentation
To run pShare:
- Clone this repo
- Install dependencies with pip install -r requirement.txt
- Navigate to the pyfiles folder
- Python app.py to launch the frontend, or python snode.py --instance instancename --storage storage_in_mb to launch a storage node, with both flags optional, and defaults to the device hostname and 15 MB, respectively
- Files will be downloaded to the /downloads folder

# FUNCTION FLOW (this is the general sequence in which this program should work):

These function names are not actually what they are called in the files, they are just an abstraction. There are too many functions to individually cover and frankly do not need to be covered.
Connections are also abstracted.

However, most of the important information regarding the flow of the program is here.

`RegistryStart` - makes the host become an rNode by starting a service (mDNS) that sNodes can find
* On any new sNode initial join, if it does not provide a UUID when it joins, send the sNode a UUID
  * TODO: secure the rNode somehow, making sure only authorized computers get to join it
* Send out pings every X time to monitor status

`StorageStart` - makes the host become a sNode
* Must load config file which has its UUID, and uses that again everytime it reconnects to a rNode.

`DistributeInfo` - rNode distributes a JSON file to all sNodes containing all the other sNodes connected to the rNode

`UpdateP2PConns` - sNodes update their connections to connect to the rest of the sNodes

`UploadFile` - rNode uploads a file into the sNode network
* `GenerateChunks` - function will be called by UploadFile, and this is where erasure coding is done, the file is coded for redundancy and split
* `StoreMetadata` - keep track of where the file has gone (to what sNodes (UUIDS), checksums, etc.)
* `SendChecksum` - send checksum to the sNode so it can compare if the file has been sent successfully

`StoreFile` - sNode stores file provided by rNode
* `ValidateChecksum` - validate the file received with the provided checksum from the rNode


# encrypt.py

This python file holds the core functions to encrypt and decrypt a file. It has concurrency for decryption and encryption (we may move all of this entirely to Go)

**The encrypt, decrypt, setP, setN function are the only interface that should be called by other program**
- `Parameter Needed` : password, input file path, normal chunk number, parity chunk number


This file should be executed like this (exclude the brackets):

    python encrypt.py [-h] [-f FILEPATH] [-n NUM_CHUNKS] [-e]


- `-f`: Provide the file path
- `-n`: Specify how many chunks. Default is 3 if not provided.
- `-e`: Flag for encryption. Do not include for decryption.

## Functions within encrypt.py

### setN(i:int)
- set normal chunk number must > 1

### setP(i:int)
- set parity chunk number must > 0

### password_enc(password)
- **Returns:** Hash of the password

### encrypt_chunk(password, input_file_path, chunk_num, chunk_size)
- **Description:** Where actual encryption happens
- **Encryption Method:** AES256.GCM

### encrypt(password, input_file_path:str, chunk_num=12)
- **Description:** Initialization for encryption
  - If there is no temp directory, create one
  - Create directory named "filename_info_" to store temporary encrypted files
  - Generate chunk size by "file size / number of chunks + 1" to ensure all content is read
- **Operation:** Run `encrypt_chunk` in parallel with threading

### decrypt_chunk(password, input_file_path, chunk_num:int)
- **Description:** Where actual decryption happens

### decrypt(password, input_file_path:str, chunk_num=12)
- **Description:** Run decryption in parallel with input of a file name

### main(args)
- **Description:** Get input arguments from command line, parsed by argparse python library
- **Pre-encryption Checks:**
  - Check if the path exists
  - Check if cipher text already exists (user choice of whether they need a re-encryption)
- **Pre-decryption Checks:**
  - Check if cipher text exists





- basic encryption algorithm using pycryptodome's AES GCM mode
    - reason for not using ECB or CBC
        - ECB result in same cipher block with same plaintext block
        - CBC might result in a padding attack
    - random nonce (initial counter), and salt is generated to create randomness on each cipher text to increase security

- key is generated with the hash512 from the password
    - hash of hash of password should be stored to do a key check before decrypt (need to add)
    - is hard to find the key of 512 bit that using to encrypt cipher
    - hash of hash is hard to be attacked




# cmd_util.py

Organized function library from command line that is used in the project

## Functions within cmd_util.py:

### create_dir(file_name:str)
- **Equivalent to:** `mkdir` command
- **Description:** Create a directory with the file_name input

### remove_all(dir_name:str)
- **Equivalent to:** `rm -rf` in Linux
- **Description:** Force remove everything in the directory

### check_exist(path:str)
- **Description:** Check if the file/directory already exists
- **Returns:** `True` if exist, `False` otherwise



# checksum

This Python file is used to verify the integrity of a file after it has been encrypted, decrypted, and reassembled. It works by calculating the SHA-512 hash of the original file and the reassembled file, comparing them to ensure that the file content remains unchanged after processing. If any differences are detected, the program will notify the user.

This file should be executed like this:
python checksum.py [FILENAME]

### calculate_checksum(file_path)
- **Description:** Reads the file in chunks of 4096 bytes to generate a hash efficiently, ensuring it can handle large files without loading the entire content into memory.
- **Returns:** SHA-512 checksum of the file content.


### store_checksum(file_path)
- **Description:** Stores the original file's checksum in hashes.json before encryption. It calculates the checksum of the file and saves it with the file name as a key in the hashes.json file.

- **Operation:**
  - Checks if the hashes.json file exists.
  - Adds or updates the checksum for the provided file.
  - Creates the JSON file if it doesn’t exist.
  - Catches and handles errors if hashes.json is corrupted or invalid.

### load_stored_checksum(file_path)
- **Description:** Loads the checksum from hashes.json. If the file's checksum is not found or if the JSON file is corrupted, it will alert the user.
- **Returns:** The previously stored checksum for the provided file.


### compare_checksums(file_path)
- **Description:** Compares the current checksum of the reassembled file with the stored checksum of the original file (from hashes.json).

- **Operation:**
  - Loads the stored checksum for the file.
  - Recalculates the checksum for the reassembled file.
  - If the checksums match, the file is verified as intact; if they don’t, the program notifies the user of discrepancies.

### main(args)
- **Description:** This function handles the file path input from the command line and triggers the comparison of checksums.

- **Operation:**
  - Parses the file path provided as an argument.
  - Calls the compare_checksums() function to perform the integrity check on the reassembled file.




# erasure.py

library created for erasure coding based on reedsoloman error correction code

### padding(input_file_path:str,n_chunk_num=3)
- **Description** 
  - add padding to last chunk
- **Operation**
  - find padding size according to difference in size between last chunk and normal chunk
  - write k (padding size) (1 byte) to end of last chunk k times

### depad(input_file_path:str,n_chunk_num=3)
- **Description**
  - remove the padding from last chunk
- **Operation**
  - read last byte as padding size, if padding size > n_chunk_num, treat as no pad, but also might be a padding error ()
  - locate where pad starts
  - read pad, compare to padding size if not equal, potential padding error (should not exist)
  - if pad is correct, create temporary file store original (undecrypted data) 
  - find number of iteration needed with buffer size
  - find which iteration pad is read
  - do not read pad and write all the other to the file use fore decryption


### encode(input_file_path:str = None,n_chunk_num:int=3,p_chunk_num:int=2)
- **Description** 
  - reedsoloman encode
- **Operation**
  - read byte by byte from normal chunk
  - concatenate to generate byte string
  - reedsoloman encode on the byte string
  - locate parity byte and write them to parity chunks

### decode(input_file_path:str = None,n_chunk_num:int=3,p_chunk_num:int=2)
- **Description**
  - reedsoloman decode 
- **Operation**
  - fill the missing chunks (if there is)
  - reed byte by byte from all chunk
  - concatenate to generate byte string
  - reedsoloman decode on the byte string
  - locate normal data in the string write into decrypt file chunk

### fill_chunk(input_file_path:str,n_chunk_num=3,p_chunk_num=2)
- **Description** 
  - fill up missing chunk (reedsolo can only do error correction, not find missing chunks)
  - check if too many missing chunks
- **Operation**
  - find first exist chunk, if it is parity chunk or last chunk, definitely too many chunk loss
  - if a chunk is missing, copy another into it, as all chunks have same size
  - check how many chunks missing, if > partiy num/2 report too many chunk missing



# aws_util.py
 - description: aws cloud support

### check key
 - check if key file exist
 - key file is "key.json" at the outer most folder

### delete_file(filename)
 - delete a file with name

### upload (filename)
### download (filename)

### get_full_name()
 - if only have the base name, can try to get full name needed to be downloaded from cloud


# google_util.py
 - description: aws cloud support

### check_key()
 - check if key file exist
 - key file is "google.json" at the outer most folder

### delete_file(filename)
 - delete a file with name

### upload (filename)
### download (filename)

### get_full_name()
 - if only have the base name, can try to get full name needed to be downloaded from cloud



