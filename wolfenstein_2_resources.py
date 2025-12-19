#!/usr/bin/env python3
"""
Wolfenstein II: The New Colossus Archive Extractor
Ported from QuickBMS script by Luigi Auriemma
"""

import os
import sys
import struct
from pathlib import Path

OODLE_AVAILABLE = False
oodle_decompress = None

# Configuration
EXTRACT_GARBAGE = False  # Skip small files without extensions in root

def load_oodle():
    """Try to load Oodle DLL for decompression"""
    global OODLE_AVAILABLE, oodle_decompress
    try:
        import ctypes
        dll_names = [
            'oo2core_9_win64.dll',
            'oo2core_8_win64.dll',
            'oo2core_7_win64.dll',
            'oo2core_6_win64.dll',
            'oo2core_5_win64.dll',
        ]
        
        search_paths = ['.']
        if len(sys.argv) > 1:
            archive_dir = os.path.dirname(os.path.abspath(sys.argv[1]))
            search_paths.append(archive_dir)
            current = archive_dir
            for _ in range(3):
                parent = os.path.dirname(current)
                if parent == current:
                    break
                search_paths.append(parent)
                current = parent
        
        oodle_dll = None
        for path in search_paths:
            for dll_name in dll_names:
                dll_path = os.path.join(path, dll_name)
                if os.path.exists(dll_path):
                    try:
                        oodle_dll = ctypes.CDLL(dll_path)
                        print(f"Loaded Oodle DLL: {dll_name}")
                        break
                    except:
                        continue
            if oodle_dll:
                break
        
        if not oodle_dll:
            return False
        
        OodleLZ_Decompress = oodle_dll.OodleLZ_Decompress
        OodleLZ_Decompress.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_int
        ]
        OodleLZ_Decompress.restype = ctypes.c_int
        
        def decompress_oodle(data, decompressed_size):
            output = ctypes.create_string_buffer(decompressed_size)
            result = OodleLZ_Decompress(
                data, len(data), output, decompressed_size,
                0, 0, 0, None, 0, None, None, None, 0, 3
            )
            if result <= 0:
                raise Exception(f"Decompression failed with code {result}")
            return bytes(output[:decompressed_size])
        
        oodle_decompress = decompress_oodle
        OODLE_AVAILABLE = True
        return True
        
    except Exception as e:
        print(f"Could not load Oodle DLL: {e}")
        return False


def read_cstring(f):
    """Read null-terminated string"""
    chars = []
    while True:
        c = f.read(1)
        if not c or c == b'\x00':
            break
        chars.append(c)
    return b''.join(chars).decode('utf-8', errors='ignore')


def sanitize_filename(name):
    """Sanitize filename by removing invalid characters"""
    name = name.replace('$', '_')
    name = name.replace('#', '_')
    name = name.replace('<', '_')
    name = name.replace('>', '_')
    name = name.replace(':', '_')
    name = name.replace('|', '_')
    name = name.replace('?', '_')
    name = name.replace('*', '_')
    name = name.replace('"', '_')
    return name


def is_garbage_file(filename, size):
    """Check if file is garbage (small file without extension in root)"""
    if not EXTRACT_GARBAGE:
        if '/' not in filename and '\\' not in filename:
            if '.' not in filename:
                if size < 100:
                    return True
    return False


def extract_resources(filepath):
    """Extract .resources, .pack and similar files"""
    output_dir = Path(filepath).stem
    os.makedirs(output_dir, exist_ok=True)
    
    with open(filepath, 'rb') as f:
        magic = f.read(4)
        if magic != b'IDCL':
            print(f"Error: Invalid magic number. Expected 'IDCL', got {magic}")
            return
        
        version = struct.unpack('<I', f.read(4))[0]
        print(f"Archive version: {version}")
        
        f.read(8)
        f.read(4)
        f.read(4)
        f.read(4)
        f.read(4)
        f.read(8)
        
        files_count = struct.unpack('<I', f.read(4))[0]
        dummy_num = struct.unpack('<I', f.read(4))[0]
        dummy2_num = struct.unpack('<I', f.read(4))[0]
        files_2 = struct.unpack('<I', f.read(4))[0]
        
        f.read(8)
        f.read(8)
        
        names_off = struct.unpack('<Q', f.read(8))[0]
        dummy4_off = struct.unpack('<Q', f.read(8))[0]
        info_off = struct.unpack('<Q', f.read(8))[0]
        dummy6_off = struct.unpack('<Q', f.read(8))[0]
        dummy7_off = struct.unpack('<Q', f.read(8))[0]
        data_off = struct.unpack('<Q', f.read(8))[0]
        
        print(f"Files to extract: {files_count}")
        
        f.seek(names_off)
        names_count = struct.unpack('<Q', f.read(8))[0]
        
        name_offsets = []
        for i in range(names_count):
            name_off = struct.unpack('<Q', f.read(8))[0]
            name_offsets.append(name_off)
        
        names_base = f.tell()
        names = [""] * names_count
        
        for i, name_off in enumerate(name_offsets):
            f.seek(names_base + name_off)
            name = read_cstring(f)
            
            if '_lodgroup=' in name:
                name = name.split('_lodgroup=')[0]
            if '_streamdb=' in name:
                name = name.split('_streamdb=')[0]
            if '_group=' in name:
                name = name.split('_group=')[0]
            
            if '.' in name:
                parts = name.rsplit('.', 1)
                basename = parts[0]
                extension = parts[1]
                if '_' in extension:
                    extension = extension.split('_')[0]
                name = basename + '.' + extension
            
            name = sanitize_filename(name)
            names[i] = name
        
        f.seek(dummy7_off)
        for i in range(dummy2_num):
            f.read(4)
        dummy7_off = f.tell()
        
        f.seek(info_off)
        extracted = 0
        skipped = 0
        
        for i in range(files_count):
            f.read(8)
            f.read(8)
            f.read(8)
            
            type_id = struct.unpack('<Q', f.read(8))[0]
            name_id = struct.unpack('<Q', f.read(8))[0]
            
            f.read(8)
            f.read(8)
            
            offset = struct.unpack('<Q', f.read(8))[0]
            zsize = struct.unpack('<Q', f.read(8))[0]
            size = struct.unpack('<Q', f.read(8))[0]
            
            f.read(8)
            f.read(4)
            f.read(4)
            f.read(8)
            f.read(4)
            f.read(4)
            
            zip_flags = struct.unpack('<Q', f.read(8))[0]
            
            f.read(8)
            f.read(4)
            f.read(4)
            f.read(8)
            
            current_pos = f.tell()
            
            type_idx = type_id * 8 + dummy7_off
            name_idx = (name_id + 1) * 8 + dummy7_off
            
            f.seek(type_idx)
            type_str_id = struct.unpack('<Q', f.read(8))[0]
            
            f.seek(name_idx)
            name_str_id = struct.unpack('<Q', f.read(8))[0]
            
            f.seek(current_pos)
            
            str2 = names[name_str_id] if name_str_id < names_count else ""
            
            filename = str2 if str2 else f"file_{i:08d}.dat"
            filename = filename.replace('\\', '/')
            
            if is_garbage_file(filename, size):
                skipped += 1
                continue
            
            output_path = Path(output_dir) / filename
            
            if output_path.exists() and output_path.is_dir():
                output_path = Path(str(output_path) + '.file')
            
            if '.' not in filename.split('/')[-1]:
                output_path = Path(str(output_path) + '.file')
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            f.seek(offset)
            
            if size == zsize:
                data = f.read(size)
                with open(output_path, 'wb') as out:
                    out.write(data)
            else:
                actual_offset = offset
                actual_zsize = zsize
                
                if zip_flags & 4:
                    if not (zip_flags & 1):
                        actual_offset += 12
                        actual_zsize -= 12
                
                f.seek(actual_offset)
                compressed_data = f.read(actual_zsize)
                
                if OODLE_AVAILABLE and oodle_decompress:
                    try:
                        decompressed = oodle_decompress(compressed_data, size)
                        with open(output_path, 'wb') as out:
                            out.write(decompressed)
                    except Exception as e:
                        print(f"Warning: Failed to decompress {filename}: {e}")
                        compressed_path = str(output_path) + '.compressed'
                        with open(compressed_path, 'wb') as out:
                            out.write(compressed_data)
                else:
                    compressed_path = str(output_path) + '.compressed'
                    with open(compressed_path, 'wb') as out:
                        out.write(compressed_data)
            
            f.seek(current_pos)
            extracted += 1
            
            if extracted % 100 == 0:
                print(f"Extracted {extracted}/{files_count} files...")
        
        print(f"\nExtraction complete! {extracted} files extracted, {skipped} garbage files skipped")
        print(f"Output folder: '{output_dir}'")


def main():
    print("Wolfenstein II: The New Colossus Archive Extractor")
    print("=" * 50)
    
    if len(sys.argv) < 2:
        print("\nUsage: Drag and drop a .resources or .pack file onto this script")
        print("       or run: python script.py <archive_file>")
        input("\nPress Enter to exit...")
        return
    
    filepath = sys.argv[1]
    
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        input("\nPress Enter to exit...")
        return
    
    ext = Path(filepath).suffix.lower()
    
    if ext == '.texdb':
        print("Error: .texdb files are no longer supported")
        input("\nPress Enter to exit...")
        return
    
    if not load_oodle():
        print("\nWarning: Oodle DLL not found. Compressed files will be saved with .compressed extension")
        print("To decompress files, the DLL should be in the game folder.\n")
    
    try:
        extract_resources(filepath)
    except Exception as e:
        print(f"\nError during extraction: {e}")
        import traceback
        traceback.print_exc()
    
    input("\nPress Enter to exit...")


if __name__ == '__main__':
    main()
