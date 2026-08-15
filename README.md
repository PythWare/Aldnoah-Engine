# Update on Aldnoah Engine going forward

Editors will no longer be built into Aldnoah Engine from versions 2.025 onward. The reason is simple, there are other modders interested in building editors for various games AE supports. So rather than restrict those modders to coding in Python/Dart to be compatible with AE's design in versions like 2.023, AE is going to change for what it's used for. AE remains the foundational toolkit for making games it supports moddable but Editors with GUI will be built separately such as my Kybernes Tools or whatever else other modders choose to make.

Scroll down for GUI examples and instructions on using AE. Recommended/Optional Tools are listed at the bottom of the readme if you want to find other tools to use with AE

Modders that use AE, make sure to read the Compatible Mods section of this readme as it briefly explains what to tell your users which version of AE they'll need for the Mod Manager

# Aldnoah Engine

Aldnoah Engine is a PC only modding toolkit for Koei Tecmo/Omega Force games that store their assets inside large containers, use IDX files, compression wrappers, and nested subcontainers.

AE is meant to be the foundation for modding the Koei Tecmo games it supports. It can unpack game containers, decompress assets, preserve rebuild metadata, rebuild subcontainers, create mod files, apply mods, disable mods, merge mods, encrypt/decrypt files that rely on encryption, etc. AE also has a rad design, it's not enough for software to be useful, i want using AE to feel like an experience as well. More tools will be made for AE as time goes on (1 idea is filename recoverer for unpacked files since some Omega Force games do keep filenames in the executables), especially as AE grows in games it supports.

You don't need games unpacked if your only goal is to apply/disable mods (you just need to click the Generate Taildata JSON button one time), game unpacking is an optional feature for those who want to mod the files.

I HIGHLY recommend reading this readme, AE_Guide.txt (detailed guide on AE usage since the readme is getting a little long), and Aldnoah_Installer_Rules_Guide.txt (if you intend to make Aldnoah installer mods).

# Requirements

## Required

- Windows PC. AE is not supported on Linux/Mac.
- Python 3.
- Pillow.

Install Pillow with:

```
python -m pip install pillow
```

# How to Launch

Launch the GUI with:

```text
main.pyw
```

You can double click `main.pyw` or run it from command prompt.

If AE does not launch it's usually caused by Python not being installed correctly, Pillow missing, or .pyw file associations using the wrong Python. Please verify your Python installation before reporting an AE bug.

Back up your game files before using Aldnoah Engine.

# Supported Games

Currently supported PC games:

- Dynasty Warriors 7 XL
- Dynasty Warriors 8 XL
- Dynasty Warriors 8 Empires
- Warriors Orochi 3
- Warriors Orochi 4
- Bladestorm Nightmare
- Warriors All Stars
- Dragon Quest Builders 2

# release Notes of AE 2.025

AE no longer includes editors built into the toolkit, making the engine leaner but also brings new features such as Aldnoah Merger, generate Taildata JSON, and other various things such as Dart code being implemented.

Aldnoah Merger merges mods that affect the same files. 

Tools gained a new one, Generate Taildata JSON. AE will generate the taildata needed for the mod manager without needing users to unpack any games. The only ones that have to unpack the games are modders since you'd need the extracted files. Generate Taildata JSON button is useful when you need to create a taildata.json file for the Mod Manager to use, as Generate Taildata JSON button doesn'tt require games to be unpacked to create the json the Mod Manager needs.

As for the Dart code, it's not a dependency. AE uses the compiled Dart executable (dqb2_crypt_cli.exe), which means you don't need Dart installed to use AE. The Dart source (dqb2_crypt_cli.dart) in Aldnoah_Logic\dart_source is just the source code of the executable version dqb2_crypt_cli.exe. You don't need to manually use dqb2_crypt_cli.exe, AE automatically uses it for decrypting/encrypting entries that rely on encryption for Dragon Quest Builders 2. If other Omega Force developed games are found to use encryption on files, I will extend the dart code to work for other games but as of AE 2.025 I have only seen DQB2 using encryption on files stored in the containers.

# Release Notes of AE 2.024

AE 2.024 adds Dragon Quest Builders 2 as a supported game as well as a new feature for AE, taildata is no longer assigned to every unpacked file. Instead like my Conception Engine/Katsuki Engine/Gokonworks, AE now stores taildata of unpacked files in a single json for Mod Creator/Mod Manager purposes.
This means modders no longer have to deal with taildata transfer since the taildata is now in the external json.

I also made decryption/encryption code for Dragon Quest Builders 2 since the PC version does use encryption.

Toukiden Kiwami was removed as a supported game because I didn't know until recently that the PC version of Toukiden Kiwami requires an internet connection to play, something the console versions didn't. In its place is WO4.

# Main Hub

The Main Hub of AE, I suggest running Diagnostics if it's your first time using AE. It essentially verifies if the current directory AE is located in is good for usage. It may create a tiny temp file to verify write permissions but it'll be automatically deleted since its only purpose is to make sure AE has write permissions in the directory it's in. Write permissions is important since that's needed for unpacking, the modding software, etc.

<img width="1920" height="1031" alt="newae" src="https://github.com/user-attachments/assets/41b038bf-a27c-424d-a48d-0896ecb2f351" />

# Mod Creator

The Mod Creator turns modded files into mod files compatible with the Mod Manager.

<img width="1918" height="1041" alt="3" src="https://github.com/user-attachments/assets/422efb70-c7ef-4829-bf04-d2d68c57ce6d" />

<img width="1920" height="1030" alt="4" src="https://github.com/user-attachments/assets/f0669452-9b9a-49bb-8688-1c504191bde9" />

<img width="1925" height="1035" alt="5" src="https://github.com/user-attachments/assets/1981c267-da5c-47a4-b6ff-526607fa3a89" />

<img width="1919" height="1030" alt="6" src="https://github.com/user-attachments/assets/b891917b-740e-4de6-a5b7-c21cfa9a75b1" />

<img width="1915" height="1034" alt="nae2" src="https://github.com/user-attachments/assets/139b94ec-851f-42be-b30e-ff6b9d52fb54" />

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

AE 2.02 introduced `.Aldnoah`, a custom mod installer format designed for flexible mod installation.

This allows mod authors to package mods in a way that gives users more control over what parts of a mod they want to install.

# Constellation Mod Manager

AE includes the **Constellation Mod Manager**, a one of a kind mod manager built specifically for Koei Tecmo/Omega Force container based games.

Constellation understands AE's taildata system. Mods can be applied without rebuilding massive game containers (sometimes over 70 gigabytes when fully unpacked), making mod applying/disabling extremely quick.

## What makes it different

- **Container-aware modding**, applies mods directly to Koei Tecmo container/IDX structures.
- **No same-size requirement**, replacement files can be larger/smaller than the originals.
- **No forced recompression**, AE can apply decompressed replacement payloads when the game accepts them.
- **Safe disable support**, original IDX entries are saved in a ledger and restored when disabling mods.
- **Disable All support**, restores tracked IDX entries and truncates containers back to their original sizes.
- **Single-file and package mods**, supports both one file mods and multi file releases. 2.02 onward supports the .Aldnoah mod installer format I have designed.
- **Metadata-rich mods**, supports mod name, author, version, description, preview images, genre, and theme audio.
- **Mod Collision Detection**, detects mod collisions and creates a red web between colliding mods to show collision.
- **Conflict Inspector**, optional feature for inspecting why some mods may collide.
- **Visual mod library**, mods are displayed as stars in a constellation style interface instead of a plain list. Mods automatically connect with mods with the same genre and form a constellation, when a constellation is full but more mods exist new constellations form.

Constellation is designed to be unique, original, and defying the norms/expectations of mod managers. It doesn't simply overwrite files. It appends modded payloads to the correct container, updates the IDX entry, records the original state, and gives the user a way back.

# Constellation Mod Manager

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

# Compatible Mods

AE 2.025 onward supports v2, v3, and v4 for mod formats. If you're not sure what mod format your single, package, or installer mod was made in just open up the Mod Manager, select the mod, and look at what is displayed beside `Format:`. 2.025 uses the v4 format but 2.025 is designed to be backwards compatible with older mod formats (v2/v3, which AE versions 2.023 and 2.0243 used). So if you're making mods with AE 2.023 or 2.0243, just tell your users to download the latest version of AE since they need the Mod Manager for applying the mods.

# Aldnoah Merger

As explained above, this handles merging of mods. Suppose mod 1 and mod 2 edit the same files, without merging, the last applied mod would overwrite the other mod. Now, you can use Aldnoah Merger to merge mods that mod the same files. This allows modders to merge mods that contain the same files in them.

<img width="1920" height="1033" alt="newae2" src="https://github.com/user-attachments/assets/d09368a8-5b4d-4686-8d45-9cf7efe9ba2b" />

<img width="1916" height="1032" alt="newae3" src="https://github.com/user-attachments/assets/9db513ba-ba65-427a-8cbf-c6563c39b022" />

# Important Concept, AE Taildata

When AE unpacks files from the main game containers, it appends data to an external json named after the game AE was used for to unpack. Don't delete the json unless you know what you're doing.

The Mod Manager uses json/taildata to know:

- which IDX file/entry belongs to the extracted file,
- which container should receive the modded payload,
- where to patch the game to load the replacement,
- how to safely disable or restore mods later.

Taildata does not interfere with normal modding. You can still edit files as usual.

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
7. AE rebuilds the subcontainer.

For nested formats, AE can rebuild supported child containers before rebuilding the parent.

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

- Extremely deep unpacking can produce hundreds of thousands of files.

# Editors (only for AE versions 2.023 and older, newer versions of AE don't bundle editors as part of the toolkit as explained at the top of the readme)

AE includes 25 Editors for the various games it supports. Each editor supports modding the unpacked files and includes multi-select modding as an optional feature which makes batch modding easier. 

After using an editor you'll need to rebuild the subcontainer the generated file was originally part of (i.e., using NPC Tactic Editor for DW8E generates 003.xl, you'd place that new XL file within the original directory of the unpacked files which in this case would be DW8E_Unpacked\Pack_00\entry_00000), after you paste the modded file in the subcontainer's directory it belonngs to click Rebuild Subcontainer and turn the rebuilt subcontainer into a Mod Manager compatibile mod with Mod Creator.

## To use multi-select 

Select one slot normally, Shift+click another slot in the populated list to select the range, then edit through the multi-slot popup. Mixed fields are left untouched unless you replace Mixed Value. You can use decimal or hex values.

# Credit

Credit goes to Kanbei and Zebuta for allowing me to include their txt file documentation on names and values for Warriors Orochi 3 and Bladestorm Nightmare, Credit also goes to The Tempest who spent time helping me identify maps based on their models. More Credit also goes to TwistZero for their documentation on Dynasty Warriors 8 Packs and Manny for gifting me Warriors Orochi 4 as well as his info on WO4's unit data.

Credit also goes to default.kramer for gifting me Dragon Quest Builders 2, without their contribution I probably wouldn't have looked into supporting DQB2.

Credit goes to sapphire and playinful for informing me of DQB2 using encryption, their sample files helped me solve the encryption used for DQB2

# Extra Notes

If you encounter issues or have questions contact me through GitHub, Reddit, or Discord but please make sure you read the readme, AE_Guide.txt, and Aldnoah_Installer_Rules_Guide.txt first since those answer a lot of questions already.

If Koei Tecmo has any issue with Aldnoah Engine, please contact me so I can comply. AE is intended for modding offline games so players and modders can keep enjoying them long after official support ends.

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
