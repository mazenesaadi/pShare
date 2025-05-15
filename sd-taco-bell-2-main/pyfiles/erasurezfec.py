import os
import sys
import zfec
from zfec.easyfec import Encoder, Decoder
import argparse


""" As defined in https://github.com/tahoe-lafs/zfec, m is the number of parts the file is
    split into, and k is how many of those blocks are necessary to reconstruct the original
    data, such that a total of m + k chunks are produced = num_snodes.
    . Requirements: 1<=m<=256, 1<=k<=m.
    
    Algorithm used for (m,k) = f(num_snodes) is located in encrypt.py:genChunkNum """
def encode_file(input_file, output_dir, k, m):
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Read the file
    with open(input_file, 'rb') as f:
        data = f.read()
    
    # Get file size
    file_size = len(data)
    
    # Create encoder
    encoder = Encoder(k, m)
    
    # Pad the data when needed
    padding_size = 0
    if file_size % k != 0:
        padding_size = k - (file_size % k)
        data += b'\0' * padding_size
    
    # Encode the data
    chunks = encoder.encode(data)
    
    # Write the chunks to files
    for i, chunk in enumerate(chunks):
        chunk_filename = os.path.join(output_dir, f"{os.path.basename(input_file)}.{i}")
        with open(chunk_filename, 'wb') as f:
            f.write(chunk)
    
    # Write metadata file that keeps track of original file size and any padding that was added
    metadata_filename = os.path.join(output_dir, f"{os.path.basename(input_file)}.meta")
    with open(metadata_filename, 'w') as f:
        f.write(f"{file_size}\n{padding_size}\n{k}\n{m}")
    
    return True

def decode_file(chunks_dir, output_file, original_filename=None):
    # Check if original filename is provided
    if original_filename is None:
        print("Error: Original filename must be specified.")
        return False
    
    # Read metadata
    metadata_file = os.path.join("registry_conf", "meta_files", f"{original_filename}.meta")
    if not os.path.exists(metadata_file):
        print(f"Error: Metadata file {metadata_file} not found.")
        return False
    
    with open(metadata_file, 'r') as f:
        lines = f.readlines()
        original_size = int(lines[0].strip())
        padding_size = int(lines[1].strip())
        k = int(lines[2].strip())
        m = int(lines[3].strip())
    
    # Find available chunks
    chunk_files = []
    chunk_nums = []
    
    for i in range(m):
        chunk_filename = os.path.join(chunks_dir, f"{original_filename}.{i}")
        if os.path.exists(chunk_filename):
            chunk_files.append(chunk_filename)
            chunk_nums.append(i)
    
    # Check if we have enough chunks
    if len(chunk_files) < k:
        print(f"Error: Not enough chunks to reconstruct the file. Found {len(chunk_files)}, need at least {k}.")
        return False
    
    # We only need k chunks to reconstruct, so just use the first k available
    chunk_files = chunk_files[:k]
    chunk_nums = chunk_nums[:k]
    
    # Read the chunks
    chunks = []
    for chunk_file in chunk_files:
        with open(chunk_file, 'rb') as f:
            chunks.append(f.read())
    
    # Create decoder and reconstruct
    decoder = Decoder(k, m)
    decoded_data = decoder.decode(chunks, chunk_nums, padding_size)
    
    download_dir = "downloaded_files"

    output_path = os.path.join(download_dir, output_file)
    
    # Write to output file
    with open(output_path, 'wb') as f:
        f.write(decoded_data[:original_size])
    
    print(f"File successfully reconstructed as: {output_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description='Apply erasure coding to files using zfec')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    encode_parser = subparsers.add_parser('encode', help='Encode a file with erasure coding')
    encode_parser.add_argument('input_file', help='File to encode')
    encode_parser.add_argument('output_dir', help='Directory to store chunks')
    encode_parser.add_argument('-k', type=int, default=3, help='Number of chunks needed for reconstruction (default: 3)')
    encode_parser.add_argument('-m', type=int, default=5, help='Total number of chunks to create (default: 5)')
    
    decode_parser = subparsers.add_parser('decode', help='Reconstruct a file from chunks')
    decode_parser.add_argument('chunks_dir', help='Directory containing chunks')
    decode_parser.add_argument('output_file', help='Path to save reconstructed file')
    decode_parser.add_argument('--original', help='Name of the original file')
    
    args = parser.parse_args()
    
    if args.command == 'encode':
        if args.k >= args.m:
            print("Error: k must be less than m")
            return 1
        encode_file(args.input_file, args.output_dir, args.k, args.m)
    elif args.command == 'decode':
        decode_file(args.chunks_dir, args.output_file, args.original)
    else:
        parser.print_help()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())