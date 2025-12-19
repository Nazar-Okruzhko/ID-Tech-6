import struct
import sys
import os
import math

# ============= CONFIGURATION =============
HEADER_SIZE = 64
BUFFER_MARKERS = (
    b'\x01\x01\x00\x00\x00\x00\x00\x00',
    b'\x01\x01\x00\x00\x00\x10\x00\x00'
)
SKIP_TO_VERTEX_COUNT = 19
SKIP_TO_FACE_COUNT = 2
SKIP_TO_FIRST_VERTEX = 26
VERTEX_STRIDE = 48

# ============= USER OPTIONS =============
ROTATE_X_MINUS_90 = True
FLIP_UV_MAPS = True
FLIP_FACE_ORIENTATION = True
SHADE_SMOOTH = True
# ==========================================

def read_int16_le(data, offset):
    """Read little-endian 16-bit integer"""
    return struct.unpack('<H', data[offset:offset+2])[0]

def read_float_le(data, offset):
    """Read little-endian 32-bit float"""
    return struct.unpack('<f', data[offset:offset+4])[0]

def rotate_x_minus_90(vertices):
    rotated = []
    for x, y, z in vertices:
        new_x = x
        new_y = z
        new_z = -y
        rotated.append((new_x, new_y, new_z))
    return rotated

def flip_uvs(uvs):
    return [(u, 1.0 - v) for u, v in uvs]

def flip_faces(faces):
    return [(f[0], f[2], f[1]) for f in faces]

def calculate_vertex_normals(vertices, faces):
    normals = [[0.0, 0.0, 0.0] for _ in vertices]

    for face in faces:
        v0 = vertices[face[0]]
        v1 = vertices[face[1]]
        v2 = vertices[face[2]]

        edge1 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
        edge2 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])

        nx = edge1[1] * edge2[2] - edge1[2] * edge2[1]
        ny = edge1[2] * edge2[0] - edge1[0] * edge2[2]
        nz = edge1[0] * edge2[1] - edge1[1] * edge2[0]

        for idx in face:
            normals[idx][0] += nx
            normals[idx][1] += ny
            normals[idx][2] += nz

    normalized_normals = []
    for n in normals:
        length = math.sqrt(n[0]**2 + n[1]**2 + n[2]**2)
        if length > 0.0:
            normalized_normals.append((n[0]/length, n[1]/length, n[2]/length))
        else:
            normalized_normals.append((0.0, 0.0, 1.0))

    return normalized_normals

def apply_transforms(model_data):
    if ROTATE_X_MINUS_90:
        print("[TRANSFORM] Applying X-axis -90° rotation...")
        model_data['vertices'] = rotate_x_minus_90(model_data['vertices'])

    if FLIP_UV_MAPS:
        print("[TRANSFORM] Flipping UV maps...")
        model_data['uvs'] = flip_uvs(model_data['uvs'])

    if FLIP_FACE_ORIENTATION:
        print("[TRANSFORM] Flipping face orientation...")
        model_data['faces'] = flip_faces(model_data['faces'])

    if SHADE_SMOOTH:
        print("[TRANSFORM] Calculating smooth vertex normals...")
        model_data['normals'] = calculate_vertex_normals(
            model_data['vertices'], model_data['faces']
        )
    else:
        model_data['normals'] = None

    return model_data

def find_buffer_marker(data, start_offset=0):
    marker_len = len(BUFFER_MARKERS[0])

    for i in range(start_offset, len(data) - marker_len + 1):
        for marker in BUFFER_MARKERS:
            if data[i:i+marker_len] == marker:
                return i, marker

    return -1, None

def extract_model(data, start_search_offset, part_number=1):
    print(f"\n{'='*60}")
    print(f"Extracting Part {part_number}")
    print(f"{'='*60}\n")

    marker_offset, marker = find_buffer_marker(data, start_search_offset)
    if marker_offset == -1:
        print(f"[INFO] No more buffer markers found (searched from offset 0x{start_search_offset:X})")
        return None, -1

    print(f"[INFO] Buffer marker found at offset: 0x{marker_offset:X} ({marker_offset})")

    offset = marker_offset + len(BUFFER_MARKERS)

    offset += SKIP_TO_VERTEX_COUNT
    vertex_count = read_int16_le(data, offset)
    print(f"[INFO] Vertex count offset: 0x{offset:X} ({offset})")
    print(f"[INFO] Vertex count: {vertex_count}")
    offset += 2

    offset += SKIP_TO_FACE_COUNT
    face_count = read_int16_le(data, offset)
    print(f"[INFO] Face count offset: 0x{offset:X} ({offset})")
    print(f"[INFO] Face count: {face_count}")
    offset += 2

    offset += SKIP_TO_FIRST_VERTEX
    print(f"[INFO] First vertex offset: 0x{offset:X} ({offset})")

    vertices = []
    uvs = []

    print(f"\n[DEBUG] First 5 vertices and UV coords (interleaved):")
    for i in range(vertex_count):
        x = read_float_le(data, offset)
        y = read_float_le(data, offset + 4)
        z = read_float_le(data, offset + 8)
        vertices.append((x, y, z))

        u = read_float_le(data, offset + 12)
        v = read_float_le(data, offset + 16)
        uvs.append((u, v))

        if i < 5:
            print(f"  Entry{i+1} at 0x{offset:X}:")
            print(f"    Vertex: ({x:.6f}, {y:.6f}, {z:.6f})")
            print(f"    UV: ({u:.6f}, {v:.6f})")

        offset += VERTEX_STRIDE

    print(f"[INFO] Extracted {len(vertices)} vertices")
    print(f"[INFO] Extracted {len(uvs)} UV coordinates")

    print(f"[INFO] Face data offset: 0x{offset:X} ({offset})")

    faces = []
    print(f"\n[DEBUG] First 5 faces (as triangles):")

    for i in range(face_count):
        idx1 = read_int16_le(data, offset)
        idx2 = read_int16_le(data, offset + 2)
        idx3 = read_int16_le(data, offset + 4)
        faces.append((idx1, idx2, idx3))

        if i < 5:
            print(f"  F{i+1}: ({idx1}, {idx2}, {idx3}) at offset 0x{offset:X}")

        offset += 6

    print(f"[INFO] Extracted {len(faces)} faces")

    return {
        'vertices': vertices,
        'uvs': uvs,
        'faces': faces,
        'vertex_count': vertex_count,
        'face_count': face_count
    }, offset

def write_obj(model_data, output_file):
    print(f"\n[INFO] Writing to {output_file}...")

    with open(output_file, 'w') as f:
        f.write("# Extracted from .bmd6model\n")
        f.write(f"# Vertices: {model_data['vertex_count']}\n")
        f.write(f"# Faces: {model_data['face_count']}\n")
        if SHADE_SMOOTH:
            f.write("# Smooth shading: ON\n")
        f.write("\n")

        for v in model_data['vertices']:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")

        if model_data.get('normals'):
            f.write("\n")
            for n in model_data['normals']:
                f.write(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")

        f.write("\n")
        for uv in model_data['uvs']:
            f.write(f"vt {uv[0]:.6f} {uv[1]:.6f}\n")

        f.write("\n")
        for face in model_data['faces']:
            if model_data.get('normals'):
                f.write(
                    f"f {face[0]+1}/{face[0]+1}/{face[0]+1} "
                    f"{face[1]+1}/{face[1]+1}/{face[1]+1} "
                    f"{face[2]+1}/{face[2]+1}/{face[2]+1}\n"
                )
            else:
                f.write(
                    f"f {face[0]+1}/{face[0]+1} "
                    f"{face[1]+1}/{face[1]+1} "
                    f"{face[2]+1}/{face[2]+1}\n"
                )

    print("[SUCCESS] OBJ file written successfully!")

def main():
    print("\n" + "="*60)
    print("BMD6Model to OBJ Converter")
    print("="*60)

    if len(sys.argv) < 2:
        print("\n[USAGE] Drag and drop a .bmd6model file onto this script")
        input("\nPress Enter to exit...")
        return

    input_file = sys.argv[1]
    if not os.path.exists(input_file):
        print(f"[ERROR] File not found: {input_file}")
        input("\nPress Enter to exit...")
        return

    model_name = os.path.splitext(os.path.basename(input_file))[0]
    output_folder = os.path.join(os.path.dirname(input_file), model_name)
    os.makedirs(output_folder, exist_ok=True)

    with open(input_file, 'rb') as f:
        file_data = f.read()

    part_number = 1
    search_offset = HEADER_SIZE

    while True:
        model_data, next_offset = extract_model(file_data, search_offset, part_number)
        if model_data is None:
            break

        model_data = apply_transforms(model_data)
        output_file = os.path.join(output_folder, f"{model_name}_part{part_number}.obj")
        write_obj(model_data, output_file)

        part_number += 1
        search_offset = next_offset

    print("\nConversion complete!")
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
