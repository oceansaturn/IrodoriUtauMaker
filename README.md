# Irodori UTAU Maker

Irodori UTAU Maker makes a Japanese CV, CVVC or VCV voicebank for OpenUtau from
[Irodori-TTS-v4.1-Small](https://huggingface.co/Aratako/Irodori-TTS-v4.1-Small).
You do not type commands, and you do not make WAV files by hand.

> **Warning.** Use only your own voice, a designed voice, or a voice whose owner agreed.
> The Irodori-TTS model card prohibits voice cloning without consent.

## Requirements

- Windows 10 or 11
- 15 GB of free disk space and an internet connection
- An NVIDIA graphics card is recommended. Without one, each generation takes minutes.

## Download and install

1. Click the green **Code** button on this page, then **Download ZIP**.
2. Unzip the folder to a short path. Example: `C:\IrodoriUtauMaker`
3. Double-click `1_Install.bat`. Wait for "Installation complete".
4. Double-click `2_Start.bat`. A browser page opens.

## Features

- Voice from a description, or from a WAV of your own voice
- CV, CVVC and VCV sound sets, with optional breath sounds
- Automatic oto.ini
- Pitch matching: keeps the take of each sound that is nearest to the voice pitch
- Short consonants for fast songs
- Speaking-style control
- A stopped or crashed build continues from the saved sounds
- Auto-oto for any folder of CV WAV files
- Bulk change of WAV file names from romaji to hiragana, with oto.ini update

`README.txt` contains the full instructions.

## Files

| File | Function |
|---|---|
| `1_Install.bat` | One-time installation of uv, Git, Irodori-TTS and the libraries |
| `2_Start.bat` | Starts the tool |
| `app/utau_maker.py` | The browser page |
| `app/pipeline.py` | Runs Irodori-TTS and manages the build |
| `app/core.py` | Sound cutting, oto.ini, pitch measurement |

The installer downloads Irodori-TTS and the model. They are not part of this repository.

## License

This project uses the [PolyForm Noncommercial License 1.0.0](LICENSE.md).

- You can use, change and share this tool for noncommercial purposes.
- You cannot sell this tool or a changed version of it.
- You must keep the license and this notice with each copy:

Required Notice: Copyright (c) 2026 oceansaturn (https://github.com/oceansaturn/IrodoriUtauMaker)

The license applies to this tool only. Irodori-TTS and its model have their own licenses.
