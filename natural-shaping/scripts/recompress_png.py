"""Recompress PNG IDAT only; preserve every ancillary/header chunk byte for byte."""
import hashlib
import json
import struct
import zlib
from pathlib import Path

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
IDAT_SIZE = 1024 * 1024


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def recompress(source, destination):
    if destination.exists():
        raise FileExistsError(destination)
    temp = destination.with_suffix(".png.partial")
    source_hash = file_hash(source)
    decoder = zlib.decompressobj()
    encoder = zlib.compressobj(9)
    scanline_hash = hashlib.sha256()
    buffered = bytearray()
    decoded_bytes = 0
    saw_idat = stream_done = saw_iend = False
    width = height = depth = color = None

    with source.open("rb") as src, temp.open("xb") as dst:
        if src.read(8) != PNG_SIGNATURE:
            raise ValueError("Bad PNG signature")
        dst.write(PNG_SIGNATURE)

        def emit(payload):
            dst.write(struct.pack(">I", len(payload)))
            dst.write(b"IDAT")
            dst.write(payload)
            dst.write(struct.pack(">I", zlib.crc32(payload, zlib.crc32(b"IDAT"))))

        def buffer_compressed(data, final=False):
            buffered.extend(data)
            while len(buffered) >= IDAT_SIZE:
                emit(bytes(buffered[:IDAT_SIZE]))
                del buffered[:IDAT_SIZE]
            if final and buffered:
                emit(bytes(buffered))
                buffered.clear()

        def feed(raw):
            nonlocal decoded_bytes
            decoded_bytes += len(raw)
            scanline_hash.update(raw)
            buffer_compressed(encoder.compress(raw))

        def finish_stream():
            nonlocal stream_done
            feed(decoder.flush())
            if not decoder.eof or decoder.unused_data:
                raise ValueError("PNG image zlib stream is incomplete or has trailing data")
            buffer_compressed(encoder.flush(), final=True)
            stream_done = True

        while not saw_iend:
            header = src.read(8)
            if len(header) != 8:
                raise ValueError("Missing IEND")
            size, kind = struct.unpack(">I4s", header)
            payload = src.read(size)
            crc_bytes = src.read(4)
            if len(payload) != size or len(crc_bytes) != 4:
                raise ValueError("Truncated PNG chunk")
            expected = struct.unpack(">I", crc_bytes)[0]
            if zlib.crc32(payload, zlib.crc32(kind)) != expected:
                raise ValueError("Invalid input CRC: " + repr(kind))

            if kind == b"IDAT":
                if stream_done:
                    raise ValueError("Nonconsecutive IDAT chunks")
                saw_idat = True
                feed(decoder.decompress(payload))
                continue

            if saw_idat and not stream_done:
                finish_stream()
            if kind == b"IHDR":
                width, height, depth, color, comp, filt, interlace = struct.unpack(">IIBBBBB", payload)
                if depth not in (8, 16) or color not in (2, 6) or comp != 0 or filt != 0 or interlace != 0:
                    raise ValueError("Expected noninterlaced RGB/RGBA8/16 PNG")
            elif kind == b"IEND":
                if size != 0 or not saw_idat:
                    raise ValueError("Invalid IEND")
                saw_iend = True
            # Keep IHDR, ICC, metadata, IEND, and their original CRC bytes untouched.
            dst.write(header)
            dst.write(payload)
            dst.write(crc_bytes)

        if src.read(1):
            raise ValueError("Unexpected bytes after IEND")

    if decoded_bytes != height * (width * (3 if color == 2 else 4) * (depth // 8) + 1):
        raise ValueError("Unexpected PNG scanline size")
    if file_hash(source) != source_hash:
        raise ValueError("Source changed during compression")
    temp.rename(destination)
    result = {
        "source": str(source), "output": str(destination),
        "dimensions": [width, height], "depthBits": depth, "colorType": color,
        "sourceBytes": source.stat().st_size, "outputBytes": destination.stat().st_size,
        "sourceMiB": round(source.stat().st_size / 1048576, 2),
        "outputMiB": round(destination.stat().st_size / 1048576, 2),
        "reductionPercent": round(100 * (1 - destination.stat().st_size / source.stat().st_size), 1),
        "sourceSha256": source_hash, "outputSha256": file_hash(destination),
        "decodedScanlineBytes": decoded_bytes, "sourceScanlineSha256": scanline_hash.hexdigest(),
        "method": "IDAT zlib compression level 9 only; all other chunks copied unchanged",
    }
    print(json.dumps(result), flush=True)
    return result



def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.report:
        forbidden = {args.source.resolve(), args.output.resolve(), args.output.with_suffix('.png.partial').resolve()}
        if args.report.resolve() in forbidden or args.report.exists():
            parser.error('Report must be a new path distinct from input and output')
    result = recompress(args.source, args.output)
    if args.report:
        with args.report.open('x', encoding='utf-8') as handle:
            json.dump({'status': 'compressed_pending_pixel_verification', 'image': result}, handle, indent=2)


if __name__ == '__main__':
    main()

