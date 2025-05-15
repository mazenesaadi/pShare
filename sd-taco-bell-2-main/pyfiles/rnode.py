import grpc
from concurrent import futures
import storage_node_pb2
import storage_node_pb2_grpc
import time
import os
import json
import random
from typing import List, Dict, Set, Tuple
import uuid_utils
import network_utils
import socket
import threading
from zeroconf import ServiceInfo, Zeroconf
from pathlib import Path
import uuid
import sys
import logging
import google_util
import aws_util
import new_enc as enclib
import shutil
import erasurezfec as zfec
import encrypt
import math
import cmd_util

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
NODES_FILE = Path("registry_conf/nodes.json")

class StorageService(storage_node_pb2_grpc.StorageServiceServicer):
    def __init__(self):
        self.connected_clients: Dict[str, str] = {} # Clients: {UUID, IP:Port}
        self.client_contexts: Dict[str, grpc.ServicerContext] = {} # Store specific gRPC stuff needed for each client as each client has specific gRPC handling
        self.client_last_heartbeat: Dict[str, float] = {}  # Add timestamp tracking: {UUID: timestamp}
        self.client_file_ports: Dict[str, int] = {} # {UUID: port}
        self.client_storage_capacity: Dict[str, int] = {} # Client {UUID : storage_capacity}
        self.client_hostnames: Dict[str, str] = {} # {UUID: hostname}
        self.download_dir = "downloaded_files"
        os.makedirs(self.download_dir, exist_ok=True)
        self.nodes = self.load_nodes()  # Load nodes from file
        self.snodes_file = Path("registry_conf/snodes.json")
        self.zombies = Path("registry_conf/file_mappings/zombies.json")
        self.snodes = self.load_snodes() # Load snodes from file, {UUID: hostname}
        self.pending_nodes: Dict[str, str] = {}  # {UUID: address}
        self.pending_hostnames: Dict[str, str] = {} # For pending snodes: {UUID: hostname}
        self.pending_storage: Dict[str, str] = {} # For pending snodes: {UUID: tribute storage}

        # Start heartbeat monitoring thread
        self._start_heartbeat_monitor()


    # Check on clients every 5 secs
    def _start_heartbeat_monitor(self):
        """Remove clients who haven't sent a signal in the last 5 seconds"""
        def monitor_heartbeats():
            while True:
                current_time = time.time()
                ianctive_clients = []
                # Check for clients that haven't sent a heartbeat in 5 seconds
                for uuid, last_time in self.client_last_heartbeat.items():
                    if current_time - last_time > 5:  # 5 second timeout
                        ianctive_clients.append(uuid)
                # Remove inactive clients
                for uuid in ianctive_clients:
                    self._handle_client_disconnect(uuid)
                time.sleep(5)  # Check every 5 seconds

        
        # Do this in a non-blocking thread
        threading.Thread(target=monitor_heartbeats, daemon=True).start()


    def _handle_client_disconnect(self, uuid: str) -> None:
        """Remove client information when it disconnects"""
        if uuid in self.connected_clients:
            addr = self.connected_clients[uuid]
            logging.info(f"\nClient disconnected - UUID: {uuid}, Address: {addr}")
            self.pop_client(uuid)
        
        if uuid in self.pending_nodes:
            del self.pending_nodes[uuid]
            self.pending_hostnames.pop(uuid, None)
            self.pending_storage.pop(uuid, None)
    
    
    def pop_client(self, uuid):
        """ Remove mentions of specified S-node from R-node fields (not JSON files) """
        if uuid in self.connected_clients:
            del self.connected_clients[uuid]
        self.client_contexts.pop(uuid, None)
        self.client_last_heartbeat.pop(uuid, None)
        self.client_file_ports.pop(uuid, None)
        self.client_storage_capacity.pop(uuid, None)
        self.client_hostnames.pop(uuid, None)

    
    def load_nodes(self):
        """Load registered nodes from nodes.json."""
        NODES_FILE.parent.mkdir(parents=True, exist_ok=True)  # Create the directory if it doesn't exist
        if not NODES_FILE.exists():
            with NODES_FILE.open('w') as f:
                json.dump({}, f, indent=4)
        try:
            with NODES_FILE.open('r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}


    def load_snodes(self):
        """Return {uuid: hostname} for all S-nodes"""
        self.snodes_file.parent.mkdir(parents=True, exist_ok=True) # Similarly
        if not self.snodes_file.exists():
            with self.snodes_file.open('w') as f:
                json.dump({}, f, indent=4)
        
        try:
            with self.snodes_file.open('r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}


    def save_node(self, uuid: str, node_type: str):
        """Changes state of a pending node to a connected snode
            transfers data from pending dics to connected client
            dics, then saves as an snode in the json reference file,
            then removes its data from the pending dics 
        """
        self.nodes[uuid] = node_type
        self.snodes[uuid] = self.pending_hostnames[uuid]
        self.client_storage_capacity[uuid] = self.pending_storage[uuid]
        self.client_hostnames[uuid] = self.pending_hostnames[uuid]
        
        # Remains connected for 15 additional seconds (prevents the delay
        # of waiting for the snode to send another request in order
        # for the frontend connected snodes to be updated)
        self.connected_clients[uuid] = uuid

        with NODES_FILE.open('w') as f:
            json.dump(self.nodes, f, indent=4)
        
        with self.snodes_file.open('w') as f:
            json.dump(self.snodes, f, indent=4)
            print(f"Finished dumping {self.snodes}")
        
        del self.pending_storage[uuid]
        del self.pending_hostnames[uuid]
        del self.pending_nodes[uuid]
        

    def Heartbeat(self, request_iterator, context):
        """Handle heartbeats from clients"""
        client_uuid = None
        
        try:
            for request in request_iterator:
                client_uuid = request.uuid
    
                if client_uuid not in self.connected_clients:

                    yield storage_node_pb2.HeartbeatResponse(
                        success=False,
                        message="Unknown client UUID"
                    )
                    return
                
                # Update last heartbeat timestamp
                self.client_last_heartbeat[client_uuid] = time.time()
                self.client_contexts[client_uuid] = context
                # Store specific file service port
                self.client_file_ports[client_uuid] = request.file_service_port
                # Store client committed storage
                self.client_storage_capacity[client_uuid] = request.storage_capacity_mb
                
                # Store host name
                # self.client_hostnames[client_uuid] = request.hostname
                # currently hostname the snode passes = instance name provided, or hostname by default
                self.client_hostnames[client_uuid] = request.hostname 
                yield storage_node_pb2.HeartbeatResponse(
                    success=True,
                    message="Heartbeat acknowledged"
                )
        except Exception as e:
            logging.error(f"Heartbeat error for client {client_uuid}: {e}", exc_info=True)
        finally:
            if client_uuid:
                self._handle_client_disconnect(client_uuid)


    def RequestUUID(self, request, context):
        """Handle when a client requests a UUID (first connection)"""
        try:
            if request.type == 'request_uuid':
                # Generate UUID for client
                client_uuid = uuid_utils.generate_uuid()

                # Backend debugging
                client_addr = context.peer()
                logging.warning(f"New node pending approval - UUID: {client_uuid}, Address: {client_addr}")

                # Store generated UUID
                self.pending_nodes[client_uuid] = client_addr

                # Initial connection time
                self.client_last_heartbeat[client_uuid] = time.time()

                # Snode provides storage and hostname information on first request
                self.pending_storage[client_uuid] = request.storage_capacity_mb
                self.pending_hostnames[client_uuid] = request.hostname

                return storage_node_pb2.UUIDResponse(
                    success=False,
                    uuid=client_uuid,
                    message="UUID generated successfully"
                )
            else:
                logging.warning("Invalid request type received in RequestUUID")
                return storage_node_pb2.UUIDResponse(
                    success=False,
                    message="Invalid request type"
                )
        except Exception as e:
            logging.error(f"Exception in RequestUUID: {e}", exc_info=True)
            context.abort(grpc.StatusCode.INTERNAL, "Internal error during UUID generation")


    def ValidateUUID(self, request, context):
        """ Handle reconnection requests from previously connected, known storage nodes """
        try:
            client_uuid = request.uuid
            client_addr = context.peer()
            
            # UUID known, approve connection immediately
            self.nodes = self.load_nodes() # reload
            if client_uuid in self.nodes:
                self.connected_clients[client_uuid] = client_addr
                self.client_last_heartbeat[client_uuid] = time.time()
                logging.info(f"Validated known UUID {client_uuid} for client at {client_addr}")
                
                return storage_node_pb2.UUIDResponse(
                    success=True,
                    uuid=client_uuid,
                    message="UUID validated successfully"
                )
            else:
                # Unknown UUID, add to pending list quietly after first warning
                if client_uuid not in self.pending_nodes:
                    self.client_last_heartbeat[client_uuid] = time.time() # if >15 seconds from last request, pending node removed
                    self.pending_nodes[client_uuid] = client_addr
                    logging.warning(f"New node pending approval - UUID: {client_uuid}, Address: {client_addr}")
                # Don't repeatedly log warnings

                # Prevent available snodes being periodically disconnected if
                # they send a request within (heartbeat check time) seconds
                else:
                    self.client_last_heartbeat[client_uuid] = time.time()

            # Add back to pending nodes (which is cleared on disconnect)
            self.pending_nodes[client_uuid] = client_addr
            self.pending_storage[client_uuid] = request.storage_capacity_mb
            self.pending_hostnames[client_uuid] = request.hostname

            return storage_node_pb2.UUIDResponse(
                success=False,
                uuid=client_uuid,
                message="UUID pending approval from registry node."
            )

        except Exception as e:
            logging.error(f"Exception in ValidateUUID: {e}", exc_info=True)
            context.abort(grpc.StatusCode.INTERNAL, "Internal error during UUID validation")
   

    def get_total_storage(self) -> int:
        """Return the total storage capacity across all connected nodes"""
        return sum(self.client_storage_capacity.values())


    def get_hostname(self, uuid: str) -> str:
        """Return hostname given UUID"""
        return self.client_hostnames.get(uuid, None)


    def get_storage(self, uuid: str) -> str:
        """ Return S-node tribute storage given UUID"""
        return self.client_storage_capacity.get(uuid, None)


class RegistryNode:
    def __init__(self, service_type="_rnode._tcp.local.", service_name="rnode"):
        self.zeroconf = Zeroconf()
        self.service_type = service_type
        self.service_name = service_name
        self.full_name = f"{service_name}.{service_type}"
        self.server = None
        self.storage_service = StorageService()
        self.mappings_dir = os.path.join(os.getcwd(), "registry_conf", "file_mappings")
        self.uuid_to_chunks = os.path.join(self.mappings_dir, "uuid_to_chunks.json")
        self.file_total_sizes = os.path.join(self.mappings_dir, "file_total_sizes.json")
        self.file_to_uuids = os.path.join(self.mappings_dir, "file_to_uuids.json")
        self.snodes_storage_used = os.path.join(self.mappings_dir, "snodes_storage_used.json")
        self.key_name_mappings = os.path.join(self.mappings_dir, "key_name_mappings.json")
        self.chunk_to_size = os.path.join(self.mappings_dir, "chunk_to_size.json")
        self.zombies = os.path.join(self.mappings_dir, "zombies.json") # uuid: list of files to delete
        self.meta_files = os.path.join(os.getcwd(), "registry_conf", "meta_files")
        self.registry_dir = os.path.join(os.getcwd(), "registry_conf")
        self.upload_dir = os.path.join(os.getcwd(), "uploading_files")

        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.mappings_dir, exist_ok=True)
        os.makedirs(self.meta_files, exist_ok=True)

        # Create the .json files if they do not already exist
        if not os.path.exists(self.uuid_to_chunks):
            f = open(self.uuid_to_chunks, 'w')
            json.dump({}, f, indent=4)
        if not os.path.exists(self.chunk_to_size):
            f = open(self.chunk_to_size, 'w')
            json.dump({}, f, indent=4)
        if not os.path.exists(self.file_total_sizes):
            f = open(self.file_total_sizes, 'w')
            json.dump({}, f, indent=4)
        if not os.path.exists(self.file_to_uuids):
            f = open(self.file_to_uuids, 'w')
            json.dump({}, f, indent=4)
        if not os.path.exists(self.snodes_storage_used):
            f = open(self.snodes_storage_used, 'w')
            json.dump({}, f, indent=4)
        if not os.path.exists(self.zombies):
            f = open(self.zombies, 'w')
            json.dump({}, f, indent=4)

        self.aws = False
        self.google = False


    def enableGoogle(self):
        if google_util.check_key():
            self.google = True
            self.storage_service.connected_clients.update({"google":"0:0"})
        return self.google
    

    def enableAws(self):
        if aws_util.check_key():
            self.aws = True
            self.storage_service.connected_clients.update({"aws":"0:0"})
        return self.aws
    

    def disableAws(self):
        self.aws = False
        if "aws" in self.storage_service.connected_clients:
            self.storage_service.connected_clients.pop("aws")


    def disableGoogle(self):
        self.google = False
        if "google" in self.storage_service.connected_clients:
            self.storage_service.connected_clients.pop("google")


    def download_from_cloud(self,file_path):
        temp_path = self.storage_service.download_dir
        if os.path.exists(temp_path)== False:
            cmd_util.create_dir(temp_path)
        basename = os.path.basename(file_path)
        google_list = []
        if self.google == True:
            google_list = google_util.get_full_name(basename)
        for file in google_list:
            google_util.download_from_gcs(file)
            shutil.move(file , f"{temp_path}/{file}")
        aws_list = []
        if self.aws == True:
            aws_list = aws_util.get_full_name(basename)
        for file in aws_list:
            aws_util.download(file)
            shutil.move(file , f"{temp_path}/{file}")


    def register_service(self, port: int):
        """Start broadcast"""
        hostname = socket.gethostname()

        local_ip = network_utils.get_real_ip()
        info = ServiceInfo(
            type_=self.service_type,
            name=self.full_name,
            addresses=[socket.inet_aton(local_ip)],
            port=port,
            server=f"{hostname}.local."
        )
        self.zeroconf.register_service(info)
        logging.info(f"Registered service {self.full_name} on {local_ip}:{port}")

        # Create the gRPC server
        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        storage_node_pb2_grpc.add_StorageServiceServicer_to_server(
            self.storage_service, self.server
        )
        # No SSL/TLS, won't matter since it's LAN(?)
        self.server.add_insecure_port(f'[::]:{port}')
        self.server.start()
        
        return info


    def unregister_service(self, info):
        """Stop broadcast"""
        if self.server:
            self.server.stop(0)
        self.zeroconf.unregister_service(info)
        self.zeroconf.close()


    def get_pending_hostname(self, uuid):
        """Get hostname of pending S-node"""
        return self.storage_service.pending_hostnames.get(uuid, None)


    def get_pending_storage(self, uuid):
        """Get tribute storage of pending S-node"""
        return self.storage_service.pending_storage.get(uuid, "Unknown storage")


    def distribute(self, filename, uuids, m, k):
        """ Upload the file specified by the absolute_path/filename to specified uuids with k parity chunks """
        try:
            if enclib.encrypt_filename(filename) is not None:
                return "Cannot upload the same file twice!"
    
            # takes file from pyfiles/uploading_files, creates (m, k) chunks in pyfiles/file_chunked
            output_dir = os.path.join(os.getcwd(), "registry_conf", "file_chunked")
            dest = os.path.join(os.getcwd(), "uploading_files")
            absolute_path = os.path.join(dest, filename)

            masked_filename = enclib.encrypt_file(absolute_path)

            if not masked_filename:
                return "Error encrypting file on upload"
            
            file_encrypted_path = os.path.join("registry_conf", masked_filename)
            
            if (zfec.encode_file(input_file = file_encrypted_path, output_dir = output_dir, m = m, k = k)):
                remove_file = os.path.join(os.getcwd(), "registry_conf", masked_filename)
                # clear encrypted file
                os.remove(remove_file)
            # On success, uploads (cwd)/file_chunked/filename.{i} to snode[i], 
            #..., (cwd)/file_chunked/file_name.{m} to snode[n]
                chunk_dir = os.path.join(os.getcwd(), "registry_conf", "file_chunked")
                meta_dir = os.path.join(os.getcwd(), "registry_conf", "meta_files")

                for i in range(m):
                    chunk_name = f"{masked_filename}.{i}"
                    chunk_path_i = os.path.join(chunk_dir, chunk_name)
                    self.upload_file_to_snode(uuids[i], chunk_path_i)
                    os.remove(chunk_path_i) # clear the folder
            
                # Move meta file from pyfiles/file_chunked to pyfiles/meta_files dir
                meta_name = f"{masked_filename}.meta"
                old_meta_path = os.path.join(chunk_dir, meta_name)
                new_meta_path = os.path.join(meta_dir, meta_name)
                shutil.move(old_meta_path, new_meta_path)

                return "Upload successful!"

        except Exception as e:
            return f"While attempting to upload file, encountered error: {e}"


    def update_json(self,chunk_name:str,chunk_size:int,target_uuid:str):
                
            # update uuid file mappings here
                # chunk_name = (erasure) chunk name
                with open(self.uuid_to_chunks, 'r') as f:
                    uuid_to_chunks = json.load(f)
                with open(self.file_total_sizes, 'r') as f:
                    file_total_sizes = json.load(f)
                with open(self.file_to_uuids, 'r') as f:
                    file_to_uuids = json.load(f)
                with open(self.snodes_storage_used, 'r') as f:
                    snodes_storage_used = json.load(f)
                if target_uuid not in uuid_to_chunks:
                    uuid_to_chunks[target_uuid] = [chunk_name]
                if chunk_name not in uuid_to_chunks[target_uuid]:
                    uuid_to_chunks[target_uuid].append(chunk_name)
                # Load chunk_to_size.json
                with open(self.chunk_to_size, 'r') as f:
                    chunk_to_size = json.load(f)
                
                # Load snodes_storage_used.json
                with open(self.snodes_storage_used, 'r') as f:
                    snodes_storage_used = json.load(f) # uuid: total storage

                # write storage space used for the chunk
                if chunk_name in chunk_to_size:
                    chunk_to_size[chunk_name] = chunk_to_size[chunk_name] + chunk_size
                else:
                    chunk_to_size[chunk_name] = chunk_size
                
                # write new storage space taken by the file (both for the file, and each snode it is stored on)
                full_file_name = chunk_name[:-2] 
                if target_uuid not in file_total_sizes:
                    file_total_sizes[full_file_name] = chunk_size
                else:
                    file_total_sizes[full_file_name] = file_total_sizes[full_file_name] + chunk_size

                if target_uuid not in snodes_storage_used:
                    snodes_storage_used[target_uuid] = chunk_size
                else:
                    snodes_storage_used[target_uuid] = snodes_storage_used[target_uuid] + chunk_size
                
                # update {file: [uuids]}
                if full_file_name not in file_to_uuids:
                    file_to_uuids[full_file_name] = [target_uuid]
                elif target_uuid not in file_to_uuids[full_file_name]:
                    file_to_uuids[full_file_name].append(target_uuid)
                
                # write changes
                with open(self.uuid_to_chunks, 'w') as f:
                    json.dump(uuid_to_chunks, f, indent=4)
                with open(self.file_total_sizes, 'w') as f:
                    json.dump(file_total_sizes, f, indent=4)
                with open(self.file_to_uuids, 'w') as f:
                    json.dump(file_to_uuids, f, indent=4)
                with open(self.snodes_storage_used, 'w') as f:
                    json.dump(snodes_storage_used, f, indent=4)
                with open(self.chunk_to_size, 'w') as f:
                    json.dump(chunk_to_size, f, indent=4)
  


    def upload_file_to_snode(self, 
    target_uuid: str, filename: str):
        """Upload specified file to specified S-node"""
        chunk_size = os.path.getsize(filename)
        chunk_name = os.path.basename(filename)
        if target_uuid == "aws":
            try:
                aws_util.upload(filename)
                self.update_json(chunk_name,chunk_size,target_uuid)
                return True
            except Exception as e:
                print(f"[ERROR] AWS Upload: {e}")
                return False
        if target_uuid == "google":
            try:
                google_util.upload_to_gcs(filename)
                self.update_json(chunk_name,chunk_size,target_uuid)
                return True
            except Exception as e:
                print(f"[ERROR] Google Upload: {e}")
                return False
        try:
            with open(self.uuid_to_chunks, 'r') as f:
                uuid_to_chunks = json.load(f)
            with open(self.file_total_sizes, 'r') as f:
                file_total_sizes = json.load(f)
            with open(self.file_to_uuids, 'r') as f:
                file_to_uuids = json.load(f)
            with open(self.snodes_storage_used, 'r') as f:
                snodes_storage_used = json.load(f)

            # Get client context for target S-node
            context = self.storage_service.client_contexts.get(target_uuid)
            if not context or target_uuid not in self.storage_service.connected_clients:
                print(f"[ERROR] Storage node {target_uuid} is not connected")
                return False
            
            client_addr = self.storage_service.connected_clients[target_uuid]
            ip = client_addr.split(':')[1]  # Get the IP address part
            port = self.storage_service.client_file_ports.get(target_uuid)
        
            # Create a channel to the storage node
            channel = grpc.insecure_channel(f'{ip}:{port}')

            # A stub is an object that allows use of server methods like local functions
            stub = storage_node_pb2_grpc.StorageServiceStub(channel)
            

            def file_chunk_generator():
                CHUNK_SIZE = 1024 * 1024  # 1MB chunks
                try:
                    with open(filename, 'rb') as f:
                        offset = 0
                        while True:
                            chunk = f.read(CHUNK_SIZE)
                            if not chunk:
                                break
                            yield storage_node_pb2.FileChunk(
                                content=chunk,
                                filename=os.path.basename(filename),
                                offset=offset,
                                total_size=chunk_size
                            )
                            offset += len(chunk)
                except FileNotFoundError:
                    print(f"[ERROR] File {filename} not found")
                    return
                except Exception as e:
                    print(f"[ERROR] failed to read file: {e}")
                    return

            # Send the file chunks to the storage node
            response = stub.UploadFile(file_chunk_generator())

            if response.success:
                # update uuid file mappings here
                # chunk_name = (erasure) chunk name
                chunk_name = os.path.basename(filename)
                if target_uuid not in uuid_to_chunks:
                    uuid_to_chunks[target_uuid] = [chunk_name]
                if chunk_name not in uuid_to_chunks[target_uuid]:
                    uuid_to_chunks[target_uuid].append(chunk_name)

                # Load chunk_to_size.json
                with open(self.chunk_to_size, 'r') as f:
                    chunk_to_size = json.load(f)
                
                # Load snodes_storage_used.json
                with open(self.snodes_storage_used, 'r') as f:
                    snodes_storage_used = json.load(f) # uuid: total storage

                # write storage space used for the chunk
                if chunk_name in chunk_to_size:
                    chunk_to_size[chunk_name] = chunk_to_size[chunk_name] + chunk_size
                else:
                    chunk_to_size[chunk_name] = chunk_size
                
                # write new storage space taken by the file (both for the file, and each snode it is stored on)
                full_file_name = chunk_name[:-2] 
                if target_uuid not in file_total_sizes:
                    file_total_sizes[full_file_name] = chunk_size
                else:
                    file_total_sizes[full_file_name] = file_total_sizes[full_file_name] + chunk_size

                if target_uuid not in snodes_storage_used:
                    snodes_storage_used[target_uuid] = chunk_size
                else:
                    snodes_storage_used[target_uuid] = snodes_storage_used[target_uuid] + chunk_size
                
                # update {file: [uuids]}
                if full_file_name not in file_to_uuids:
                    file_to_uuids[full_file_name] = [target_uuid]
                elif target_uuid not in file_to_uuids[full_file_name]:
                    file_to_uuids[full_file_name].append(target_uuid)
                
                # write changes
                with open(self.uuid_to_chunks, 'w') as f:
                    json.dump(uuid_to_chunks, f, indent=4)
                with open(self.file_total_sizes, 'w') as f:
                    json.dump(file_total_sizes, f, indent=4)
                with open(self.file_to_uuids, 'w') as f:
                    json.dump(file_to_uuids, f, indent=4)
                with open(self.snodes_storage_used, 'w') as f:
                    json.dump(snodes_storage_used, f, indent=4)
                with open(self.chunk_to_size, 'w') as f:
                    json.dump(chunk_to_size, f, indent=4)
                
                return True
            else:
                print(f"[ERROR] Upload failed: {response.message}")
                return False

        except Exception as e:
            print(f"[ERROR] on upload: {e}")
            return False
    

    def availability_util(self, file_name):
        """ Accept a filename, return {snode_name: connected_status} for all snodes storing the file """
        try:
            with open(self.file_to_uuids, 'r') as f:
                file_to_uuids = json.load(f) # {filename: [uuids]}

            # List of UUIDs storing the specified filename
            relevant_uuids = file_to_uuids[file_name]

            snode_to_availability = {}
            for uuid in relevant_uuids:
                with self.storage_service.snodes_file.open('r') as f:
                    uuids_to_names = json.load(f)
                available = 0
                if uuid in self.storage_service.connected_clients:
                    available = 1
                snode_to_availability[uuids_to_names[uuid]] = available
            
            return snode_to_availability

        except Exception as e:
            print(f"Error: {e}")


    def get_used_storage(self, uuid):
        """ Return the storage used by a specified snode """
        with open(self.snodes_storage_used, 'r') as f:
            snodes_storage_used = json.load(f)
        
        return snodes_storage_used[uuid] if uuid in snodes_storage_used else 0



    def download(self, filename: str) -> bool:
        """ Download all the chunks, and puts them in downloaded_files,
        to be decrypted and reassembled """
        print(f"Received: {filename}")
        try: self.download_from_cloud(filename)
        except Exception as e:
            print()
        try:
            with open(self.file_to_uuids, 'r') as f:
                file_to_uuids = json.load(f)
            with open(self.uuid_to_chunks, 'r') as f:
                uuid_to_chunks = json.load(f)

            file_uuids = file_to_uuids[filename]
            connected_uuids = self.get_uuids()
            # all connected uuids containing a chunk (uuids not unique in list, since node can store multiple chunks)
            expanded_chunk_mapping = []
            available_chunks = 0

            # Add data to uuid_to_chunk: {uuid1: chunk1, uuid1: chunk7, uuid4: chunk8, ...}
            for uuid in connected_uuids:
                if uuid not in file_uuids:
                    break
                
                # Now iterating through connected, relevant uuid chunks
                for chunk in uuid_to_chunks[uuid]:
                    stored_chunks = uuid_to_chunks[uuid] # stored on this node
                    for chunk in stored_chunks:
                        if chunk[:-2] == filename:
                            expanded_chunk_mapping.append((uuid, chunk))
                            available_chunks = available_chunks + 1

            num_required = self.get_required(filename)
            if available_chunks < num_required:
                return f"Not enough required S-nodes to reconstruct"


            # Get k random chunks from the n available
            subset_available = random.sample(range(0, available_chunks), num_required)
            # A file cannot be reuploaded until deleted, so the chunks will
            # be unique (i.e. snode.example1 cannot have the same chunk as snode.example2)
            # But one S-node may have multiple chunks, in the case that it is carrying
            # a chunk from an S-node that previously stored this file but was deleted
            for index in subset_available:
                expanded_map = expanded_chunk_mapping[index]
                self.download_chunk(expanded_map[0], expanded_map[1]) # uuid, stored_chunk
            
            enclib.decrypt_file(filename)
            return "Success"
        
        except Exception as e:
            return f"Error on download: {e}"


    def download_chunk(self, target_uuid, chunk_name):
        """ Download a specified chunk from the target uuid """
        try:
            # Check if node is connected
            if target_uuid not in self.storage_service.connected_clients:
                print(f"[ERROR] Storage node {target_uuid} is not connected!")
                raise Exception("Target UUID could not be reached")
                    
            client_addr = self.storage_service.connected_clients[target_uuid]
            ip = client_addr.split(':')[1]
            port = self.storage_service.client_file_ports.get(target_uuid)
            
            if not port:
                print(f"[ERROR] No file service port found for storage node {target_uuid}")
                return False
                
            # Create channel to storage node
            print(f"[INFO] Connecting to storage node at {ip}:{port}")
            channel = grpc.insecure_channel(f'{ip}:{port}')
            stub = storage_node_pb2_grpc.StorageServiceStub(channel)
            
            # Prepare download request
            request = storage_node_pb2.FileRequest(filename=chunk_name)
            os.makedirs("downloaded_files", exist_ok=True)
            save_path = os.path.join("downloaded_files", chunk_name)

            total_size = 0
            with open(save_path, 'wb') as f:
                try:
                    for chunk in stub.RequestFile(request):
                        f.write(chunk.content)
                        total_size += len(chunk.content)
                        if chunk.total_size > 0:
                            progress = (total_size / chunk.total_size) * 100
                            print(f"\rDownloading: {progress:.1f}%", end="", flush=True)
                except grpc.RpcError as rpc_error:
                    print(f"\nRPC error: {rpc_error.code()}: {rpc_error.details()}")
                    if os.path.exists(save_path):
                        os.remove(save_path)
                    return False
                        
            print(f"File downloaded successfully to {save_path}")
            return True
            
        except Exception as e:
            print(f"Download error details: {str(e)}")
            print(f"Error type: {type(e)}")
            if 'save_path' in locals() and os.path.exists(save_path):
                os.remove(save_path)
            return False

     
    def get_random_snodes(self, n: int):
        """Choose N random S-nodes"""
        connected_snodes = list(self.storage_service.connected_clients.keys())

        if not connected_snodes:
            print("No storage nodes connected")
            return []
        
        if n > len(connected_snodes):
            print("Too many snodes requested")
            return []
        
        selected_snodes = random.sample(connected_snodes, n)
        return selected_snodes
    

    def remove_client(self, uuid: str) -> None:
        """ Disconnect from an S-node (will then require approval on its next connection attempt) """

        # Open jsons
        with open(self.uuid_to_chunks, 'r') as f:
            uuid_to_chunks = json.load(f)
        with open(NODES_FILE, 'r') as f:
            gen_nodes_file = json.load(f)
        with open(self.storage_service.snodes_file, 'r') as f:
            gen_snodes_file = json.load(f)

        if uuid in uuid_to_chunks:
            # Remove any stored files
            file_names = uuid_to_chunks[uuid] # returns chunk names, which end with .{i} (i.e. .2) so need [:-2]
            for file_name in file_names:
                file_name = file_name[:-2]
                self.redistribute(file_name, uuid)
            del uuid_to_chunks[uuid]
        
        # clear temp memory of client        
        self.storage_service.pop_client(uuid)

        with open(self.file_to_uuids, 'r') as f:
            file_to_uuids = json.load(f)
        """ Since the redistribute function call updates this json, it is necessary to load it here"""
        with open(self.snodes_storage_used, 'r') as f:
            snodes_storage_used = json.load(f)

        # Delete all mentions of the S-node in .json files
        for file, uuids in file_to_uuids.items():
            if uuid in uuids:
                file_to_uuids[file].remove(uuid)
            if uuids is None:
                del file_to_uuids[file]
        
        if uuid in snodes_storage_used:
            del snodes_storage_used[uuid]
        
        if uuid in gen_nodes_file:
            del gen_nodes_file[uuid]

        if uuid in gen_snodes_file:
            del gen_snodes_file[uuid]

        # Write changes
        with open(self.uuid_to_chunks, 'w') as f:
            json.dump(uuid_to_chunks, f, indent=4)
        with open(self.snodes_storage_used, 'w') as f:
            json.dump(snodes_storage_used, f, indent=4)
        with open(NODES_FILE, 'w') as f:
            json.dump(gen_nodes_file, f, indent=4)
        with open(self.storage_service.snodes_file, 'w') as f:
            json.dump(gen_snodes_file, f, indent=4)
        
        self.nodes = self.storage_service.load_nodes() # Reload to update field


    def redistribute(self, file_name, uuid):
        """Given the file and S-node uuid, 2 scenarios: 
            1) If >=1 other connected client and k>1, stores disconnecting client's chunk on one of the connected clients
                idea is that this disconnect should not affect the data on other S-nodes
            2) If no other connected client, stores disconnecting client's chunk on the R-node (so skip upload step)
        """
        try:
            with open(self.uuid_to_chunks, 'r') as f:
                uuid_to_chunks = json.load(f)

            num_snodes = len(self.get_uuids())
            relevant_chunks = uuid_to_chunks[uuid]

            for relevant_chunk in relevant_chunks:
                # Download target chunk from disconnecting S-node
                self.download_chunk(uuid, relevant_chunk)

            """Case 1: no S-nodes to send the chunk to: store locally"""
            if num_snodes < 2:
                return 1

            """Case 2: can re-upload chunk(s) from disconnecting S-node"""
            for relevant_chunk in relevant_chunks:
                download_path = os.path.join(os.getcwd(), "downloaded_files", relevant_chunk)
                upload_path = os.path.join(os.getcwd(), "uploading_files", relevant_chunk)
                if os.path.exists(download_path):
                    shutil.move(download_path, upload_path)
                
                # A bit of a hack: sample 2 so even if get current in sample, won't reupload to it
                random_snodes = self.get_random_snodes(2)
                if uuid in random_snodes:
                    random_snodes.remove(uuid)
                target_snode = random_snodes[0]


                # Expects full path
                full_path = os.path.join(os.getcwd(), "uploading_files", relevant_chunk)
                self.upload_file_to_snode(target_snode, full_path)
                
                # Remove from disconnecting S-node
                self.remote_delete_file(relevant_chunk, uuid)
            
            return 2
        
        except Exception as e:
            print(e)


    def delete_file(self, file_name):
        """ Delete a file from all connected snodes, and remove all references to it """
        # Open jsons
        try:
            with open(self.file_total_sizes, 'r') as f:
                file_total_sizes = json.load(f)
            with open(self.uuid_to_chunks, 'r') as f:
                uuid_to_chunks = json.load(f)
            with open(self.file_to_uuids, 'r') as f:
                file_to_uuids = json.load(f)
            with open(self.key_name_mappings, 'r') as f:
                key_name_mappings = json.load(f)
            with open(self.snodes_storage_used, 'r') as f:
                snodes_storage_used = json.load(f)
            with open(self.chunk_to_size, 'r') as f:
                chunk_to_size = json.load(f)
            with open(self.zombies, 'r') as f:
                zombies = json.load(f)

            # Some S-nodes where the file is stored may not be connected: add them to
            # the zombies.json file so that when the S-nodes next connect, the appropriate 
            # files are removed
            relevant_uuids = file_to_uuids[file_name] if file_name in file_to_uuids else None
            connected_uuids = self.get_uuids()
            if relevant_uuids:
                for uuid in relevant_uuids:
                    if uuid not in connected_uuids and uuid not in zombies:
                        # The S-node has no other zombie files
                        zombies[uuid] = [file_name]
                    elif uuid not in connected_uuids:
                        zombies[uuid].append(file_name)
                    else:
                        chunk_name = self.snode_to_chunk(target_uuid=uuid, file_name=file_name)
                        if uuid == "gopgle":
                            google_util.delete_file(chunk_name)
                        elif uuid == "aws":
                            aws_util.delete_file(chunk_name)
                        else:
                            self.remote_delete_file(chunk_name=chunk_name, target_uuid=uuid)

            # Remove from chunk_to_size and update snodes_storage_used based on the freed space
            to_delete = []
            for chunk_name, size in chunk_to_size.items():
                if chunk_name[:-2] == file_name:
                    relevant_snode = self.chunk_to_snode(chunk_name)
                    snodes_storage_used[relevant_snode] = snodes_storage_used[relevant_snode] - size
                    to_delete.append(chunk_name)
            for chunk_name in to_delete: # then delete the collected items
                del chunk_to_size[chunk_name]

            # Remove from uuid_to_chunks.json
            for uuid, chunks in uuid_to_chunks.items():
                if uuid in self.get_uuids(): # leave zombie references
                    for chunk in chunks:
                        if chunk[:-2] == file_name: # chunks have file_name.{i} i.e. my_file.1
                            uuid_to_chunks[uuid].remove(chunk)
            
            # Remove from key_name_mappings.json    
            if file_name in key_name_mappings:
                del key_name_mappings[file_name]

            # Remove from file_total_sizes.json
            if file_name in file_total_sizes:
                del file_total_sizes[file_name]
            
            # Remove from file_to_uuids.json
            if file_name in file_to_uuids:
                del file_to_uuids[file_name]
            
            # Write changes
            with open(self.file_total_sizes, 'w') as f:
                json.dump(file_total_sizes, f, indent=4)
            with open(self.uuid_to_chunks, 'w') as f:
                json.dump(uuid_to_chunks, f, indent=4)
            with open(self.file_to_uuids, 'w') as f:
                json.dump(file_to_uuids, f, indent=4)
            with open(self.key_name_mappings, 'w') as f:
                json.dump(key_name_mappings, f, indent=4)
            with open(self.chunk_to_size, 'w') as f:
                json.dump(chunk_to_size, f, indent=4)
            with open(self.snodes_storage_used, 'w') as f:
                json.dump(snodes_storage_used, f, indent=4)
            with open(self.zombies, 'w') as f:
                json.dump(zombies, f, indent=4)
            
            return "Success"

        except Exception as e:
            return e

    def remote_delete_file(self, chunk_name, target_uuid):
        """Attempt to remote delete the file stored on the S-node"""
        try:
            client_addr = self.storage_service.connected_clients[target_uuid]
            ip = client_addr.split(':')[1]
            port=self.storage_service.client_file_ports.get(target_uuid)
            channel = grpc.insecure_channel(f'{ip}:{port}')
            
            stub = storage_node_pb2_grpc.StorageServiceStub(channel)
            request = storage_node_pb2.FileDelete(filename=chunk_name)
            response = stub.DeleteFile(request)
            if response.success:
                return 0
            else:
                raise Exception(response.message)
        
        except Exception as e:
            print(e)

 
    def chunk_to_snode(self, chunk_name):
        """Return the S-node associated with a specified chunk, or None"""
        with open(self.uuid_to_chunks, 'r') as f:
            uuid_to_chunks = json.load(f)
        
        for uuid, chunks in uuid_to_chunks.items():
            for chunk in chunks:
                if chunk == chunk_name:
                    return uuid
        
        return None
    
    def snode_to_chunk(self, target_uuid, file_name):
        """Return the chunk associated with a specified S-node and file_name, or None"""
        with open(self.uuid_to_chunks, 'r') as f:
            uuid_to_chunks = json.load(f)
        
        if target_uuid not in uuid_to_chunks:
            return None
        
        for chunk in uuid_to_chunks[target_uuid]:
            if chunk[:-2] == file_name:
                return chunk

    

    def upload_folder_to_snodes(self, folder_path: str) -> Dict[str, Tuple[str, bool]]:
        """Upload folder to n snodes, folder will have erasure coded files"""

        if not os.path.isdir(folder_path):
            print(f"Folder {folder_path} does not exist")
            return {}
            
        # Get all files in folder
        files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
        
        if not files:
            print(f"No files found in {folder_path}")
            return {}
            
        n = len(files)
        snodes = self.get_random_snodes(n)
        
        if self.aws==True:
            snodes.append("aws")
            
        if self.google == True:
            snodes.append("google")
    
        if not snodes:
            print("[ERROR] No storage nodes available for upload")
            return {}
        

        num_files_to_upload = min(len(files), len(snodes))
        
        # Upload each file to a different storage node
        results = {}
        for i in range(num_files_to_upload):
            file_path = os.path.join(folder_path, files[i])
            snode_uuid = snodes[i]
            if snode_uuid == "google":
                try:
                    google_util.upload_to_gcs(file_path)
                    success = True
                except Exception as e: 
                    success = e

            elif snode_uuid == "aws":
                try:
                    aws_util.upload(file_path)
                    success = True
                except Exception as e:
                    success = e
            else:
                success = self.upload_file_to_snode(snode_uuid, file_path)
            
        return results
        

    def get_client_list(self) -> List[Dict[str, str]]:
        """Return [{uuid, address, hostname, storage}] for all connected clients"""
        return [
            {
                'uuid': uuid, 
                'address': addr, 
                'hostname': self.storage_service.get_hostname(uuid),
                'storage': self.storage_service.client_storage_capacity.get(uuid, 0)
            }
            for uuid, addr in self.storage_service.connected_clients.items()
        ]

        
    def index_availability(self):
        """Return {filename: availability} for all stored files"""
        file_availability = {}

        all_files = self.get_files()
        if all_files:
            for file in all_files:
                file_availability[enclib.decrypt_filename(file)['original_filename']] = self.index_availability_util(file)
        
        return file_availability


    def get_files(self):
        """Return {filename: [uuids where stored]} for all stored files"""
        with open(self.file_to_uuids, 'r') as f:
            file_to_uuids = json.load(f)

        return file_to_uuids.keys()

   
    def index_availability_util(self, file_name):
        """Accept a filename, return `Yes` if available, otherwise `No`"""
        try:
            with open(self.file_to_uuids, 'r') as f:
                file_to_uuids = json.load(f)

            # List of UUIDs storing the specified filename
            relevant_uuids = file_to_uuids[file_name]
            all_connected_uuids = self.storage_service.connected_clients.keys()
            relevant_connected_uuids = []

            for uuid in all_connected_uuids:
                if uuid in relevant_uuids:
                    relevant_connected_uuids.append(uuid)

            num_available_snodes = len(relevant_connected_uuids)
            num_req_snodes = self.get_required(file_name)
            
            if num_available_snodes >= num_req_snodes:
                return "Yes"
            
            return "No"

        except Exception as e:
            print(e)
            return "Error calculating"

    def fill_storage_request(self, required_storage):
        """Return a list of uuids that have enough remaining storage
           space to store a file of the specified size
        """
        required_storage = math.ceil(required_storage / 1000000) # bytes to mb
        client_list = self.get_client_list()
        uuids_with_space = []

        with open(self.snodes_storage_used, 'r') as f:
            snodes_storage_used = json.load(f)
                
        for client in client_list:
            uuid = client["uuid"]
            if uuid == "aws" or uuid == "google":
                uuids_with_space.append(uuid)
                continue
            used_storage = snodes_storage_used[uuid] / 1000000 if uuid in snodes_storage_used else 0 # S-node used storage, MB
            storage_limit = client["storage"] # S-node tribute storage cap, MB
            available_storage = storage_limit - used_storage # MB

            if available_storage >= required_storage:
                uuids_with_space.append(uuid)
        
        return uuids_with_space

    def get_required(self, filename: str):
        """Return the required number of chunks to reconstruct the specified file"""
        try:
            meta_dir = os.path.join(os.getcwd(), "registry_conf", "meta_files")
            filename = filename + ".meta"
            meta_file = os.path.join(meta_dir, filename)
            with open(meta_file, 'r') as f:
                lines = f.readlines()
                return int(lines[3].strip()) - int(lines[2].strip())

        except Exception as e:
            print(f"[ERROR] on get_required: {e}")
    

    def get_m(self, filename: str):
        """Return the number of S-nodes a file is chunked across"""
        try:
            meta_file = os.path.join(meta_dir, filename)
            with open(meta_file, 'r') as f:
                lines = f.readlines()
                return int(lines[3].strip())
        
        except Exception as e:
            print(f"[ERROR] on get_m: {e}")
                

    def get_uuids(self):
        """Return the list of uuids of all connected S-nodes"""
        return [uuid for uuid, _ in self.storage_service.connected_clients.items()]
    

    def get_total_storage(self) -> int:
        """Return the total storage capacity across all connected S-nodes"""
        return self.storage_service.get_total_storage() 


    def get_pending_nodes(self) -> list:
        """Return the list of uuids and addresses of available S-nodes pending approval""" 
        pending_nodes = []
        
        for uuid, address in self.storage_service.pending_nodes.items():
            if self.get_pending_hostname(uuid) and self.get_pending_storage(uuid):
                pending_nodes.append({
                    'uuid': uuid,
                    'address': address
                })
        
        return pending_nodes 

    
    def clear_zombies(self):
        """Delete any files on connected S-nodes that have been deleted
           (but this change has yet to reflect remotely on the S-node)"""
        # Delete zombies: chunks deleted by the R-node while the S-node was not connected,
        # and now need to be freed for their storage space
        while True:
            try:
                with open(self.zombies, 'r') as f:
                    zombies = json.load(f) # {uuid: [zombie_chunknames]}
                with open(self.uuid_to_chunks, 'r') as f:
                    uuid_to_chunks = json.load(f)
                
                
                for client_uuid in self.get_uuids():
                    if client_uuid in zombies:
                        zombie_files = zombies[client_uuid] 
                        for file_name in zombie_files:
                            chunk_name = self.snode_to_chunk(client_uuid, file_name)
                            client_addr = self.storage_service.connected_clients[client_uuid]
                            ip = client_addr.split(':')[1]
                            port=self.storage_service.client_file_ports.get(client_uuid)
                            channel = grpc.insecure_channel(f'{ip}:{port}')
                            
                            stub = storage_node_pb2_grpc.StorageServiceStub(channel)
                            if chunk_name is None:
                                return
                            request = storage_node_pb2.FileDelete(filename=chunk_name)
                            response = stub.DeleteFile(request)

                            uuid_to_chunks[client_uuid].remove(chunk_name)
                        

                        del zombies[client_uuid] # all zombie files cleared from S-node
                
                with open(self.zombies, 'w') as f:
                    json.dump(zombies, f, indent=4)
            except Exception as e:
                print(f"Error in clear zombies: {e}")
            time.sleep(10)


if __name__ == "__main__":
    service = RegistryNode()
    service_info = service.register_service(port=12345)

    try:
        while True:
            command = input("\nEnter command (list/pending/approve/reject/help/quit/upload/download/uploadfolder): ").strip().lower()
            
            if command == "help":
                print("\nAvailable commands:")
                print("  list        - List all connected clients")
                print("  pending      - List nodes pending approval")
                print("  approve      - Approve a pending node")
                print("  reject       - Reject a pending node")
                print("  upload      - Upload a file to a storage node")
                print("  download    - Download a file from a storage node")
                print("  uploadfolder - Upload all files from a folder across storage nodes")
                print("  help        - Show this help message")
                print("  quit        - Exit the program")
                
            elif command == "list":
                client_list = service.get_client_list()
                if not client_list:
                    print("No clients connected")
                else:
                    print("\nConnected Clients:")
                    for i, client in enumerate(client_list):
                        print(f"{i}: Hostname: {client['hostname']:<15} Address: {client['address']:<15} UUID: {client['uuid']} Storage: {client['storage']} GB")
            
            elif command == "upload":
                client_list = service.get_client_list()
                if not client_list:
                    print("No storage nodes connected")
                    continue
                    
                # Display available storage nodes
                print("\nAvailable storage nodes:")
                for i, client in enumerate(client_list):
                    print(f"{i}: Address: {client['address']:<15} UUID: {client['uuid']}")
                
                # Get target node
                try:
                    node_idx = int(input("\nEnter storage node number: "))
                    if node_idx < 0 or node_idx >= len(client_list):
                        print("Invalid storage node number")
                        continue
                except ValueError:
                    print("Invalid input")
                    continue
                
                # Get filename
                filename = input("Enter filename to upload: ").strip()
                if not filename:
                    print("Invalid filename")
                    continue
                
                # Attempt upload
                target_uuid = client_list[node_idx]['uuid']
                service.upload_file_to_snode(target_uuid, filename)

            elif command == "download":
                # Get filename to download
                filename = input("Enter filename to download: ").strip()
                if not filename:
                    print("Invalid filename")
                    continue
                
                # Attempt download
                if self.download(filename):
                    print(f"Successfully downloaded {filename}")
                else:
                    print(f"Failed to download {filename}")
            
            elif command == "uploadfolder":
                # Check if there are enough storage nodes connected
                client_list = service.get_client_list()
                if not client_list:
                    print("No storage nodes connected")
                    continue
                
                # Get folder path
                folder_path = input("Enter folder path to upload: ").strip()
                if not folder_path:
                    print("Invalid folder path")
                    continue
                
                if not os.path.isdir(folder_path):
                    print(f"Folder {folder_path} does not exist")
                    continue
                
                # Count files in the folder
                files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
                
                if not files:
                    print(f"No files found in {folder_path}")
                    continue
                
                if len(files) > len(client_list):
                    print(f"Warning: Not enough storage nodes ({len(client_list)}) for all files ({len(files)})")
                    proceed = input("Continue with partial upload? (y/n): ").strip().lower()
                    if proceed != 'y':
                        continue
                
                # Upload folder to storage nodes
                results = service.upload_folder_to_snodes(folder_path)
                
                # Display results
                if results:
                    print("\nUpload results:")
                    for filename, (snode_uuid, success) in results.items():
                        status = "SUCCESS" if success else "FAILED"
                        print(f"{filename}: {status} -> Node: {snode_uuid}")
                    
                    success_count = sum(1 for _, success in results.values() if success)
                    print(f"\nSuccessfully uploaded {success_count}/{len(results)} files")
                else:
                    print("No files were uploaded")

            elif command == "pending":
                pending = service.storage_service.pending_nodes
                if not pending:
                    print("\nNo pending nodes.")
                else:
                    print("\nPending Nodes:")
                    for uuid, addr in pending.items():
                        print(f"UUID: {uuid}, Address: {addr}")

            elif command == "approve":
                uuid_to_approve = input("Enter UUID to approve: ").strip()
                pending = service.storage_service.pending_nodes
                if uuid_to_approve in pending:
                    # Approve and save node
                    service.storage_service.save_node(uuid_to_approve, "SNODE")
                    print(f"UUID {uuid_to_approve} approved successfully.")
                else:
                    print("UUID not found in pending nodes.")

            elif command == "reject":
                uuid_to_reject = input("Enter UUID to reject: ").strip()
                pending = service.storage_service.pending_nodes
                if uuid_to_reject in pending:
                    del pending[uuid_to_reject]
                    print(f"UUID {uuid_to_reject} rejected and removed from pending nodes.")
                else:
                    print("UUID not found in pending nodes.")
                    
            elif command == "storage":
                total_storage = service.get_total_storage()
                print(f"\nTotal available storage across all nodes: {total_storage} GB")

            elif command == "quit":
                break

            elif command == "pending":
                print(service.get_pending_nodes)
            else:
                print("Unknown command. Type 'help' for available commands.")
            
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        print("Unregistering service...")
        service.unregister_service(service_info)
