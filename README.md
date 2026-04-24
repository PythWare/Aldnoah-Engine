# AE 2.015 Release Info

Aldnoah Engine 2.015 is released, it's a massive overhaul not just for the GUI but also the code for unpacking and other various things. Included are innovative features that only Aldnoah Engine has as of March 18 2026, the Constellation Mod Manager (the first of its kind, a truly unique mod manager unlike any other). Make sure to read the readme, it contains guides and info on how to use.

# Changes in 2.015

MANY subcontainers get deep unpacking, which nows leads to more files being unpacked. The repack process for subcontainers is the same as before you just select the subcontainer folder to rebuild and then the source subcontainer itself (i.e., entry_00000 folder and entry_00000.bin), you don't need to select the subfolders for the smaller subcontainers that get unpacked from the subcontainer.

Since some subcontainers have smaller subcontainers within them, AE will unpack those smaller subcontainers into the folder that belongs to the main subcontainer. So the subcontainer rebuilding as explained above is the same as before, merely more files get unpacked now.

# Aldnoah Engine Info
Aldnoah Engine is a PC-only modding toolkit for Koei Tecmo games that store assets in containers and IDX pairs. AE is meant to be the foundation, establishing the modding ecosystem for games it supports. It ships with a Tkinter GUI that lets you unpack/decompress game files with taildata, repack subcontainers, and launch a built-in Mod Creator and Mod Manager. When you unpack, Aldnoah Engine appends a tiny 6 byte taildata guide to each extracted file which is a 1 byte idx_marker, 4 bytes idx_entry_offset, and a 1 byte comp_marker. The Mod Manager uses that taildata to know exactly which IDX entry to patch and which container to append to, then it can also restore/disable mods safely later.

Modded files do not have to be the same size as the original, Aldnoah Engine supports dynamic file sizes so if your mod is larger/smaller than the original file/files that's not an issue. Another thing, the Mod Manager can apply mods without needing to recompress the files. The games can load decompressed versions of compressed assets.

<img width="1475" height="948" alt="ae1" src="https://github.com/user-attachments/assets/5cae2e98-d41e-418d-8c8d-5f636ddbd402" />

# What is needed

Python 3 installed, also Pillow which is a Python Imaging Library. To install Pillow, open a command prompt and type `pip install pillow`

If you want to make audio mods (replacing/adding new audio such as voiced audio, sounds, music, etc) you will need Harklight which is in my Kybernes Tools repository https://github.com/PythWare/Kybernes-Tools

Noesis and specifically Joschuka's noesis files (https://github.com/Joschuka/Project-G1M) are needed if you want to view/convert G1M/G1T files. It's important to know the G1M/G1T formats have changed over the years across games so porting G1M/G1T files from other Koei Tecmo games may require some additional legwork. eArmada8 made a G1M tool for gust games that also works for other Koei Tecmo games so you may want to view it as well https://github.com/eArmada8/gust_stuff.

G1T Krieger (my tool for modding G1T files as well as converting them) will be released at a later date so for now rely on Noesis/eArmada8's G1T tool until G1T Krieger releases.

# How to use Aldnoah Engine

Launch the GUI via main.pyw. You can double click it or run through cmd but i'd just double click the file. I highly recommend backing up your game files before using Aldnoah Engine.

# Supported games (currently only PC games)

Toukiden Kiwami, Dynasty Warriors 7 XL, Dynasty Warriors 8 XL, Dynasty Warriors 8 Empires, Warriors Orochi 3, Bladestorm Nightmare, and Warriors All Stars.

# What can be done

Unpack/decompress assets from the containers.

Append mods/files to the end of containers and updating IDX entries to tell the games to read from new offsets instead (Mod Manager section will explain more).

Detect and handle split-zlib streams (when Omega Force compresses chunks of sections across a file rather than compressing all of a single file's data as 1 blob) via structure checks.

Repack subcontainers from a folder. If the folder contains .kvs chunks then it builds a KVS container otherwise it builds a signatureless subcontainer. It can also pull taildata from a chosen base file and append it to the output for mod manager compatibility.

Eventually built in Editors for modding files, over 30+ editors tbh.

# Types of mods that can be made

A lot, we have the same modding potential as larger modding communities like Xenoverse 2. To do any file mods you have to have access to the files, which AE gives. Too many types of mods to list, so the quick rundown is since we can access the files we have the ability to mod game assets and replace them with other assets. However Aldnoah Engine is a tool suite for unpacking, decompressing, repacking, appending, and applying/disabling mods through Mod Manager. So essentially, a tool suite to access the files and apply/disable modded files. Separate GUI tools like Unit Data Editors (handles parameters like stats, motion/moveset, model, etc), Stage Data Editors (handles battlefield parameters like which troops/officers appear in the stage, coordinates of where units spawn, etc), and other GUI tools will be made separately.

# Mod Creator

Creates mod files by turning modded files into compatible files with the Mod Manager. Also has some metadata support like author of the mod, naming mod file, version of your mod, description, preview images, theme audio, etc.

Single mod = 1 file payload

Package mod = N file payloads

Both use a consistent header, size, and data payload format I designed. If you're doing a single file mod use single file, if you're making large scale mods that mod more than 1 file I suggest using Package mod button.

When using Mod Package, I suggest selecting a folder that contains only the files you want applied to the game within the folder (i.e., if I want to mod unitdata and apply audio mods i'd create a mod folder, place all the files in there I want applied to the game and then use mod package). Mod Package gets all the files within the folder selected and turns it into a single file release, you don't need subdirectories within a folder that is meant to store mods to turn into package mods, only the files themselves.

<img width="1221" height="1011" alt="AE3" src="https://github.com/user-attachments/assets/42a7b09b-081a-4e2c-bc25-a62d0e09ee21" />
<img width="1912" height="1012" alt="AE4" src="https://github.com/user-attachments/assets/5877510d-2ca4-434f-805f-0da6fbba3115" />

# Mod Manager

Applies/disables mods, splits payload from trailing taildata, appends payload to containers with 16 byte alignment, patches the IDX entry at the recorded offset, and supports Disable All (including truncating containers back to original sizes, use this when wanting to disable all mods). The Mod Manager does not rebuild containers, that is inefficient. Instead it appends your modded files to the end of the containers, updates the IDX files which then makes the game load the modded files rather than the original unmodded files. This ensures quick, easy, and safe mod applying/disabling.

<img width="1218" height="1009" alt="AE5" src="https://github.com/user-attachments/assets/7b04555e-d302-43ee-9f2a-4ef8b578501f" />
<img width="1946" height="1041" alt="AE6" src="https://github.com/user-attachments/assets/e85840bd-2a08-46c9-a514-491090c245ed" />
<img width="1920" height="1038" alt="AE7" src="https://github.com/user-attachments/assets/6b462972-f964-447d-8d00-7dd6d5d14a11" />
<img width="1917" height="1035" alt="AE8" src="https://github.com/user-attachments/assets/dba0ddd7-79e6-4480-b1ea-850ebc9fd988" />


# Taildata

It is essential that unless you know what you're doing, you must not remove taildata. Taildata is 6 bytes of data added to every unpacked file (not files unpacked from subcontainers since subcontainer unpacked files get repacked, they don't need taildata) that is used by the Mod Manager for applying/disabling mods. Taildata does not impact the usability/moddability of files so mod away without worry. To clarify on subcontainers, the subcontainers have taildata but the files unpacked from the subcontainers won't and shoudn't have taildata since you're not applying those individual files to the game, you're applying a repacked subcontainer since that is what the game expects.

# Audio Modding

KVS files unpacked may be loose or a subcontainer, it varies and that's just how Koei Tecmo designed KVS files. So some KVS files extracted may be loose solo KVS files, some may be a big KVS file that actually stores thousands of sequentially stored KVS files (which in that case, they're unpacked into a folder named after the KVS subcontainer such as entry_00000 which pairs with entry_00000.kvs as an example, that subcontainer stores 9,750 KVS files).

To replace audio, place your new kvs files within the folder of the kvs subcontainer you want to rebuild (i.e., entry_00000 folder which has 9,750 kvs files, if you wanted to replace audio files from it you'd replace the files within it with yours). Name your new kvs files after the kvs files you want to replace (i.e., let's say 024.kvs belongs to xiahou dun and you want to replace with a new voiced audio, name your new voiced audio 024.kvs and replace the original kvs within the subfolder). It's important you place your KVS files into the subcontainer folder before running subcontainer repacking. So let's say you want to dub Orochi 3, you'd replace each Japanese KVS file within the subcontainers with your KVS file named after the file it's replacing and then rebuild with aldnoah engine. After that you click the "Update KVS Metadata" button in the main GUI (and naturally follow the instructions the popup says), use Mod Creator for the KVS subcontainer/subcontainers to turn into a mod file/package when you finish with Updating KVS Metadata, and then apply with Mod Manager.

The Update KVS Metadata button only supports Warriors Orochi 3 for now, i'll try adding support for the other 6 games.

<img width="1203" height="1031" alt="AE9" src="https://github.com/user-attachments/assets/8dac59ae-5a6c-47a4-ad06-531ba16b7023" />

# Subcontainer Info

It's essential that subfolders (named after the file it belongs to) for repacking don't have extra files stored within the folder selected for repacking (i.e., let's say entry_00000 folder has 100 files, don't have more than 100 files in there when you click subcontainer repacking, only keep the 100 files you want repacked in this example whether it's the original 100 or the originals mixed with files you modded/replaced). It's also important that you don't delete empty files generated during unpacking/repacking, those empty files are used for indexing when repacking files.

# Games that support full KVS Audio replacing/adding as of version 2.015

Warriors Orochi 3. You could literally dub the entire game with English audio or other languages, or just replace audio files if your goal isn't dubbing. Orochi 3 has full support as of version 2.015. Other games will be supported for audio modding in later versions.

# Things to keep in mind

Each subcontainer unpacked will create a folder named after the subcontainer file which stores the subcontainer's unpacked files.

Depending on the game the unpacking may take a few minutes. If the status bar seems stuck to you, it isn't. It's doing a lot of unpacking/decompressing (as well as subcontainer handling which is what takes the longest), Orochi 3 has over 181k files so some games may take a few minutes to unpack. If you're unpacking to a HDD instead of SSD that may impact speed but either way, the bar will not stay stuck unless you tampered with the containers/idx files on your own before using AE.

You may see a comp_log.txt file. It'll probably have some lines saying things like "zlib decompress failed at IDX entry 5903 (BIN=LINKFILE_000.BIN, offset=0x170ABA00, size=0x25): Could not find a valid Omega-style zlib_header stream in blob; wrote raw to entry_03655.bin", that means Omega Force tagged a file with the compression marker in the IDX file, that's not an issue on your part or AE. No idea why Omega Force has some files marked as compressed that aren't compressed. Just ignore those kind of warnings, it's basically saying a file was flagged as compressed by the IDX file but isn't compressed.

Use Batch Binary File Scanner (a tool I made) to scan through files quickly/easily. To help with finding specific files since files are extracted with incrementing filenames (a lot of the later Koei Tecmo games either strip filenames from the executable or obfuscate them, so Aldnoah Engine unpacks with incrementing filenames and extensions based on the file's data) and there will be thousands of files unpacked, I suggest using my Batch Binary File Scanner that scans binary files in the selected directory and all subdirectories within it. The link is https://github.com/PythWare/Batch-Binary-File-Scanner

Most Omega Force games have signatureless subcontainers it seems, this is more documentation for those curious. They do have some containers with signatures but most subcontainers seem to be signatureless.

# Handling G1M/G1T Replacing

Some later Koei Tecmo games perform checks on certain models. If you swap in a non-playable character ingame through stuff like cheat engine, the game may crash.

A simple workaround is to make the replacement model use the same IDX targets as a playable base character. In AE, this is done through taildata. Later i'll add a "Swap taildata" button but for now this is what you should do

Loose G1M/G1T files:

If the model and texture you want to replace are loose files, do this:

1. Find the base playable character you want to replace.
Example: Dian Wei

2. Copy the last 6 bytes from that character’s G1M file.

3. Find the G1M file of the model you actually want to use.
Example: an NPC troop model.

4. Replace the last 6 bytes of that replacement G1M with the last 6 bytes from the base G1M.

5. Repeat the same process for the matching G1T file:
   copy the last 6 bytes from the base character’s G1T then replace the last 6 bytes of the replacement G1T.

What this does:
The Mod Manager uses those last 6 bytes to know which IDX entry the file belongs to. When you build and enable the mod, AE appends the new G1M and G1T to the container and updates the correct IDX entries to the new offsets and sizes.

Result:
The game will load the replacement model through the base character’s slots which helps bypass the normal crash checks.

To undo the change, use Disable Mod or Disable All Mods in Mod Manager. Nothing is permanently lost.

Important, DON'T do this with unpacked subcontainer files:

DON'T copy the last 6 bytes from files that came out of unpacked subcontainers.

Examples:
   files inside folders such as entry_00000
   G1M or G1T files extracted from a named subcontainer folder

Why:
Those inner files do not carry standalone taildata for Mod Manager use. The taildata belongs to the subcontainer itself, not the files inside it.

Replacing G1M/G1T inside a subcontainer:

If the character’s files are stored inside a subcontainer instead of as loose files:

1. Find the subcontainer folder that contains the G1M and G1T you want to replace.
2. Replace those files directly with your new ones.
3. Make sure the replacement files keep the exact same filenames as the originals.
4. Rebuild the subcontainer with AE.

Short version:
  If the files are loose: transfer taildata from the base G1M/G1T.
  If the files came from a subcontainer: replace the files directly and rebuild the subcontainer.

# Possible issues

Audio/subcontainer KVS files, let's talk about that. AE can repack the subcontainers KVS files are in and apply new audio to the supported games but only Warriors Orochi 3 has full audio replacing support until I find the KVS metadata files for Toukiden Kiwami, Dynasty Warriors 7 XL, Dynasty Warriors 8 XL, Dynasty Warriors 8 Empires, Bladestorm Nightmare, and Warriors All Stars. Later versions of AE should eliminate that issue but as of version 2.015 only Warriors Orochi 3 supports full audio replacing/adding.

You may see some subfolders unpacked with regular files but also empty files, don't delete the empty files if it belongs to the subcontainer (meaning it's stored within the folder where you found them), they're intentionally created to maintain indexing during repacking. It's normal behavior. Review Subcontainer Info section if needing more details.

# Extra Info

If you encounter any issues/have questions then let me know on here, reddit, or discord. If Koei Tecmo takes issue with Aldnoah Engine please contact me so I can comply, Aldnoah Engine is meant for modding offline games for players/modders to enjoy your games long after you finished supporting them.

I know the unit data for Warriors Orochi 3 is within the file entry_00032.bin, that's within the Pack_00 folder when you unpack Orochi 3.

Kybernes Tools (my other repository) is recommended for using with Aldnoah Engine, that will be my other main repository for GUI modding tools for Koei Tecmo games such as Festum Conversion, Wild Liberd, Kybernes Scanner, etc. They're more independent tools so i'm keeping them in the Kybernes Tools repository instead of this one. https://github.com/PythWare/Kybernes-Tools
