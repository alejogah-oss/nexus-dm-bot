import os, subprocess, sys
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FONT = os.path.join(os.path.dirname(__file__), "fonts/Anton-Regular.ttf")
CLIPS_DIR = "/Users/macbookpro/nexus-automation/test_output/corolla_familia/clips"
OUT = "/Users/macbookpro/nexus-automation/test_output/corolla_familia/CorollaFamilia_final.mp4"

# (filename, duration_s, year_label or None)
SCENES = [
    ("clip_01.mp4", 4, "1968-1970"),
    ("clip_02.mp4", 4, "1971-1974"),
    ("clip_03.mp4", 4, "1975-1979"),
    ("clip_04.mp4", 4, "1980-1983"),
    ("clip_05.mp4", 5, "1984-1987"),
    ("clip_06.mp4", 4, "1988-1992"),
    ("clip_07.mp4", 4, "1993-1997"),
    ("clip_08.mp4", 4, "1998-2002"),
    ("clip_09.mp4", 4, "2003-2008"),
    ("clip_10.mp4", 4, "2009-2013"),
    ("clip_11.mp4", 4, "2014-2019"),
    ("clip_12.mp4", 3, "2020-2026"),
    ("clip_13_family.mp4", 5, None),
    ("clip_14_beauty.mp4", 4, None),
]
TRANSITIONS = [0.35] * 11 + [0.6, 0.6]  # 11 between the 12 generations, then 0.6 into family, 0.6 into beauty

def drawtext(text, size, color, y, alpha_expr):
    return (
        f"drawtext=fontfile={FONT}:text='{text}':fontsize={size}:fontcolor={color}:"
        f"borderw=6:bordercolor=black:x=(w-text_w)/2:y={y}:alpha='{alpha_expr}'"
    )

def window_alpha(start, end, fade=0.3):
    # alpha ramps up over `fade`s at start, holds, ramps down over `fade`s before end
    return (
        rf"if(lt(t\,{start})\,0\,"
        rf"if(lt(t\,{start+fade})\,(t-{start})/{fade}\,"
        rf"if(lt(t\,{end-fade})\,1\,"
        rf"if(lt(t\,{end})\,({end}-t)/{fade}\,0))))"
    )

def main():
    durations = [d for _, d, _ in SCENES]
    n = len(SCENES)

    # Compute xfade offsets (relative to t=0 of the whole chain) and each clip's
    # "clean" visible window [win_start, win_end] for text placement.
    cum = durations[0]
    win_start = [0.0]
    offsets = []
    for i in range(1, n):
        t = TRANSITIONS[i - 1]
        offset = cum - t
        offsets.append(offset)
        win_start.append(offset + t)  # next clip's clean content starts once its fade-in completes
        cum = cum + durations[i] - t
    total = cum

    win_end = []
    for i in range(n):
        if i < n - 1:
            win_end.append(offsets[i])
        else:
            win_end.append(total)
    # first clip's window ends at its own fade-out start
    win_end[0] = offsets[0] if n > 1 else total

    print("Escena  inicio   fin     duracion_visible")
    for i, (fname, d, label) in enumerate(SCENES):
        print(f"{i:02d} {fname:20s} {win_start[i]:6.2f} {win_end[i]:6.2f}  ({win_end[i]-win_start[i]:.2f}s) {label or ''}")
    print(f"Duracion total: {total:.2f}s")

    # Build filter_complex
    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]scale=-2:1920,crop=1080:1920:'(iw-1080)/2':0,setsar=1,fps=30[c{i}];")

    # Chain xfade
    chain = "c0"
    for i in range(1, n):
        prev = chain
        label = f"x{i}"
        dur = TRANSITIONS[i - 1]
        offset = offsets[i - 1]
        parts.append(f"[{prev}][c{i}]xfade=transition=fade:duration={dur}:offset={offset:.3f}[{label}];")
        chain = label

    # Text overlays
    hook_fade = window_alpha(0, 3.2)
    text_layers = [
        drawtext("58 ANOS", 78, "white", 260, hook_fade),
        drawtext("UNA SOLA FAMILIA", 78, "0xEB0A1E", 360, hook_fade),
    ]
    for i, (fname, d, label) in enumerate(SCENES):
        if label:
            a = window_alpha(win_start[i], win_end[i])
            text_layers.append(drawtext(label, 50, "white", 260, a))

    fam_i = 12  # clip_13_family index
    reveal_a = window_alpha(win_start[fam_i], win_end[fam_i])
    text_layers.append(drawtext("HOY, LA FAMILIA", 78, "white", 260, reveal_a))
    text_layers.append(drawtext("SIGUE CRECIENDO", 78, "0xEB0A1E", 360, reveal_a))

    beauty_i = 13  # clip_14_beauty index
    cta_a = window_alpha(win_start[beauty_i], total, fade=0.4)
    text_layers.append(drawtext("TAMBIEN SERAS FAMILIA", 72, "white", 1400, cta_a))
    text_layers.append(drawtext("ESCRIBENOS (954) 910-6671", 68, "0xEB0A1E", 1500, cta_a))

    text_layers.append(drawtext("@tucarroconalejo", 44, "white", 1720, "1"))

    parts.append(f"[{chain}]" + ",".join(text_layers) + "[vout];")

    filt = "\n".join(parts)
    script_path = "/tmp/corolla_film_filter.txt"
    with open(script_path, "w") as f:
        f.write(filt)

    cmd = [FFMPEG, "-y"]
    for fname, _, _ in SCENES:
        cmd += ["-i", os.path.join(CLIPS_DIR, fname)]
    cmd += ["-filter_complex_script", script_path, "-map", "[vout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-an", OUT]

    print("Ejecutando ffmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFMPEG ERROR:")
        print(result.stderr[-4000:])
        sys.exit(1)
    print(f"LISTO -> {OUT}")

if __name__ == "__main__":
    main()
