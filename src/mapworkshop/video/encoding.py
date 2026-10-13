"""FFmpeg execution, full-decode validation and size-constrained exports."""
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import imageio_ffmpeg


def encode(args, log):
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w') as stream:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-hide_banner',*map(str,args)],
                       stdout=stream,stderr=stream,check=True)


def validate(path, expected_duration=None, expected_frames=None, max_bytes=None):
    path = Path(path)
    if max_bytes is not None and path.stat().st_size >= max_bytes:
        raise ValueError(f'Export must be smaller than {max_bytes} bytes: {path}')
    check = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(path),'-f','null','-'],
                           capture_output=True,text=True,check=True)
    if check.stderr.strip():
        raise ValueError(f'Export decode errors: {check.stderr}')
    reader = imageio_ffmpeg.read_frames(str(path),pix_fmt='rgb24')
    metadata = next(reader)
    count = sum(1 for _ in reader)
    if expected_frames is not None and count != expected_frames:
        raise ValueError(f'Expected {expected_frames} frames, found {count}: {path}')
    if expected_duration is not None and abs(metadata['duration']-expected_duration) > .1:
        raise ValueError(f'Incomplete duration: {path}')
    return dict(file=path.name,bytes=path.stat().st_size,frames=count,
                duration=metadata['duration'],size=metadata['size'])


def export_profile(source, destination, profiles, name):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or source == destination:
        raise FileExistsError(f'Export destination already exists: {destination}')
    profile = tomllib.loads(Path(profiles).read_text())['profiles'][name]
    reader = imageio_ffmpeg.read_frames(str(source)); info = next(reader); reader.close()
    destination.parent.mkdir(parents=True, exist_ok=True)
    limit = profile.get('max_bytes')
    audio = profile.get('audio_kbps',128)
    bitrate = profile.get('video_kbps',1850)
    if limit:
        bitrate = min(bitrate, int(limit*.96*8/info['duration']/1000)-audio)
        if bitrate < 100:
            raise ValueError('Duration is too long for this size profile')
    # Encode to a temporary sibling; publish only after validation succeeds.
    with tempfile.TemporaryDirectory(prefix='bfx-encode-',dir=destination.parent) as folder:
        folder = Path(folder); temporary = folder / destination.name
        common = ['-i',source,'-map','0:v:0','-c:v','libx264','-preset',profile.get('preset','slow'),
                  '-pix_fmt','yuv420p']
        if 'width' in profile:
            common += ['-vf',f"scale={profile['width']}:{profile['height']}:flags=lanczos"]
        if 'crf' in profile and limit is None:
            common += ['-crf',str(profile['crf'])]
        else:
            common += ['-b:v',f'{bitrate}k','-passlogfile',folder/'pass']
            encode(common+['-pass','1','-an','-f','null','-'],folder/'pass1.log')
            common += ['-pass','2']
        encode(common+['-map','0:a:0?','-c:a','aac','-b:a',f'{audio}k','-movflags','+faststart',temporary],folder/'export.log')
        result = validate(temporary,expected_duration=info['duration'],max_bytes=limit)
        temporary.replace(destination)
    destination.with_suffix('.validation.json').write_text(json.dumps({'outcome':'pass',**result},indent=2)+'\n')
    return result
