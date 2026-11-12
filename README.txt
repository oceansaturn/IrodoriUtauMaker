IRODORI UTAU MAKER
==================
This tool makes a Japanese CV, CVVC or VCV voicebank for OpenUtau from Irodori-TTS-v4.1-Small.
You do not type commands. You do not make WAV files by hand.

WARNINGS (read these first)
- Use only your own voice, a designed voice, or a voice whose owner agreed.
  The Irodori-TTS model card prohibits voice cloning without consent.
- Put this folder in a short path without Japanese letters. Example: C:\IrodoriUtauMaker
- You need Windows 10 or 11, 15 GB of free disk space, and an internet connection.
- An NVIDIA graphics card is recommended. Without one, each generation takes minutes.

INSTALL (one time)
1. Double-click 1_Install.bat.
2. Wait until the window shows "Installation complete".

MAKE A VOICEBANK
1. Double-click 2_Start.bat. A browser page opens.
2. Step 1: click "Make a new voice". Listen to the result.
   Click again until you like the voice. You can also upload a WAV of your own voice.
3. Step 2: select "Quick test - CV" and click "Build voicebank".
   The first run downloads the model (about 3 GB).
4. If the quick test works, select a CV or CVVC sound set and click "Build voicebank" again.
5. Step 3 (optional): listen to a sound. Click "Make this sound again" if it is bad.

VOICEBANK TYPES (the "Sound set and voicebank type" list)
- CV: one sound for each kana. Simple and fast to build. Use the DEFAULT phonemizer.
- CVVC: the CV sounds plus 162 vowel-consonant transitions (aliases such as "a k").
  Notes connect more smoothly. The build takes about 2.5 times longer.
  Use the JA CVVC phonemizer.
- VCV: the CV sounds plus each kana after each vowel (aliases such as "a か").
  This type gives the smoothest connection between notes. The build is the longest:
  707 sounds for Basic, which is about 5 times the CV build. Use the JA VCV phonemizer.
- You can change a finished CV voicebank to CVVC or VCV. Keep the same name, select a CVVC set,
  and click "Build voicebank". The tool keeps the CV sounds and adds the transitions.
- "Short consonants" changes the CV sounds only. It does not change VCV transitions.

BREATHS
- Select "Add 4 breath sounds" before you build.
- In OpenUtau, type br1, br2, br3 or br4 as the lyric of a short note.
- The breaths are spoken sighs from the TTS. Listen to them in step 3 and remake bad ones.

PITCH MATCHING (uneven or shouted voice)
- The TTS speaks some sounds much higher than other sounds. The singing voice is then uneven.
  A new oto.ini cannot correct this. The sounds must be made again.
- Keep "Pitch matching" on Normal or Strong, and select the style "Low, calm and flat".
- The tool makes more takes of each row and keeps the take nearest to the target pitch.
- The target is the pitch of your voice sample. You can also type a target in Hz.
- After a build, the Progress box shows how many sounds are near the target.
- Click "Make the flagged sounds again" in step 3 to replace the other sounds.

SHORT CONSONANTS (noisy or whispered singing)
- The TTS speaks slow consonants. In a fast song, most of each note is then consonant noise.
- Keep "Short consonants" selected. The tool cuts each consonant to 40-70 ms.
- The original sounds stay in the "work" folder. Clear the box and build again to undo this.

AUTO-OTO (step 4)
- Every build writes oto.ini automatically. Click "Build voicebank" again to get a new
  oto.ini for a finished voicebank. This is fast because the sounds exist.
- Step 4 writes a new oto.ini for any folder of CV WAV files (ka.wav or hiragana names).
  The old oto.ini stays as oto_backup_1.ini.

HIRAGANA FILE NAMES (step 5)
- The tool writes romaji file names (ka.wav). These names are safe on every PC.
- Step 5 changes the names of a voicebank folder to hiragana (か.wav, "a か.wav").
  It also updates oto.ini and keeps the old file as a backup.
- Do this step last. A new build writes romaji names again.
- A zip file with hiragana names needs the correct archive encoding during installation.
  Copy the folder into the OpenUtau "Singers" folder to avoid this problem.

AFTER A CRASH
- Double-click 2_Start.bat. The page loads the last voicebank.
- Click "Build voicebank". The tool continues from the saved sounds.

USE THE VOICEBANK IN OPENUTAU
1. Drag the finished .zip file onto the OpenUtau window.
2. In the install window, keep the encoding Shift-JIS. Click Next until it finishes.
3. Select the singer on a track.
4. Select the phonemizer: DEFAULT for CV, JA CVVC for CVVC, JA VCV for VCV.
5. Type hiragana lyrics (か). A CV voicebank also accepts romaji lyrics (ka).

HOW IT WORKS
- The tool tells Irodori-TTS to say one kana row, for example "かー。きー。くー。けー。こー。".
- It cuts the recording at the pauses. One WAV file is made for each kana.
- For CVVC, it also generates pairs such as "アカ" and keeps the part from "a" into "k".
- It measures each sound and writes oto.ini (the timing file that OpenUtau reads).
- If a row does not split correctly, the tool generates each sound alone.
- The oto.ini values are automatic estimates. Adjust them in OpenUtau if a sound is wrong.

IF SOMETHING FAILS
- Copy the error text from the black window or the Progress box. Send it to Claude.
- A stopped build continues from the same point when you click "Build voicebank" again.
- Files: finished voicebanks are in the "voicebanks" folder. Temporary audio is in "work".
