from google.cloud import storage
import os
from google.oauth2 import service_account
import rnode
import cmd_util
import shutil
import new_enc

KEY_PATH = "google.json"
BucketName = "pshare1234"

def set_key(path:str):
    if os.path.exists(KEY_PATH):
        os.remove(KEY_PATH)
    shutil.copy2(path, KEY_PATH)

def check_key():
    return cmd_util.check_exist(KEY_PATH)

def get_credentials():
    return service_account.Credentials.from_service_account_file(KEY_PATH)
    
# Initialize the client for Google Cloud Storage
def get_storage_client():
    credentials = get_credentials()
    return storage.Client(credentials=credentials, project=credentials.project_id)

# Upload a file to Google Cloud Storage
def upload_to_gcs( source_file_name,  bucket_name=BucketName):
    # Get the storage client
    client = get_storage_client()

    #check if bucket exist
    buck_list = list_buckets()
    print(buck_list)
    if buck_list == None: create_bucket(BucketName)
    
    
    destination_blob_name = os.path.basename(source_file_name)

    # Get the bucket
    bucket = client.get_bucket(bucket_name)
    if bucket == None: create_bucket(BucketName)
    
    # Create a blob (object) in the bucket
    blob = bucket.blob(destination_blob_name)
    
    # Upload the file to GCS
    blob.upload_from_filename(source_file_name)
    print(f"File {source_file_name} uploaded to {destination_blob_name}.")

# Download a file from Google Cloud Storage 
def download_from_gcs( destination_file_name, bucket_name=BucketName):
    # Get the storage client
    client = get_storage_client()
    
    source_blob_name = os.path.basename(destination_file_name)

    # Get the bucket
    bucket = client.get_bucket(bucket_name)
    
    # Get the blob (object)
    blob = bucket.blob(source_blob_name)
    
    # Download the file
    blob.download_to_filename(destination_file_name)
    print(f"File {source_blob_name} downloaded to {destination_file_name}.")


def create_bucket(bucket_name, location="US"):
    # Get the storage client
    client = get_storage_client()
    
    # Create a new bucket
    bucket = client.bucket(bucket_name)
    
    
    
    # Create the bucket in Google Cloud Storage
    bucket = client.create_bucket(bucket)
    print(f"Bucket {bucket.name} created in {bucket.location}.")


def list_buckets():
    project_id=get_credentials().project_id
    # Set up credentials and create the storage client
    client = storage.Client(credentials=get_credentials(), project=project_id)
    
    # List all buckets in the project
    buckets = client.list_buckets()
    
    # Print the bucket names
    return buckets

def delete_file(file_name:str,bucket_name=BucketName):
    client = get_storage_client()
    bucket = client.bucket(bucket_name)
    file = bucket.blob(file_name)
    file.delete()

def get_full_name(basename:str):
    """Lists all the blobs in the bucket."""
    bucket_name = BucketName

    storage_client = get_storage_client()

    blobs = storage_client.list_blobs(bucket_name)
    
    blob_list = []
    for blob in blobs:
        if basename.split(".")[0] == blob.name.split(".")[0]:
            name_len = len(basename.split("."))
            if  name_len > 1:
                if basename.split(".")[name_len-1] == blob.name.split(".")[name_len-1]:
                    blob_list.append(blob.name)
                else: blob_list.append(blob.name)
    return blob_list

def get_file_list():
    bucket_name = BucketName

    storage_client = get_storage_client()

    blobs = storage_client.list_blobs(bucket_name)
    
    blob_list = []
    for blob in blobs:
        map_dict = new_enc.decrypt_filename(new_enc.reconstruct_chunk_name_to_file_name(blob.name))
        if map_dict != None:
            blob_list.append(map_dict["original_filename"])
        else:
            delete_file(blob.name)
    return blob_list


if __name__ == "__main__":
    # Replace with your bucket name
    # create_bucket(bucket_name)
    list_buckets()
    
    # Upload example
    source_file_name = './hashes.json'  # The local file to upload
    destination_blob_name = 'hashes.json'  # The name of the object in GCS
    upload_to_gcs(source_file_name)

    # Download example
    source_blob_name = 'hashes.json'  # The object name in GCS
    destination_file_name = 'hashes.json'  # Local path to save the file
    download_from_gcs(destination_file_name)
    delete_file(destination_blob_name)