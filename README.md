# Aldnoah Engine Info
Aldnoah Engine is a PC-only modding toolkit for Koei Tecmo games that store assets in BIN containers and IDX index pairs. It ships with a Tkinter GUI that lets you unpack/decompress game files with taildata, repack g1pack2/KVS subcontainers, and launch a built-in Mod Creator and Mod Manager. When you unpack, Aldnoah Engine appends a tiny 6 byte taildata guide to each extracted file which is a 1 byte idx_marker, 4 bytes idx_entry_offset, and a 1 byte comp_marker. The Mod Manager uses that taildata to know exactly which IDX entry to patch and which BIN to append to, then it can also restore/disable mods safely later. Game-specific behavior is defined in Configs/<GAME>.ref, loaded by load_ref_config(). The loader supports single values, comma lists, continuation lines, and repeated keys.

Modded files do not have to be the same size as the original, Aldnoah Engine supports dynamic file sizes so if your mod is larger/smaller than the original file/files that's not an issue. Another thing, the Mod Manager can apply mods without needing to recompress the files. The games can load decompressed versions of compressed assets. I suggest keeping "Force uncompressed IDX Flag" toggled in Mod Manager.

<img width="1009" height="822" alt="a1" src="https://github.com/user-attachments/assets/6b4a727f-5182-4ea5-8dcd-cd8ee42707f8" />

# What is needed

Python 3 installed, this is a dependency free tool suite so you just need Python installed to run the scripts.

If you want to make audio mods (replacing/adding new audio such as voiced audio, sounds, music, etc) you will need kvs2ogg which is in the Musou Warriors discord server within the resources-and-other channel. That is a tool that can convert kvs files to wav, mp3, and ogg and converting back to KVS. Read "Audio Modding" section for a guide.

Noesis and specifically Joschuka's noesis files (https://github.com/Joschuka/Project-G1M) are needed if you want to view/convert G1M/G1T files. It's important to know the G1M/G1T formats have changed over the years across games so porting G1M/G1T files from other Koei Tecmo games may require some additional legwork. eArmada8 made a G1M tool for gust games that also works for other Koei Tecmo games so you may want to view it as well https://github.com/eArmada8/gust_stuff.

# How to use Aldnoah Engine

Launch the GUI via main.pyw (it just creates a Tk root and starts Core_Tools). You can double click it or run through cmd but i'd just double click the file. I highly recommend backing up your game files before using Aldnoah Engine.

# Supported games (currently only PC games)

Dynasty Warriors 7 XL, Dynasty Warriors 8 XL, Dynasty Warriors 8 Empires, Warriors Orochi 3, Bladestorm Nightmare, and Warriors All Stars.

# What can be done

Unpack/decompress assets using a per-game .ref config (custom metadata files I designed). Compression modes include zlib/zlib_header/zlib_split/none/auto.

Append mods/files to the end of containers and updating IDX entries to tell the games to read from new offsets instead (Mod Manager section will explain more).

Detect and handle split-zlib streams (when Omega Force compresses chunks of sections across a file rather than compressing all of a single file's data as 1 blob) via structure checks.

Repack subcontainers from a folder:

If the folder contains .kvs chunks then it builds a KVS container

Otherwise builds a g1pack2 container
It can also pull taildata from a chosen base file and append it to the output for mod-manager compatibility.

# Types of mods that can be made

A lot, we have the same modding potential as larger modding communities like Xenoverse 2. To do any file mods you have to have access to the files, which Aldnoah Engine gives. Too many types of mods to list, so the quick rundown is since we can access the files we have the ability to mod game assets and replace them with other assets. However Aldnoah Engine is a tool suite for unpacking, decompressing, repacking, appending, and applying/disabling mods through Mod Manager. So essentially, a tool suite to access the files and apply/disable modded files. Separate GUI tools like Unit Data Editor (handles parameters like stats, motion/moveset, model, etc), Stage Data Editor (handles battlefield parameters like which troops/officers appear in the stage, coordinates of where units spawn, etc), and other GUI tools will be made separately.

# Mod Creator

Creates mod files by turning modded files into compatible files with the Mod Manager. Also has some metadata support like author of the mod, naming mod file, specifying the version of your mod, and having a description with your mod.

Single mod = 1 file payload

Package mod = N file payloads

Both use a consistent header, size, and data payload format I designed. If you're doing a single file mod use single file, if you're making large scale mods that mod more than 1 file I suggest using Package mod button.

When using Mod Package, I suggest selecting a folder that contains only the files you want applied to the game within the folder (i.e., if I want to mod unitdata and apply audio mods i'd create a mod folder, place all the files in there I want applied to the game and then use mod package). Mod Package gets all the files within the folder selected and turns it into a single file release, you don't need subdirectories within a folder that is meant to store mods to turn into package mods, only the files themselves.

<img width="1272" height="731" alt="a2" src="https://github.com/user-attachments/assets/82d9c57b-0d50-4787-8366-942dd1715240" />

# Mod Manager

Applies/disables mods with a ledger system, splits payload from trailing taildata, appends payload to BIN with 16 byte alignment, patches the IDX entry at the recorded offset, and supports Disable All (including truncating BINs back to original sizes, use this when wanting to disable all mods). The Mod Manager does not rebuild BIN containers, that is inefficient. Instead it appends your modded files to the end of the containers, updates the IDX files which then makes the game load the modded files rather than the original unmodded files. This ensures quick, easy, and safe mod applying/disabling.

<img width="1645" height="794" alt="a3" src="https://github.com/user-attachments/assets/eaf22b5e-f311-4dea-a0e6-4332a9376a83" />

# Taildata

It is essential that unless you know what you're doing, you must not remove taildata. Taildata is 6 bytes of data added to every unpacked file (not files unpacked from subcontainers since subcontainer unpacked files get repacked, they don't need taildata) that is used by the Mod Manager for applying/disabling mods. Taildata does not impact the usability/moddability of files so mod away without worry. To clarify on subcontainers, the subcontainers have taildata but the files unpacked from the subcontainers won't and shoudn't have taildata since you're not applying those individual files to the game, you're applying a repacked subcontainer since that is what the game expects.

# Audio Modding

KVS files unpacked may be loose or a subcontainer, it varies and that's just how Koei Tecmo designed KVS files. So some KVS files extracted may be loose solo KVS files, some may be a big KVS file that actually stores thousands of sequentially stored KVS files (which in that case, they're unpacked into a folder named after the KVS subcontainer such as entry_00000 which pairs with entry_00000.kvs as an example, that subcontainer stores 9,750 KVS files).

To replace audio, place your new kvs files within the folder of the kvs subcontainer you want to rebuild (i.e., entry_00000 folder which has 9,750 kvs files, if you wanted to replace audio files from it you'd replace the files within it with yours). Name your new kvs files after the kvs files you want to replace (i.e., let's say 024.kvs belongs to xiahou dun and you want to replace with a new voiced audio, name your new voiced audio 024.kvs and replace the original kvs within the subfolder). It's important you place your KVS files into the subcontainer folder before running subcontainer repacking. So let's say you want to dub Orochi 3, you'd replace each Japanese KVS file within the subcontainers with your KVS file named after the file it's replacing and then rebuild with aldnoah engine. After that you click the "Update KVS Metadata" button in the main GUI (and naturally follow the instructions the popup says), use Mod Creator for the KVS subcontainer/subcontainers to turn into a mod file/package when you finish with Updating KVS Metadata, and then apply with Mod Manager.

The Update KVS Metadata button only supports Warriors Orochi 3 for now, i'll try adding support for the other 5 games.

<img width="552" height="383" alt="a5" src="https://github.com/user-attachments/assets/3d7c14cc-218f-472c-89c0-dc51c4e0a7db" />

# Games that support full KVS Audio replacing/adding as of version 0.9

Warriors Orochi 3. You could literally dub the entire game with English audio or other languages, or just replace audio files if your goal isn't dubbing. Orochi 3 has full support as of version 0.9.

# Things to keep in mind

Each subcontainer unpacked will create a folder named after the subcontainer file which stores the subcontainer's unpacked files.

Depending on the game the unpacking may take a few minutes. If the status bar seems stuck to you, it isn't. It's doing a lot of unpacking/decompressing, Orochi 3 has over 164k files so some games may take a few minutes to unpack.

You may see a comp_log.txt file. It'll probably have some lines saying things like "zlib decompress failed at IDX entry 5903 (BIN=LINKFILE_000.BIN, offset=0x170ABA00, size=0x25): Could not find a valid Omega-style zlib_header stream in blob; wrote raw to entry_03655.bin", that means Omega Force tagged a file with the compression marker in the IDX file, that's not an issue on your part or Aldnoah Engine. No idea why Omega Force has some files marked as compressed that aren't compressed. Just ignore those kind of warnings, it's basically saying a file was flagged as compressed by the IDX file but isn't compressed.

This is a huge project and I'm the only one currently reversing the games. I don't have enough storage space at the moment to personally reverse other games not listed, if you want support for other Koei Tecmo games you need to do some legwork, by that I mean you need to look into the file formats for games not listed that you're interested in and document the structure of the container files. I can definitely add support for other games I don't own if someone provides some documentation, then i'll update Aldnoah Engine to support said games.

If you want GUI file modding tools like a Unit Data Editor, Stage Editor, etc then you may need to help by identifying which files store said data and then documenting the file's format. There are way too many files for me to find everything on my own, Warriors Orochi 3 alone has over 164k files when unpacked. I have started building a Unit Data Editor for Orochi 3 and Bladestorm Nightmare though ;). Use Batch Binary File Scanner (a tool I made) to scan through files quickly/easily. To help with finding specific files since files are extracted with incrementing filenames (a lot of the later Koei Tecmo games either strip filenames from the executable or obfuscate them, so Aldnoah Engine unpacks with incrementing filenames and extensions based on the file's data) and there will be thousands of files unpacked, I suggest using my Batch Binary File Scanner that scans binary files in the selected directory and all subdirectories within it. The link is https://github.com/PythWare/Batch-Binary-File-Scanner

g1pack1/g1pack2 are custom extensions I made for Aldnoah Engine since a lot of subcontainers when unpacked from BINS, LINKDATA, etc don't have filenames nor extensions detected within the executables. I have implemented support for unpacking g1pack2 subcontainers but not gtpack1 subcontainers yet, the format for subcontainers varies across games. For example, Orochi 3 has several different types of subcontainers and they vary with how they store data (some store files sequentially without a TOC, some store with a TOC, etc).

Later Koei Tecmo games have special checks inplace when you use characters that aren't playable such as in Orochi 3. Usually the game will crash. To bypass the checks other than pulling out ghidra and altering the executable you can find which G1M file (model file) belongs to the character you want to use as a base to replace, copy the last 6 bytes of the base G1M file you want to replace (i.e., let's say you want to replace Dian Wei with a NPC troop, grab the last 6 bytes from Dian Wei's G1M file), find the G1M file of the model you do want to use, replace the last 6 bytes of the taildata at the end of the G1M file you want to use with the taildata from the base G1M you're replacing (taildata is the last 6 bytes, so you'd grab Dian Wei's taildata in this example and replace say NPC Troop's taildata with it), find the G1T file (texture file, used for various things but models rely on G1T) that belongs to the base model you want to replace and copy its taildata (last 6 bytes at the end of the file), find the G1T file of the model you want to use with your new G1M replacement and replace the last 6 bytes/taildata with the taildata from the base G1T file. What this essentially does is change which IDX entries will seek the G1M and G1T files we want to use. By replacing the taildata with the base G1T/G1M files we want to replace, the Mod Manager (after you turned your modded files into a package mod) will append the new G1M/G1T files to the end of the container and update the IDX entries to the new offsets, sizes, etc. When the game runs it shouldn't crash because this bypasses those checks I mentioned, the game will load the model you replaced the base model with. To revert this change, just click disable mod/disable all mods in Mod Manager. nothing is lost, it's a safe design.

# Possible issues

Audio/subcontainer KVS files, let's talk about that. Aldnoah Engine can repack the subcontainers KVS files are in and apply new audio to the supported games but only Warriors Orochi 3 has full audio replacing support until I find the KVS metadata files for Dynasty Warriors 7 XL, Dynasty Warriors 8 XL, Dynasty Warriors 8 Empires, Bladestorm Nightmare, and Warriors All Stars. Version 1.0 of Aldnoah Engine should eliminate that issue but as of version 0.9 only Warriors Orochi 3 supports full audio replacing/adding.

# Extra Info

If you encounter any issues/have questions then let me know on here, reddit, or discord. If Koei Tecmo takes issue with Aldnoah Engine please contact me so I can comply, Aldnoah Engine is meant for modding offline games for players/modders to enjoy your games long after you finished supporting them.

I know the unit data for Warriors Orochi 3 is within the file entry_00032.bin, that's within the Pack_00 folder when you unpack Orochi 3. I'll give a sneak peak at the Unit Data Editor since it isn't finished yet
<img width="1003" height="825" alt="a4" src="https://github.com/user-attachments/assets/fd621640-fad2-4e9a-b0e1-fa685f5281eb" />
