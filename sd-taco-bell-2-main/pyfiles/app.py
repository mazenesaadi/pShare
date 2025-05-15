from flask import Flask, render_template, request, redirect, url_for, session
from pshare import *

from werkzeug.utils import secure_filename
import os
import glob

import google_util
import aws_util
import pathlib


cur_rnode = None

path = os.getcwd() 
parent = os.path.join(path, os.pardir) 
template_location = os.path.abspath(parent) + "/templates"

app = Flask(__name__, template_folder=template_location)
app.secret_key = "1234" # TODO: does this need to be implemented?

@app.route('/')
def home():
    """ Return the list of files the user has stored on SNODES, if applicable """
    files_to_storage, files_to_availability, files_to_encfiles = backend.pFiles() # dictionary: {filename: kb}
    if "upload-result" in session:
        upload_result = session["upload-result"]
        session.pop("upload-result")
    else:
        upload_result = None

    if "download-result" in session:
        download_result = session["download-result"]
        session.pop("download-result")
    else:
        download_result = None
    
    if "delete-result" in session:
        delete_result = session["delete-result"]
        session.pop("delete-result")
    else:
        delete_result = None
    
    return render_template('index.html', files_to_storage=files_to_storage, 
    files_to_availability = files_to_availability, files_to_encfiles = files_to_encfiles, 
    upload_result=upload_result, download_result=download_result, delete_result = delete_result)


@app.route('/upload', methods=['POST'])
def upload():
    """ Upload the file the user has selected to upload """
    if request.method == "POST" and 'file' in request.files:
        try:
            f = request.files.get('file')
            if not f or f.filename == '':
                return redirect('/')

            filename = secure_filename(f.filename) # prevent malicious entries
            print(filename)
            dest = os.path.join(path, "uploading_files")
            full_path = os.path.join(dest, filename)

            f.save(full_path)
            file_size = os.path.getsize(full_path) # bytes
            
            # buffer for ciphertext. 1.2 is arbitrary and intended as a ceiling but can be adjusted
            required_storage = int(file_size * 1.3) 

            result = backend.pDistribute(filename = filename, required_storage = required_storage)
            session["upload-result"] = result

            # After uploading, empty the uploading_files folder
            uploaded_files = glob.glob(os.path.join(dest, '*')) #all files in dir
            for uploaded_file in uploaded_files:
                if os.path.isfile(uploaded_file):
                    os.remove(uploaded_file)
            
            return redirect('/')


        except Exception as e:
            print(f"[ERROR] While attempting to store file locally, encountered error: {e}")
            return redirect('/')

    return redirect('/')


@app.route('/download', methods=['POST'])
def download():
    """ Collect a list of file names and download them"""
    if request.method == "POST":
        selected_files = [request.form.get('file')]
        session["download-result"] = backend.pRetrieve(selected_files)

    return redirect('/')


@app.route('/availability', methods=['POST'])
def availability():
    """Direct to more info on S-nodes associated with a file the user has specified on index.html"""
    # The file name the user has selected to know availability for
    selected_file = list(request.form.keys())[0]

    # {snode_name: connected_status} for all snodes storing a chunk of the file
    name_availability = backend.pFileToSnodeAvailability(selected_file)

    return render_template("availability.html", name_availability=name_availability)



@app.route('/delete', methods=['POST'])
def delete():
    """ Collects the list of selected file names and delete them,
    displaying the remaining files by redirecting to `/`"""
    if request.method == "POST":
        selected_files = [request.form.get('file')]
        session["delete-result"] = backend.pDelete(selected_files)

    return redirect('/')


@app.route('/snodes', methods=['GET', 'POST'])
def snodes():
    """Return the list of connected SNODES and display, with info, on nodes.html"""
    connected_snodes, used_storage = backend.pSnodes() # {uuid: (node_name, used_storage, total_storage)} (for that snode)
    connected_snodes = connected_snodes if connected_snodes is not None else {}
    
    requested_snodes = backend.pAvailableSnodes()
    requested_snodes = requested_snodes if requested_snodes is not None else {}
    
    total_storage = backend.pTotalStorage()

    return render_template('nodes.html', connected_snodes=connected_snodes, 
        available_snodes = requested_snodes, total_storage = total_storage, 
        used_storage = used_storage, type="s")


@app.route('/rnodes', methods=['GET', 'POST'])
def rnodes():
    """Return the list of connected RNODES and provide modification options"""
    connected_rnodes = backend.pRnodes()
    connected_rnodes = connected_rnodes if connected_rnodes is not None else {}
    
    available_rnodes = backend.pAvailableRnodes()
    available_rnodes = available_rnodes if available_rnodes is not None else {}

    return render_template('nodes.html', connected_nodes = connected_rnodes, available_nodes = available_rnodes, type="r")


@app.route('/add-snode', methods=['POST'])
def add_snode():
    """Transfer selected pending S-node to connected"""
    selected_snodes = request.form.keys()
    backend.pAddSnode(selected_snodes)
    return redirect('/snodes')

@app.route('/remove-snode', methods=['POST'])
def remove_snode():
    """Remove the S-node selected by the user on index.html"""
    selected_snodes = list(request.form.keys())[0]
    backend.pRemoveSnode(selected_snodes)
    return redirect('/snodes')

@app.route('/add-rnode', methods=['POST'])
def add_rnode():
    """TODO: implement?"""
    selected_rnodes = request.form.getlist('selected-available-node')
    size_snode = request.form.get('StorageSize')
    backend.pAddRnode(selected_rnodes, size_snode)
    return redirect('/rnodes')

@app.route('/remove-rnode', methods=['POST'])
def remove_rnode():
    """TODO: implement?"""
    selected_rnodes = request.form.getlist('selected-node')
    backend.pRemoveRnode(selected_rnodes)
    return redirect('/rnodes')


@app.route('/cloud',methods=['GET','POST'])
def cloud_support():
    """TODO: docstring"""
    google_avaliability = False
    aws_avaliablity = False
    err_msg = ""
    if request.method=="POST":
        google_avaliability = request.form.get("google")
        aws_avaliability = request.form.get("aws")
        if google_avaliability == "on":
            err = backend.rnode.enableGoogle()
            if err == False:
                err_msg = err_msg + "google key not found"
            else: err_msg = err_msg + "successfully enable google\n"
        else: 
            backend.rnode.disableGoogle()
            err_msg = err_msg + "successfully disable google\n"
        if aws_avaliability == "on":
            err = backend.rnode.enableAws()
            if err == False:
                err_msg = err_msg + "aws key not found"
            else: err_msg = err_msg + "successfully enable google\n"
        else: 
            backend.rnode.disableAws()
            err_msg = err_msg + "successfully disable aws\n"
    if backend.rnode != None:
        google_avaliability = backend.rnode.google
        aws_avaliablity = backend.rnode.aws
    cloud_files = []
    if backend.rnode.aws:
        for filename in aws_util.get_file_list():
            if filename not in cloud_files:
                cloud_files.append(filename)
    if backend.rnode.google:
        for filename in google_util.get_file_list():
            if filename not in cloud_files:
                cloud_files.append(filename)

    return render_template("cloud.html",google=google_avaliability,aws=aws_avaliablity, err_msg = err_msg,cloud_files = cloud_files)
 

@app.route('/google',methods=["POST"])
def set_google_key():
    """TODO: docstring"""
    if request.method=="POST":
        google_path = request.form['google_key']
        google_util.set_key(google_path)

    return redirect('/cloud')


@app.route('/aws',methods=["POST"])
def set_aws_key():
    """TODO: docstring"""
    if request.method=="POST":
        aws_access_id = request.form['aws_access_id']
        aws_access_key = request.form['aws_access_key']
        aws_util.set_key(access_id=aws_access_id,key=aws_access_key)
 
    return redirect('/cloud')


@app.route('/download-cloud/<filename>',methods=["GET","POST"])
def download_from_cloud(filename):
    masked_file_name = new_enc.encrypt_filename(filename)
    backend.rnode.download_from_cloud(masked_file_name)
    encrypt.decrypt(filename)
    download_path = f"{pathlib.Path.home()}/Downloads"
    if os.path.exists(download_path):
        cmd_util.move(filename,f"{download_path}/{filename}")
    return redirect("/cloud")

if __name__ == '__main__':
    backend = pShare()
    app.run(debug=False)
