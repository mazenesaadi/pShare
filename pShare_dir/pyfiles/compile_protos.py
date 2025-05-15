from grpc_tools import protoc
import os

def compile_protos():
    current_dir = os.path.dirname(os.path.abspath(__file__))

    proto_file = os.path.join(current_dir, 'protos', 'file_service.proto')
    
    output_dir = os.path.join(current_dir, 'protos')
    
    protoc.main([
        'grpc_tools.protoc',
        f'--proto_path={os.path.join(current_dir, "protos")}',
        f'--python_out={output_dir}',
        f'--grpc_python_out={output_dir}',
        proto_file
    ])
    
    print("Proto files compiled")

if __name__ == '__main__':
    compile_protos()