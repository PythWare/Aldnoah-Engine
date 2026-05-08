# Aldnoah Engine

Aldnoah Engine is a PC only modding toolkit for Koei Tecmo/Omega Force games that store their assets inside large containers, use IDX files, compression wrappers, and nested subcontainers.

AE is meant to be the foundation for modding the Koei Tecmo games it supports. It can unpack game containers, decompress assets, preserve rebuild metadata, rebuild subcontainers, create mod files, apply mods, disable mods, and launch built-in editors/tools for supported game data.

AE uses a Tkinter GUI and currently only requires Python and Pillow.

You don't need games unpacked if your only goal is to apply/disable mods, game unpacking is an optional feature for those who want to mod the files.

I HIGHLY recommend reading this readme, AE_Guide.txt (detailed guide on AE usage since the readme is getting a little long), and Aldnoah_Installer_Rules_Guide.txt (if you intend to make Aldnoah installer mods).

# Requirements

## Required

- Windows PC. AE is not supported on Linux/Mac.
- Python 3.
- Pillow.

Install Pillow with:

```
pip install pillow
```

# How to Launch

Launch the GUI with:

```text
main.pyw
```

You can double click `main.pyw` or run it from command prompt.

Back up your game files before using Aldnoah Engine.

# Credit

Credit goes to Kanbei and Zebuta for allowing me to include their txt file documentation on names and values for Warriors Orochi 3 and Bladestorm Nightmare, Credit also goes to The Tempest who spent time helping me identify maps based on their models. More Credit also goes to TwistZero for their documentation on Dynasty Warriors 8 Packs and Manny for gifting me Warriors Orochi 4 as well as his info on WO4's unit data.

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
- **Mod Collision Detection**, detects mod collisions and creates a red web between colliding mods to show collision.
- **Conflict Inspector**, optional feature for inspecting why some mods may collide.
- **Visual mod library**, mods are displayed as stars in a constellation style interface instead of a plain list. Mods automatically connect with mods with the same genre and form a constellation, when a constellation is full but more mods exist new constellations form.

Constellation is designed to be unique, original, and defying the norms/expectations of mod managers. It doesn't simply overwrite files. It appends modded payloads to the correct container, updates the IDX entry, records the original state, and gives the user a way back.

# Release Notes of AE 2.02

AE 2.02 is a major expansion. It adds deeper editor support, new modding systems, stronger subcontainer handling, and major GUI upgrades.

2.02 features include:

- 25 built-in editors for supported games (more editors will be made in 2.03).
- Improved Constellation Mod Manager GUI.
- Custom `.Aldnoah` mod installer format I designed.
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

Toukiden Kiwami was removed as a supported game because I didn't know until recently that the PC version of Toukiden Kiwami requires an internet connection to play, something the console versions didn't. In its place is WO4.

WO4 doesn't have any editors included in 2.02 since it was added at the last moment as a supported game, expect WO4 editors in AE 2.03 along with more modding software.

# Upcoming Features for AE 2.03

AE 2.03 will bring new features such as DW9 added as a supported game, more audio modding support for other games, more built-in editors, etc.

# Main Hub

The Main Hub of AE, I suggest running Diagnostics if it's your first time using 2.02. It essentially verifies if the current directory AE is located in is good for usage. It may create a tiny temp file to verify write permissions but it'll be automatically deleted since its only purpose is to make sure AE has write permissions in the directory it's in. Write permissions is important since that's needed for unpacking, the modding software, etc.

<img width="1917" height="1033" alt="1" src="https://github.com/user-attachments/assets/ba18e4d2-860c-48cf-b59e-4780933d0e9f" />

# Editors

AE 2.02 includes 25 Editors for the various games it supports. Each editor supports modding the unpacked files and includes multi-select modding as an optional feature which makes batch modding easier. 

After using an editor you'll need to rebuild the subcontainer the generated file was originally part of (i.e., using NPC Tactic Editor for DW8E generates 002.xl, you'd place that new XL file within the original directory of the unpacked files which in this case would be DW8E_Unpacked\Pack_00\entry_00000), after you paste the modded file in the subcontainer's directory it belonngs to click Rebuild Subcontainer and turn the rebuilt subcontainer into a Mod Manager compatibile mod with Mod Creator.

## To use multi-select 

Select one slot normally, Shift+click another slot in the populated list to select the range, then edit through the multi-slot popup. Mixed fields are left untouched unless you replace Mixed Value. You can use decimal or hex values.

Some sample images that show some of the editors (including a screenshot of every editor would bloat the readme).

<img width="1920" height="1033" alt="7" src="https://github.com/user-attachments/assets/d4ace773-0451-42c3-8811-5f50c6c8cee0" />

<img width="1920" height="1033" alt="8" src="https://github.com/user-attachments/assets/99cd382a-fda2-4ce6-ab71-394ba45a047a" />

<img width="1920" height="1031" alt="9" src="https://github.com/user-attachments/assets/0266c033-ff41-490f-a4ad-684ad57cba5a" />

<img width="1920" height="1030" alt="10" src="https://github.com/user-attachments/assets/51d5bc46-0e98-4f87-a474-173f169f124c" />

<img width="1914" height="1044" alt="11" src="https://github.com/user-attachments/assets/a45de2c3-4fba-48cc-af05-0624e59e1d76" />

# Mod Creator 2.02

The Mod Creator turns modded files into mod files compatible with the Mod Manager.

<img width="1918" height="1041" alt="3" src="https://github.com/user-attachments/assets/422efb70-c7ef-4829-bf04-d2d68c57ce6d" />

<img width="1920" height="1030" alt="4" src="https://github.com/user-attachments/assets/f0669452-9b9a-49bb-8688-1c504191bde9" />

<img width="1925" height="1035" alt="5" src="https://github.com/user-attachments/assets/1981c267-da5c-47a4-b6ff-526607fa3a89" />

<img width="1919" height="1030" alt="6" src="https://github.com/user-attachments/assets/b891917b-740e-4de6-a5b7-c21cfa9a75b1" />

<img width="1920" height="1043" alt="2" src="https://github.com/user-attachments/assets/841ae4ec-b33b-4908-8c7b-ac9810ced447" />

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

## Custom `.Aldnoah` Mod Installers

AE 2.02 introduces `.Aldnoah`, a custom mod installer format designed for flexible mod installation.

This allows mod authors to package mods in a way that gives users more control over what parts of a mod they want to install.

# Mod Manager 2.02

The Mod Manager applies/disables AE mods and has a lot of features.

Use the mousewheel to zoom in and out, hold left click to move around the galaxy, click mods to preview and choose to enable/disable, etc.

If you'd rather find a mod quickly instead of moving around the galaxy, just type the mod's name in the Signal bar which will locate/take you to the mod directly for quick access.

<img width="1910" height="1035" alt="14" src="https://github.com/user-attachments/assets/3cbe1d38-1aa8-4127-b5a4-910542f8e8db" />

<img width="1915" height="1028" alt="15" src="https://github.com/user-attachments/assets/6b58d619-db2b-4236-8bb9-31d0e316e700" />

<img width="1912" height="1041" alt="12" src="https://github.com/user-attachments/assets/da76d2fb-4219-44af-a990-9b0319abc691" />

<img width="1916" height="1031" alt="13" src="https://github.com/user-attachments/assets/3a232cfc-f51c-4e12-9828-54d0f3b1fe42" />

It doesn't rebuild the original large game containers, that's inefficient and not needed. Instead it:

1. Splits the mod payload from AE taildata.
2. Appends the modded payload to the correct game container.
3. Aligns appended data as needed.
4. Updates the recorded IDX entry to point to the new payload.
5. Lets the game load the modded file instead of the original.

This makes mod applying/disabling faster and safer than rewriting entire game containers.

## Mod Collision detection

Constellation Mod Manager can detect mod collisions, when it does it'll create a red web that connects the colliding mods to show a collision. Users can still choose to apply mods even if there's a detected collision.

## Conflict Inspector

Conflict Inspector is an optional feature that allows you to inspect why a mod collides with another. Suppose you want to enable a mod but it has detected collision with another mod you have enabled, you can
click Inspect Conflict and a popup of Conflict Inspector will show what files within the mods are colliding.

## Disable Mod/Disable All

The Mod Manager can disable individual mods or disable all mods.

Disable All truncates containers back to their original sizes.

## Recommended/Optional Tools

### Noesis/Project G1M

Noesis and Joschuka's Project G1M scripts are recommended for viewing/converting many G1M/G1T files:

https://github.com/Joschuka/Project-G1M

G1M/G1T formats vary across Koei Tecmo games so porting files between games may require extra work.

### eArmada8 Gust Tools

eArmada8 made tools for Gust game formats that can also be useful for some Koei Tecmo assets:

https://github.com/eArmada8/gust_stuff

### Kybernes Tools

Kybernes Tools is recommended alongside AE for extra modding workflows, scanning tools, Editors, and audio related tools.

https://github.com/PythWare/Kybernes-Tools

For audio modding, Harklight from Kybernes Tools may be needed for replacing or creating audio such as voices, sounds, music, etc.

### Batch Binary File Scanner

For searching through large unpacked folders, use Batch Binary File Scanner:

https://github.com/PythWare/Batch-Binary-File-Scanner

AE extracts many files with generated names because many later Koei Tecmo games strip, hide, or obfuscate original filenames. A binary scanner makes research/modding much easier.

# Supported Games

Currently supported PC games:

- Dynasty Warriors 7 XL
- Dynasty Warriors 8 XL
- Dynasty Warriors 8 Empires
- Warriors Orochi 3
- Warriors Orochi 4
- Bladestorm Nightmare
- Warriors All Stars

# What Aldnoah Engine can do

AE can:

- Unpack game containers.
- Decompress compressed entries.
- Detect and handle Omega Force split-zlib layouts.
- Preserve 6 byte AE taildata for mod manager compatibility.
- Deep unpack many subcontainers.
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

As of AE 2.02 full KVS audio replacing/adding is supported for:

- Warriors Orochi 3

Other supported games will receive KVS metadata support in later versions.

# Handling G1M/G1T replacements

Some later Koei Tecmo games perform checks on certain models. Directly swapping some NPC/non-playable models into playable slots in something like cheat engine can crash the game.

AE can help work around this through taildata, 2.02 has a 'Transfer Taildata' button. Make sure to read the AE_Guide.txt file for more info on transferring taildata.

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

# Extra Notes

If you encounter issues or have questions contact me through GitHub, Reddit, or Discord but please make sure you read the readme, AE_Guide.txt, and Aldnoah_Installer_Rules_Guide.txt first since those answer a lot of questions already.

If Koei Tecmo has any issue with Aldnoah Engine, please contact me so I can comply. AE is intended for modding offline games so players and modders can keep enjoying them long after official support ends.
