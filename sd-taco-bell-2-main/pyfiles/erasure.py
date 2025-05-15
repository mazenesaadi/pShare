from reedsolo import RSCodec, ReedSolomonError
import argparse
import cmd_util
import shutil
import glob
import os
import math
import sys



CHUNK_SIZE_EC = 8192

def padding(input_file_path:str,n_chunk_num=3):
    # padding size should be the difference between normal chunk and last chunk
    padding_size = os.path.getsize(f"temp/{input_file_path}_info_/{input_file_path}_enc_0") - os.path.getsize(f"temp/{input_file_path}_info_/{input_file_path}_enc_{n_chunk_num-1}")

    # if there is no need for padding just return
    if padding_size == 0: return 0
    last_chunk = open(f"temp/{input_file_path}_info_/{input_file_path}_enc_{n_chunk_num-1}","ab")
    # cast padding to one byte byte data because the way we devide, 
    # there should not be pad greater than number of encrypted chunk
    # one byte should be enough to fill out the gap, as we won't devide file into too many chunks
    byte_data= int(padding_size).to_bytes(1,'big')

    # write the pad to file to fill out the gap
    for i in range(padding_size):
        last_chunk.write(byte_data)
    last_chunk.close()

    return 1

def depad(input_file_path:str,n_chunk_num=3):
    file_name = f"temp/{input_file_path}_info_/{input_file_path}_dec_{n_chunk_num-1}"
    # get file size
    file_size = os.path.getsize(f"temp/{input_file_path}_info_/{input_file_path}_dec_{n_chunk_num-1}")
    last_chunk = open(file_name,"rb")
    # read last byte to get pad size
    last_chunk.seek(file_size-1)
    pad_data = last_chunk.read(1)
    # convert byte to int
    padding_size = int.from_bytes(pad_data,'big')
    # there should not be pad greater than number of encrypted chunk
    # if we get this case, should be no padding
    if (padding_size > n_chunk_num):
        return "Padding error"
    print(f"padding size:{padding_size}, ")
    # seek the head of the pad
    last_chunk.seek(file_size - padding_size)
    print(f"seek pos: {file_size-padding_size}")

    # read padding
    data = last_chunk.read(1)

    
    
    cnt = 0
    while data != b'':
        print(f"pad read: {data}")
        # as we write padding to fill the gap
        # content in the padding should be padding size
        # other wise padding error
        if (padding_size != int.from_bytes(data,'big')):
            print("might be a padding error, treat as no padding")
            return 
        cnt += 1
        data = last_chunk.read(1)
    # number of byte in padding should be the padding size otherwise error
    if (cnt != padding_size): 
        print("might be a padding error, treat as no padding")
        return 
    # create temporary file to record original data
    shutil.copy(file_name,"depad")
    last_chunk.close()

    temp_chunk = open("depad","rb")
    # for large file, we can only read a chunk each time, calculate how many time we need to read
    iteration = int(file_size / CHUNK_SIZE_EC)
    # to locate if padding cross the read chunk
    shift_size = 0
    # as computer division round down, if there is something left, need one more iteration
    if (file_size % CHUNK_SIZE_EC != 0):
        iteration += 1
        # if padding cross the chunk, only for remainder chunk, if no chunk left, there is no need to 
        # remove one iteration
        if (file_size % CHUNK_SIZE_EC <= padding_size) :
            iteration -= 1
            # if cross chunk, the remainder will be the padding left in the new iteration
            shift_size = file_size % CHUNK_SIZE_EC
   
    # last chunk read size should be file size - buffer block already readed (as one more iter left)
    # iteration need to -1, padding size left in the last chunk need to - remainder, and don't need 
    # to read pads, so need to - padding size
    last_read_size = file_size - (iteration-1) * CHUNK_SIZE_EC - (padding_size - shift_size)
    print(f"last read size: {last_read_size}")
    # read pad and write to file chunk used for decryption
    last_chunk = open(file_name,"wb")
    for i in range(iteration):
        if i == iteration - 1:
            temp_data = temp_chunk.read(last_read_size)
            last_chunk.write(temp_data)
        else: 
            temp_data = temp_chunk.read(CHUNK_SIZE_EC)
            last_chunk.write(temp_data)
    last_chunk.close()
    temp_chunk.close()
    # remove the temporary file
    os.remove("depad")
    return None




def fill_chunk(input_file_path:str,n_chunk_num=3,p_chunk_num=2):
    if p_chunk_num == 0: return 
    # check if all chunk are there
    missing_chunk = 0
    # to find first chunk exist, as all chunk have same size, copy one chunk to another can fill the gap
    exist_chunk_name = glob.glob(f"temp/{input_file_path}_info_/*")[0]
    # if only last chunk survives, there is too many missing chunks, as usually we won't create
    # parity chunk number = 2* normal chunk number
    if exist_chunk_name == os.path.abspath(f"temp/{input_file_path}_info_/{input_file_path}_enc_{n_chunk_num-1}"):
        raise Exception("too many missing chunk")
    
    # if miss one chunk, just copy another in
    for i in range(n_chunk_num):
        if cmd_util.check_exist(f"temp/{input_file_path}_info_/{input_file_path}_enc_{i}") == False:
            shutil.copy(exist_chunk_name,f"temp/{input_file_path}_info_/{input_file_path}_enc_{i}")
            missing_chunk+=1
    for i in range(p_chunk_num):
        if cmd_util.check_exist(f"temp/{input_file_path}_info_/{input_file_path}_par_{i}") == False:
            shutil.copy(exist_chunk_name,f"temp/{input_file_path}_info_/{input_file_path}_par_{i}")
            missing_chunk+=1
    # check if there is too many chunk missing
    if missing_chunk > p_chunk_num/2:
        raise Exception("too many missing chunk")


def encode(input_file_path:str = None,n_chunk_num:int=3,p_chunk_num:int=2):
    if p_chunk_num == 0: return 
    rsc = RSCodec(p_chunk_num)
    

    head_pos = 0
    while True:
        byte=b""
        # read one byte each time from each chunk to compute reedsolomon across different chunks
        for i in range(n_chunk_num):
            cur_file = open(f"temp/{input_file_path}_info_/{input_file_path}_enc_{i}","rb")
            cur_file.seek(head_pos)
            
            byte += cur_file.read(1)
            cur_file.close
        head_pos += 1

        if len(byte) <= 0:
            break
        # generate reedsoloman encode along the file bytes
        enc = rsc.encode(byte)
        # find where parity byte starts
        pos = len(enc) - p_chunk_num
        num = 0
        # write corresponding parity byte to corresponding chunks
        while pos < len(enc):
            par_file = open(f"temp/{input_file_path}_info_/{input_file_path}_par_{num}","ab")
            par_file.write(enc[pos:pos+1])
            par_file.close()
            num+=1
            pos+=1
        

    
def decode(input_file_path:str = None,n_chunk_num:int=3,p_chunk_num:int=2):
    if p_chunk_num == 0: return 
    rsc = RSCodec(p_chunk_num)

    head_pos = 0
    # check if too many chunks missing, and fill up missing chunks
    try:
        fill_chunk(input_file_path,n_chunk_num,p_chunk_num)
    except Exception as e:
        return e
    while True:
        byte=b""
        # read one byte each time from each chunk to compute reedsolomon across different chunks
        for i in range(n_chunk_num):
            if cmd_util.check_exist(f"temp/{input_file_path}_info_/{input_file_path}_enc_{i}"):
                cur_file = open(f"temp/{input_file_path}_info_/{input_file_path}_enc_{i}","rb")
                cur_file.seek(head_pos)
            
                byte += cur_file.read(1)
                cur_file.close()
        for i in range(p_chunk_num):
            if cmd_util.check_exist(f"temp/{input_file_path}_info_/{input_file_path}_par_{i}"):
                par_file = open(f"temp/{input_file_path}_info_/{input_file_path}_par_{i}","rb")
                par_file.seek(head_pos)
                byte += par_file.read(1)
                par_file.close()
        head_pos += 1
        # if no data read, exit the loop
        if len(byte) <= 0:
            break
        # decode the byte string
        try:
            dec = rsc.decode(byte)
        except:
            return "too many error, fail to decode"
        # write data to each file used to decrypt
        for i in range(len(dec[0])):
            out_file = open(f"temp/{input_file_path}_info_/{input_file_path}_dec_{i}","ab")
            out_file.write(dec[0][i:i+1])
            out_file.close
    return None




            
# def main(args):
#     if args.encode == True:
#         encode(input_file_path=args.filepath)
#     else:
#         decode(input_file_path=args.filepath)

# if __name__ == '__main__':
#     parser = argparse.ArgumentParser()
#     parser.add_argument('-f', '--filepath', type=str, required=True, help="file path need to be encode or decode")
#     parser.add_argument('-e','--encode',action='store_true', help="whether in encode or decode mode")
#     args = parser.parse_args()
#     main(args)


    