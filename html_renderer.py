import asyncio
from playwright.async_api import async_playwright


async def _render(html: str, output_path: str, width: int, height: int):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.set_content(html, wait_until="networkidle")
        await page.wait_for_timeout(800)
        await page.screenshot(path=output_path, clip={"x": 0, "y": 0, "width": width, "height": height})
        await browser.close()


def render_to_image(html: str, output_path: str, width: int = 1080, height: int = 1080):
    asyncio.run(_render(html, output_path, width, height))
    return output_path


async def _render_video(html: str, out_mp4: str, width: int, height: int, duration_s: float):
    import glob
    import os
    import subprocess
    import tempfile

    rec_dir = tempfile.mkdtemp(prefix="nexus_vid_")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=rec_dir,
            record_video_size={"width": width, "height": height},
        )
        page = await ctx.new_page()
        await page.set_content(html, wait_until="networkidle")
        await page.wait_for_timeout(int(duration_s * 1000))
        await ctx.close()
        await browser.close()

    webm = sorted(glob.glob(os.path.join(rec_dir, "*.webm")), key=os.path.getmtime)[-1]
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        # LaunchAgent corre Python 3.11 sin imageio_ffmpeg — usar el binario del venv
        _venv_ff = os.path.join(
            os.path.dirname(__file__),
            "venv/lib/python3.14/site-packages/imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1",
        )
        ffmpeg = _venv_ff if os.path.exists(_venv_ff) else "ffmpeg"
    # Recorta el primer medio segundo (carga de página) y fija 30fps
    subprocess.run(
        [ffmpeg, "-y", "-ss", "0.5", "-i", webm,
         "-c:v", "libx264", "-preset", "fast", "-crf", "20",
         "-r", "30", "-pix_fmt", "yuv420p", "-an", out_mp4],
        check=True, capture_output=True,
    )
    os.remove(webm)
    return out_mp4


def render_to_video(html: str, output_path: str, width: int = 1080,
                    height: int = 1080, duration_s: float = 6.0):
    """Graba un template HTML animado (CSS keyframes) como video MP4."""
    asyncio.run(_render_video(html, output_path, width, height, duration_s))
    return output_path
