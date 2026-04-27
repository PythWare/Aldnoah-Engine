# Aldnoah Engine

Aldnoah Engine is a PC only modding toolkit for Koei Tecmo/Omega Force games that store their assets inside large containers, use IDX files, compression wrappers, and nested subcontainers.

AE is meant to be the foundation for modding the Koei Tecmo games it supports. It can unpack game containers, decompress assets, preserve rebuild metadata, rebuild subcontainers, create mod files, apply mods, disable mods, and launch built-in editors/tools for supported game data.

AE uses a Tkinter GUI and currently only requires Python and Pillow.

# Requirements

## Required

- Windows PC.
- Python 3.
- Pillow.

Install Pillow with:

```
pip install pillow
```

# Constellation Mod Manager

AE includes the **Constellation Mod Manager**, a one of a kind mod manager built specifically for Koei Tecmo/Omega Force container based games.

Unlike normal mod managers that copy loose files into folders, Constellation understands AE's taildata system. Every compatible mod file carries the information needed to locate the original IDX entry, append the new payload to the correct game container, patch the game to load the replacement, and restore the original IDX data when the mod is disabled.

This means mods can be applied without rebuilding massive game containers (sometimes over 70 gigabytes when fully unpacked).

## What makes it different

- **Container-aware modding**, applies mods directly to Koei Tecmo container/IDX structures.
- **No same-size requirement**, replacement files can be larger/smaller than the originals.
- **No forced recompression**, AE can apply decompressed replacement payloads when the game accepts them.
- **Safe disable support**, original IDX entries are saved in a ledger and restored when disabling mods.
- **Disable All support**, restores tracked IDX entries and truncates containers back to their original sizes.
- **Single-file and package mods**, supports both one file mods and multi file releases. 2.02 will support the .Aldnoah mod installer format I have designed.
- **Metadata-rich mods**, supports mod name, author, version, description, preview images, genre, and theme audio.
- **Visual mod library**, mods are displayed as stars in a constellation style interface instead of a plain list. Mods automatically connect with mods with the same genre and form a constellation, when a constellation is full but more mods exist new constellations form.

Constellation is designed to be unique, original, and defying the norms/expectations of mod managers. It doesn't simply overwrite files. It appends modded payloads to the correct container, updates the IDX entry, records the original state, and gives the user a way back.

# Upcoming AE 2.02

AE 2.02 is a major expansion. It adds deeper editor support, new modding systems, stronger subcontainer handling, and major GUI upgrades.

Planned/in-progress 2.02 features include:

- 30+ built-in editors for supported games.
- Improved Constellation Mod Manager GUI.
- Custom `.Aldnoah` mod installer support.
- Flexible mod packages where users can choose what to install.
- Better visual collision detection between mods.
- Support for companion tools and editors such as:
  - **Heaven's Fall Editor**, a 3D map modding tool that supports displaying the maps with their models, modding maps, creating new maps, etc. Think of it as a level/map modding/generating tool. You'll be able to create custom maps.
  - **Marylcian Editor**, G1M modding tool, similar in spirit to Skyrim Bodyslide but designed for G1M files broadly including characters, items, buildings, and other models.
  - **Barouhcruz Editor**, G1A/G2A animation handling tool, animates G1M models and supports modding animation files.
  - **Saazbaum Editor**, Motion/ATK data handling editor.
  - **Rayregalia Editor**, Shader tooling.

The names are inspired by *Aldnoah.Zero*.

Later versions may use compiled Dart (so that you don't need Dart installed, keeping it lightweight since Dart can compile to executables) for some heavy logic while keeping the GUI lightweight. The goal is still to ship finished tools without making users install extra language runtimes beyond what AE itself requires.

# Screenshots/Sneak peeks for 2.02

<img width="1913" height="1036" alt="a6" src="https://github.com/user-attachments/assets/2932a2e3-e27b-473d-b164-9e533d7b4730" />

<img width="1911" height="1036" alt="a7" src="https://github.com/user-attachments/assets/bf7c734b-348a-4236-ad6b-0cc0449b1528" />

<img width="1915" height="1030" alt="a9" src="https://github.com/user-attachments/assets/a4cc1809-a681-4385-b8e6-12d318ad0c22" />

<img width="1915" height="1036" alt="a13" src="https://github.com/user-attachments/assets/dda18339-95ce-4338-8e79-f9d460e89f06" />

<img width="1917" height="1031" alt="a10" src="https://github.com/user-attachments/assets/6aab5ef3-45fd-4a75-b8d7-3f2d68d20e14" />

<img width="1920" height="1036" alt="a11" src="https://github.com/user-attachments/assets/21f77390-da79-441a-8034-79208b3d0e44" />

<img width="1911" height="1038" alt="a12" src="https://github.com/user-attachments/assets/d414fdba-7cc0-4dcf-af5e-6a25363de3ff" />

<img width="1916" height="1043" alt="a1" src="https://github.com/user-attachments/assets/b9db9e90-1f8c-486a-9ae1-c423ff9a7821" />

<img width="1916" height="1035" alt="a2" src="https://github.com/user-attachments/assets/55457b61-dac3-462d-bc0e-c0acf279d755" />

<img width="1914" height="1042" alt="a3" src="https://github.com/user-attachments/assets/540314fe-9989-4256-ba48-ebbfc26ee789" />

<img width="1918" height="1037" alt="a4" src="https://github.com/user-attachments/assets/63cca846-c434-4e7a-8b06-bd0f96a85bc9" />

<img width="1475" height="1025" alt="ae2" src="https://github.com/user-attachments/assets/b46db0a3-0cd8-41f9-807a-562359d31143" />

<img width="1222" height="1022" alt="ae3" src="https://github.com/user-attachments/assets/fcfba97e-726e-4d9e-8b10-7c874dff24c0" />

<img width="1286" height="1000" alt="ae4" src="https://github.com/user-attachments/assets/ad4a6c35-533b-4f10-8a88-17d13e9991a4" />

## Recommended/Optional Tools

### Noesis/Project G1M

Noesis and Joschuka's Project G1M scripts are recommended for viewing/converting many G1M/G1T files:

https://github.com/Joschuka/Project-G1M

G1M/G1T formats vary across Koei Tecmo games so porting files between games may require extra work.

### eArmada8 Gust Tools

eArmada8 made tools for Gust game formats that can also be useful for some Koei Tecmo assets:

https://github.com/eArmada8/gust_stuff

### Kybernes Tools

Kybernes Tools is recommended alongside AE for extra modding workflows, scanning tools, Editors, and audio-related tools.

https://github.com/PythWare/Kybernes-Tools

For audio modding, Harklight from Kybernes Tools may be needed for replacing or creating audio such as voices, sounds, music, etc.

### Batch Binary File Scanner

For searching through large unpacked folders, use Batch Binary File Scanner:

https://github.com/PythWare/Batch-Binary-File-Scanner

AE extracts many files with generated names because many later Koei Tecmo games strip, hide, or obfuscate original filenames. A binary scanner makes research/modding much easier.

# Supported Games

Currently supported PC games:

- Toukiden Kiwami
- Dynasty Warriors 7 XL
- Dynasty Warriors 8 XL
- Dynasty Warriors 8 Empires
- Warriors Orochi 3
- Bladestorm Nightmare
- Warriors All Stars

# How to Launch

Launch the GUI with:

```text
main.pyw
```

You can double click `main.pyw` or run it from command prompt.

Back up your game files before using Aldnoah Engine.

# What Aldnoah Engine can do

AE can:

- Unpack game containers.
- Decompress compressed entries.
- Detect and handle Omega Force split-zlib layouts.
- Preserve 6 byte AE taildata for mod manager compatibility.
- Deep-unpack many subcontainers.
- Rebuild subcontainers from folders.
- Rebuild nested subcontainers before rebuilding their parent containers.
- Repack KVS audio subcontainers.
- Update KVS metadata for supported games.
- Create mod files.
- Apply and disable mods.
- Append modded payloads to containers instead of rebuilding entire main game archives (rebuilding 20-70+ GB games is inefficent if you can append instead).
- Support dynamic file sizes.
- Launch built-in editors and companion tools.

Modded files do **not** need to be the same size as the originals. AE supports larger and smaller replacements.

# Important Concept, AE Taildata

When AE unpacks files from the main game containers, it appends a tiny 6 byte guide called **taildata**.

Taildata contains:

```text
1 byte  = IDX marker
4 bytes = IDX entry offset
1 byte  = compression marker
```

The Mod Manager uses this taildata to know:

- which IDX file/entry belongs to the extracted file,
- which container should receive the modded payload,
- where to patch the game to load the replacement,
- how to safely disable or restore mods later.

Do **not** remove taildata unless you know exactly what you are doing.

Taildata does not interfere with normal modding. You can still edit files as usual.

## Taildata and Subcontainers

Files extracted from inside subcontainers usually do **not** receive standalone taildata. That is intentional.

The taildata belongs to the subcontainer file itself because the game expects the rebuilt subcontainer to be applied back as one modded file.

Example:

```text
entry_00149.bin   <- has AE taildata
entry_00149/      <- unpacked subcontainer folder
  000.MDLK        <- inner file, usually no standalone AE taildata
  000/            <- unpacked MDLK contents
    000.g1m
    001.g1m
```

To mod inner files replace the files inside the subfolder, rebuild the subcontainer, then apply the rebuilt parent file through the Mod Manager.

---

# Subcontainers

Many Omega Force games use subcontainers. Some have obvious signatures while many are signatureless and can only be recognized through structure.

AE attempts to deeply unpack these so modders can reach the actual files inside.

Subcontainers may contain:

- regular files,
- KVS audio chunks,
- model bundles,
- shader bundles,
- split-zlib wrapped resources,
- nested subcontainers,
- empty placeholder slots used for indexing.

A full unpack can produce a very large number of files, that is is normal. AE is trying to preserve the structure needed for lossless rebuilding.

## Nested Subcontainers

Some subcontainers contain more subcontainers. AE creates same name folders for these.

Example:

```text
entry_00280.bin
entry_00280/
  005.KSHL
  005/
    000.vsh
    001.vsh
    002.psh
```

When rebuilding, AE works bottom up:

```text
rebuild inner folders first
insert rebuilt inner files into parent
rebuild parent offsets/sizes
preserve parent taildata for Mod Manager use
```

You do **not** need to manually select every inner folder. Select the parent subcontainer folder and its original/base file. AE will rebuild known nested child formats automatically when the matching child folder exists.

## Empty files

Don't delete empty files created during subcontainer unpacking.

Some empty files represent real index slots. Removing them can shift file order and break rebuilding.

## Extra files warning

When rebuilding a subcontainer, don't leave unrelated extra files inside the folder being rebuilt.

If a subcontainer originally has 100 payload slots, the rebuild folder should contain the 100 files that belong to those slots. Extra files can cause file count mismatches or incorrect rebuilds.

---

# Rebuilding Subcontainers

To rebuild a subcontainer:

1. Find the subcontainer folder created by AE.
2. Replace/edit files inside that folder as needed.
3. Keep the original filenames unless you know the format allows otherwise.
4. Use AE's subcontainer rebuild option.
5. Select the subcontainer folder.
6. Select the original/base subcontainer file.
7. AE rebuilds the subcontainer and preserves/reapplies taildata when needed.

For nested formats, AE can rebuild supported child containers before rebuilding the parent.

Supported rebuild targets include:

- Generic signatureless subcontainers.
- KVS subcontainers.
- Split zlib wrappers.
- Classic split zlib resources.
- MDLK model link bundles.
- KSHL shader bundles.

# MDLK Model Bundles

MDLK files are model link style bundles. They can contain G1M and G1C payloads.

AE can unpack MDLK into its child files and rebuild the MDLK after replacements.

When replacing files inside MDLK:

- Keep filenames the same.
- Don't delete placeholder/empty slots if AE created them.
- Rebuild the MDLK or the parent subcontainer that contains it.

AE patches the embedded size fields for G1M/G1C payloads when rebuilding.

# KSHL Shader Bundles

KSHL files are shader bundle/library containers used by Koei Tecmo games.

AE can unpack KSHL files into shader payloads such as:

- `.vsh` vertex shader blobs,
- `.psh` pixel shader blobs,
- `.bin` unknown/unsupported shader-like payloads.

KSHL rebuild support is intended for replacing same slot shader payloads while preserving the original container structure.

Shader editing is still an advanced workflow. Rayregalia Editor is planned for deeper shader tooling.

# Mod Creator

The Mod Creator turns edited files into mod files compatible with the Mod Manager.

<img width="1221" height="1011" alt="AE3" src="https://github.com/user-attachments/assets/42a7b09b-081a-4e2c-bc25-a62d0e09ee21" />
<img width="1912" height="1012" alt="AE4" src="https://github.com/user-attachments/assets/5877510d-2ca4-434f-805f-0da6fbba3115" />

AE supports:

## Single Mod

A single modded file payload.

Use this when your mod changes one file.

## Package Mod

Multiple file payloads packed into one mod release.

Use this for larger mods that change many files.

Recommended package workflow:

1. Create a clean folder for the mod package.
2. Place only the final modded files in that folder.
3. Don't include unnecessary subdirectories unless the tool specifically expects them.
4. Use Mod Package to create the release file.

Mod Creator can include metadata such as:

- mod name,
- author,
- version,
- description,
- preview images,
- theme audio.

---

# Mod Manager

The Mod Manager applies/disables AE mods.

<img width="1218" height="1009" alt="AE5" src="https://github.com/user-attachments/assets/7b04555e-d302-43ee-9f2a-4ef8b578501f" />
<img width="1946" height="1041" alt="AE6" src="https://github.com/user-attachments/assets/e85840bd-2a08-46c9-a514-491090c245ed" />
<img width="1920" height="1038" alt="AE7" src="https://github.com/user-attachments/assets/6b462972-f964-447d-8d00-7dd6d5d14a11" />
<img width="1917" height="1035" alt="AE8" src="https://github.com/user-attachments/assets/dba0ddd7-79e6-4480-b1ea-850ebc9fd988" />

It doesn't rebuild the original large game containers, that's inefficient and not needed. Instead it:

1. Splits the mod payload from AE taildata.
2. Appends the modded payload to the correct game container.
3. Aligns appended data as needed.
4. Updates the recorded IDX entry to point to the new payload.
5. Lets the game load the modded file instead of the original.

This makes mod applying/disabling faster and safer than rewriting entire game containers.

## Disable Mod/Disable All

The Mod Manager can disable individual mods or disable all mods.

Disable All truncates containers back to their original sizes.

# Custom `.Aldnoah` Mod Installers

AE 2.02 introduces `.Aldnoah`, a custom mod installer format designed for flexible mod installation.

This allows mod authors to package mods in a way that gives users more control over what parts of a mod they want to install.

# Audio Modding

KVS audio can appear in different forms depending on the game.

Some KVS files are loose single audio files while others are large KVS subcontainers holding hundreds/thousands of sequential KVS chunks.

Example:

```text
entry_00000.kvs
entry_00000/
  000.kvs
  001.kvs
  002.kvs
  ...
```

To replace audio inside a KVS subcontainer:

1. Find the KVS subcontainer folder.
2. Replace the target `.kvs` file with your new `.kvs` file.
3. Keep the replacement filename exactly the same as the original.
4. Rebuild the KVS subcontainer.
5. Use Update KVS Metadata if the game requires it.
6. Use Mod Creator to package the rebuilt KVS subcontainer.
7. Apply it with Mod Manager.

## KVS Metadata Support

As of AE 2.016 full KVS audio replacing/adding is supported for:

- Warriors Orochi 3

Other supported games will receive KVS metadata support in later versions.

# Handling G1M/G1T replacements

Some later Koei Tecmo games perform checks on certain models. Directly swapping some NPC/non-playable models into playable slots in something like cheat engine can crash the game.

AE can help work around this through taildata, 2.02 will have a 'Transfer Taildata' button but for version 2.016 the taildata transfer has to be done manually.

## Loose G1M/G1T Files

If the model/texture files are loose files:

1. Find the playable base character you want to replace.
2. Copy the last 6 bytes from that character's G1M file.
3. Paste those 6 bytes over the last 6 bytes of the replacement G1M.
4. Repeat the same process for the matching G1T.
5. Build the mod with Mod Creator.
6. Apply with Mod Manager.

This makes AE apply the replacement through the base character's IDX targets.

## Files inside Subcontainers

Do **not** copy taildata from files extracted inside subcontainers.

If the files came from a subcontainer:

1. Replace the inner files directly.
2. Keep filenames the same.
3. Rebuild the subcontainer.
4. Apply the rebuilt subcontainer.

Short version:

```text
Loose file: use taildata transfer if needed.
Subcontainer file: replace inside folder and rebuild the subcontainer.
```

# Logs/Warnings

## `comp_log.txt`

You may see messages like:

```text
zlib decompress failed at IDX entry ... wrote raw to entry_XXXXX.bin
```

This usually means Omega Force marked a file as compressed in the IDX but the file data was not actually compressed in the expected way.

That isn't an AE error, it may be a mistake that happened during the game's development process.

# Performance Notes

Some games unpack very large numbers of files. That is normal especially when deep subcontainer unpacking is enabled.

Unpacking can take several minutes or longer depending on:

- game size,
- number of container entries,
- compression,
- nested subcontainer depth,
- SSD vs HDD

If the progress bar appears stuck, it isn't. It may still be working through heavy subcontainer/decompression logic.

For best results, unpack to a SSD.

# Current known limitations

- Full KVS metadata updating is currently only supported for Warriors Orochi 3.
- Extremely deep unpacking can produce hundreds of thousands of files.
- Later versions of AE will add more editors and format specific tools.

# AE 2.016 Release Notes

AE 2.016 was a major overhaul for unpacking code, subcontainer handling, and mod tools.

Major 2.016 changes included:

- Deeper subcontainer unpacking.
- More extracted files due to nested subcontainer support.
- Repack flow for subcontainers using folders and source/base files.

# Extra Notes

Kybernes Tools is my other repository for standalone tools that pair with AE including Festum Conversion, Wild Liberd, Kybernes Scanner, Harklight, and other Koei Tecmo modding utilities.

https://github.com/PythWare/Kybernes-Tools

If you encounter issues or have questions contact me through GitHub, Reddit, or Discord.

If Koei Tecmo has any issue with Aldnoah Engine, please contact me so I can comply. AE is intended for modding offline games so players and modders can keep enjoying them long after official support ends.

