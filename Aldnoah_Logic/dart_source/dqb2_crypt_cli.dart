import 'dart:io';
import 'dart:typed_data';

const int MULT = 0x6C078965;
const int INCR = 0x3039;
const int MASK32 = 0xFFFFFFFF;
const int SEED_BASE = 0xF7114F36;

void transformInPlace(Uint8List data, int entryIndex) {
  if (data.isEmpty) return;

  int seed = (SEED_BASE + entryIndex) & MASK32;
  int state = seed;
  int remaining = data.length;
  int i = 0;

  while (remaining > 0) {
    if (remaining >= 2) {
      state = (state * MULT + INCR) & MASK32;

      if (((state >> 16) & 1) == 1) {
        state = (state * MULT + INCR) & MASK32;
        int key = (state >> 16) & 0xFFFF;

        data[i] ^= (key & 0xFF);
        data[i + 1] ^= ((key >> 8) & 0xFF);

        i += 2;
        remaining -= 2;
        continue;
      }
    }

    state = (state * MULT + INCR) & MASK32;
    int d = (state >> 16) & 0xFFFF;

    data[i] ^= (((d >> 8) & 0xFF) ^ (d & 0xFF));

    i += 1;
    remaining -= 1;
  }
}

Uint8List readWholeFile(String path) {
  return Uint8List.fromList(File(path).readAsBytesSync());
}

Uint8List readContainerSlice(String path, int offset, int length) {
  RandomAccessFile handle = File(path).openSync(mode: FileMode.read);
  try {
    handle.setPositionSync(offset);
    Uint8List data = Uint8List(length);
    int got = handle.readIntoSync(data);
    if (got != length) {
      throw Exception('read $got of $length bytes at offset $offset in $path');
    }
    return data;
  } finally {
    handle.closeSync();
  }
}

void main(List<String> arguments) {
  if (arguments.length == 3) {
    int entryIndex = int.parse(arguments[0]);
    Uint8List data = readWholeFile(arguments[1]);
    transformInPlace(data, entryIndex);
    File(arguments[2]).writeAsBytesSync(data);
    return;
  }

  if (arguments.length == 5) {
    int entryIndex = int.parse(arguments[0]);
    int offset = int.parse(arguments[2]);
    int length = int.parse(arguments[3]);
    Uint8List data = readContainerSlice(arguments[1], offset, length);
    transformInPlace(data, entryIndex);
    File(arguments[4]).writeAsBytesSync(data);
    return;
  }

  stderr.writeln('usage: dqb2_crypt_cli <entryIndex> <inPath> <outPath>');
  stderr.writeln('   or: dqb2_crypt_cli <entryIndex> <containerPath> <offset> <length> <outPath>');
  exit(2);
}
