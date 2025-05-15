import boto3
import json
import io
import os
import cmd_util
from boto3.s3.transfer import S3UploadFailedError
from botocore.exceptions import ClientError
import shutil
import new_enc

BucketName="pshare1234"

def set_key(access_id:str,key:str):
    dict_key = {
        "aws_access_id" : access_id,
        "aws_access_key" :key
    }
    json_obj = json.dumps(dict_key,indent=4)
    with open('key.json', 'w') as f:
        f.write(json_obj)

def get_file_list():
    s3_resource = load_s3_source()
    bucket = s3_resource.Bucket(BucketName)
    file_list=[]
    for file in bucket.objects.all():
        file_dict = new_enc.decrypt_filename(new_enc.reconstruct_chunk_name_to_file_name(file.key))
        if file_dict != None:
            file_list.append(file_dict["original_filename"])
        else: delete_file(file.key)
    return file_list

def check_key():
    return cmd_util.check_exist("key.json")

def load_s3_source():
    with open('key.json', 'r') as f:
        data = json.load(f)
    s3_resource = boto3.resource("s3",aws_access_key_id=data['aws_access_id'],aws_secret_access_key=data['aws_access_key'])
    print("Hello, Amazon S3! Let's list your buckets:")

    
    return s3_resource


def get_bucket_name():
    s3_resource=load_s3_source()
    buckets = []
    for bucket in s3_resource.buckets.all():
        buckets.append(bucket.name)
    return buckets

def check_bucket_exist(bucket_name=BucketName):
    buckets = get_bucket_name()
    if bucket_name in buckets:
        return True
    return False

def upload(file_name:str,bucket_name=BucketName):
    s3_resource = load_s3_source()
    if check_bucket_exist(BucketName)==False: 
        s3_resource.create_bucket(Bucket=BucketName)
    
    bucket = s3_resource.Bucket(bucket_name)
    file_obj = bucket.Object(os.path.basename(file_name))
    try:
        file_obj.upload_file(file_name)
        print("upload aws success")
        return 0
    except S3UploadFailedError as err:
        print(f"Couldn't upload file {file_name} to {bucket.name}.")
        print(f"\t{err}")
        return -1


def download(file_name:str,bucket_name=BucketName):
    s3_resource = load_s3_source()
    bucket = s3_resource.Bucket(bucket_name)
    dest_obj = bucket.Object(os.path.basename(file_name))
    data = io.BytesIO()
    try:
        dest_obj.download_file(dest_obj.key)
        cmd_util.move_file(dest_obj.key,file_name)
        print(f"Got your object. File: {file_name}\n")
        # print(f"\t{data.read()}")
    except ClientError as err:
        print(f"Couldn't download {dest_obj.key}.")
        print(
            f"\t{err.response['Error']['Code']}:{err.response['Error']['Message']}"
    )

def delete_file(file_name:str,bucket_name=BucketName):
    s3_resource = load_s3_source()
    bucket = s3_resource.Bucket(bucket_name)
    s3_resource.Object(bucket_name=bucket_name, key=file_name).delete()

def get_full_name(basename:str):
    """Lists all the blobs in the bucket."""
    bucket_name = BucketName
    with open('key.json', 'r') as f:
        data = json.load(f)
    s3 = boto3.client("s3",aws_access_key_id=data['aws_access_id'],aws_secret_access_key=data['aws_access_key'])
    obj = s3.list_objects_v2(Bucket=bucket_name)
    blob_list = []
    if 'Contents' not in obj:
        return blob_list
    for f in obj['Contents']:
        
        if basename.split(".")[0] == f['Key'].split(".")[1] :
            name_len =  len(basename.split("."))
            if name_len > 1:
                if basename.split(".")[name_len-1] == f['Key'].split(".")[name_len-1]:
                    blob_list.append(f['Key'])
            else: blob_list.append(f['Key'])
    return blob_list