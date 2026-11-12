"""Irodori UTAU Maker - browser window (Gradio)."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gradio as gr  # noqa: E402

import core  # noqa: E402
import pipeline  # noqa: E402

PRESETS = {
    "Bright young woman": "明るく元気な若い女性の声。はっきりとした発音で、近い距離感。",
    "Calm adult woman": "落ち着いた大人の女性の声。やわらかく、ゆっくりと話す。",
    "Cute high voice": "かわいらしい高めの女の子の声。明るくはっきりと話す。",
    "Gentle young man": "やさしい若い男性の声。落ち着いていて、はっきりとした発音。",
    "Deep adult man": "低く落ち着いた大人の男性の声。ゆっくり、はっきりと話す。",
}
SET_NAMES = list(core.SETS.keys())
ALL_KANA = []
for _set in SET_NAMES:
    for _row in core.rows_for(_set, True):
        for _k, _ in _row:
            if _k not in ALL_KANA:
                ALL_KANA.append(_k)


def on_preset(label):
    return PRESETS.get(label, "")


def on_make_voice(caption, extra):
    path, msg = pipeline.make_voice(caption, extra)
    if path is None:
        return None, msg
    return path, "The voice is ready. Listen to it. Click the button again for a different voice."


def _watch():
    # Send the status every second. This also keeps the browser connection alive.
    while pipeline.JOB["running"]:
        status, text = pipeline.job_view()
        yield status, text, None
        time.sleep(1.0)
    status, text = pipeline.job_view()
    yield status, text, pipeline.JOB["zip"]


def on_style(label):
    return pipeline.STYLES.get(label, "")


def _tries(pitch_mode):
    return pipeline.PITCH_TRIES.get(pitch_mode, 0)


def _pitch_mode(tries):
    for label, n in pipeline.PITCH_TRIES.items():
        if n == int(tries or 0):
            return label
    return pipeline.PITCH_MODES[1]


def on_rename(folder):
    return core.rename_to_hiragana((folder or "").strip().strip('"'))


def on_reoto(folder, short):
    return core.reoto_folder((folder or "").strip().strip('"'), bool(short))


def on_redo_flagged(name, set_name, extra, style, mode, breaths, pitch_mode, target_hz, short):
    if not pipeline.JOB["running"]:
        redo = pipeline.flagged_sounds(name)
        if not redo:
            yield "### Status: No flagged sounds. Build the voicebank first.", "", None
            return
        pipeline.start_job(name, None, set_name, True, extra, style, mode, redo, breaths,
                           _tries(pitch_mode), target_hz, short)
    yield from _watch()


def on_build(name, ref, set_name, skip_done, extra, style, mode, breaths, pitch_mode, target_hz,
             short):
    if not pipeline.JOB["running"]:
        if not ref and pipeline.project_info(name) is None:
            yield "### Status: Step 1 is not complete. Make or upload a voice first.", "", None
            return
        pipeline.start_job(name, ref, set_name, skip_done, extra, style, mode, (), breaths,
                           _tries(pitch_mode), target_hz, short)
    yield from _watch()
    return
    # Send the status every second. This also keeps the browser connection alive.
    while pipeline.JOB["running"]:
        status, text = pipeline.job_view()
        yield status, text, None
        time.sleep(1.0)
    status, text = pipeline.job_view()
    yield status, text, pipeline.JOB["zip"]


def on_refresh():
    status, text = pipeline.job_view()
    return status, text, pipeline.JOB["zip"]


def _describe(info):
    if info["done"] >= info["total"]:
        return (f"Loaded **{info['name']}**. All {info['total']} sounds are made. "
                "Select a larger sound set or repair sounds in step 3.")
    return (f"Loaded **{info['name']}**: {info['done']} of {info['total']} sounds are made. "
            "Click **Build voicebank** to continue from this point.")


def on_restore():
    """Page load: bring back the last voicebank after a crash or a restart."""
    info = pipeline.last_project()
    names = pipeline.list_projects()
    if info is None:
        return (gr.update(),) * 10 + (gr.update(choices=names), "")
    return (info["name"], info["set_name"], info["ref"], info["extra"], info["style"],
            info["mode"], bool(info["breaths"]), _pitch_mode(info["tries"]), info["target_hz"],
            bool(info["short"]), gr.update(choices=names, value=info["name"]), _describe(info))


def on_load_project(project):
    info = pipeline.project_info(project) if project else None
    if info is None:
        return (gr.update(),) * 10 + ("",)
    return (info["name"], info["set_name"], info["ref"], info["extra"], info["style"],
            info["mode"], bool(info["breaths"]), _pitch_mode(info["tries"]), info["target_hz"],
            bool(info["short"]), _describe(info))


def on_tick():
    return pipeline.job_view()


def on_stop():
    pipeline.STOP["now"] = True
    return "The tool stops after the current generation."


def on_pick(name, set_name, kana):
    return pipeline.sound_path(name, kana, set_name)


def on_regen(name, set_name, kana, extra, style, mode):
    path, msg = pipeline.regenerate_one(name, set_name, kana, extra, style, mode)
    return path, msg


def on_open_folder():
    os.makedirs(pipeline.BANKS, exist_ok=True)
    pipeline.open_folder(pipeline.BANKS)
    return "Voicebank folder: " + pipeline.BANKS


with gr.Blocks(title="Irodori UTAU Maker") as demo:
    gr.Markdown(
        "# Irodori UTAU Maker\n"
        "This tool makes an OpenUtau voicebank from Irodori-TTS-v4.1-Small. "
        "Do the three steps from top to bottom.\n\n"
        "**Use only your own voice, a designed voice, or a voice whose owner agreed.**"
    )

    with gr.Row():
        project = gr.Dropdown([], label="Continue a saved voicebank (optional)")
        restore_msg = gr.Markdown("")

    gr.Markdown("## Step 1. Choose the voice")
    with gr.Row():
        with gr.Column():
            preset = gr.Dropdown(list(PRESETS.keys()), label="Voice idea (optional)")
            caption = gr.Textbox(label="Voice description (Japanese gives the best result)",
                                 lines=2, value=PRESETS["Bright young woman"])
            voice_btn = gr.Button("Make a new voice", variant="primary")
            voice_msg = gr.Markdown("")
        with gr.Column():
            ref = gr.Audio(type="filepath",
                           label="Voice for the voicebank (generated here, or upload a 5-15 second WAV)")
    gr.Markdown("The first generation downloads the model (about 3 GB). That generation takes "
                "several minutes.")

    gr.Markdown("## Step 2. Build the voicebank")
    with gr.Row():
        name = gr.Textbox(label="Voicebank name (English letters are safest)", value="MyIrodoriVoice")
        set_name = gr.Dropdown(SET_NAMES, value=SET_NAMES[0],
                               label="Sound set and voicebank type (CV, CVVC or VCV)")
    breaths = gr.Checkbox(value=False,
                          label="Add 4 breath sounds (lyrics in OpenUtau: br1, br2, br3, br4)")
    gr.Markdown("**Speaking style of the sounds.** Use a calm style if some sounds are shouted. "
                "Japanese text gives the best result.")
    with gr.Row():
        style_pick = gr.Dropdown(list(pipeline.STYLES.keys()), label="Style idea",
                                 value=list(pipeline.STYLES.keys())[0])
        mode = gr.Dropdown(pipeline.TEXT_MODES, value=pipeline.TEXT_MODES[0],
                           label="How the tool writes each sound")
    style = gr.Textbox(label="Style description (you can edit this text)", lines=2,
                       value=list(pipeline.STYLES.values())[0])
    gr.Markdown("**Pitch matching.** The TTS speaks some sounds much higher than other sounds. "
                "That makes the singing voice uneven. With pitch matching, the tool makes more "
                "takes and keeps the take that is nearest to the target pitch. The build is slower.")
    with gr.Row():
        pitch_mode = gr.Dropdown(pipeline.PITCH_MODES, value=pipeline.PITCH_MODES[1],
                                 label="Pitch matching")
        target_hz = gr.Number(value=0, label="Target pitch in Hz (0 = pitch of the voice sample)")
    short = gr.Checkbox(value=True, label="Short consonants (recommended). The TTS speaks slow "
                        "consonants. Fast songs then sound noisy and whispered.")
    skip_done = gr.Checkbox(value=True, label="Keep the sounds that are already made (continue a stopped build)")
    with gr.Row():
        build_btn = gr.Button("Build voicebank", variant="primary")
        stop_btn = gr.Button("Stop")
        folder_btn = gr.Button("Open voicebank folder")
        refresh_btn = gr.Button("Refresh status")
    status = gr.Markdown("### Status: Idle. No build is running.")
    note = gr.Markdown("")
    log = gr.Textbox(label="Progress", lines=12)
    zip_file = gr.File(label="Finished voicebank (.zip). Drag this file onto the OpenUtau window.")

    gr.Markdown("## Step 3. Check and repair sounds (optional)")
    with gr.Row():
        kana = gr.Dropdown(ALL_KANA, label="Sound (kana, transition such as \"a k\" or \"a か\", or breath)",
                           allow_custom_value=False)
        regen_btn = gr.Button("Make this sound again")
        flagged_btn = gr.Button("Make the flagged sounds again")
    preview = gr.Audio(type="filepath", label="Listen", interactive=False)
    regen_msg = gr.Textbox(label="Result", lines=3)

    gr.Markdown("## Step 4. Auto-oto a voicebank folder (optional)\n"
                "This step writes a new oto.ini for a folder of CV WAV files. The file names must "
                "be romaji (ka.wav) or hiragana. The old oto.ini stays as a backup file. "
                "Voicebanks from step 2 get the same oto.ini automatically.")
    with gr.Row():
        oto_folder = gr.Textbox(label="Folder path", placeholder="C:\\UTAU\\voice\\MyBank")
        oto_short = gr.Checkbox(value=True, label="Short consonants (changes the WAV files, "
                                "keeps the originals in original_wavs)")
        oto_btn = gr.Button("Write a new oto.ini")
    oto_msg = gr.Textbox(label="Result", lines=5)

    gr.Markdown("## Step 5. Change WAV file names to hiragana (optional)\n"
                "This step renames the romaji files of a voicebank folder, for example "
                "ka.wav to か.wav. It also updates oto.ini and keeps a backup of it.")
    with gr.Row():
        rename_folder = gr.Textbox(label="Folder path",
                                   placeholder="C:\\IrodoriUtauMaker\\voicebanks\\MyIrodoriVoice")
        rename_btn = gr.Button("Change the names to hiragana")
    rename_msg = gr.Textbox(label="Result", lines=4)

    with gr.Accordion("Advanced (leave empty unless a guide tells you)", open=False):
        extra = gr.Textbox(label="Extra infer.py options",
                           placeholder="Example for low video memory: --model-precision bf16")

    preset.change(on_preset, preset, caption)
    voice_btn.click(on_make_voice, [caption, extra], [ref, voice_msg])
    style_pick.change(on_style, style_pick, style)
    oto_btn.click(on_reoto, [oto_folder, oto_short], oto_msg)
    rename_btn.click(on_rename, rename_folder, rename_msg)
    build_btn.click(on_build, [name, ref, set_name, skip_done, extra, style, mode, breaths,
                               pitch_mode, target_hz, short],
                    [status, log, zip_file])
    flagged_btn.click(on_redo_flagged, [name, set_name, extra, style, mode, breaths,
                                        pitch_mode, target_hz, short],
                      [status, log, zip_file])
    stop_btn.click(on_stop, None, note, queue=False)
    folder_btn.click(on_open_folder, None, note, queue=False)
    refresh_btn.click(on_refresh, None, [status, log, zip_file], queue=False)
    demo.load(on_refresh, None, [status, log, zip_file])
    demo.load(on_restore, None, [name, set_name, ref, extra, style, mode, breaths, pitch_mode, target_hz, short,
                                  project, restore_msg])
    project.change(on_load_project, project, [name, set_name, ref, extra, style, mode, breaths,
                                                 pitch_mode, target_hz, short, restore_msg])
    if hasattr(gr, "Timer"):  # newer Gradio: update the status automatically
        gr.Timer(3).tick(on_tick, None, [status, log])
    kana.change(on_pick, [name, set_name, kana], preview)
    regen_btn.click(on_regen, [name, set_name, kana, extra, style, mode], [preview, regen_msg])

if __name__ == "__main__":
    # allowed_paths lets the page play and download files from this tool's folders.
    demo.queue().launch(inbrowser=True, allowed_paths=[pipeline.BASE])
