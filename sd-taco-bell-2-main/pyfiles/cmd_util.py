import subprocess
import os
import shutil

def create_dir(file_name:str):
    os.mkdir(file_name)

def remove_all(dir_name:str):
    shutil.rmtree(dir_name)

def check_exist(path:str):
    return os.path.exists(path)

def move(origin:str,destination:str):
    shutil.move(origin,destination)

    